import os
import json
import asyncio
import shutil
import time
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import dashscope
from qwen_agent.agents import Assistant
from apscheduler.schedulers.background import BackgroundScheduler
import docs_assistant as da
import stock_assistant as sa

logger = logging.getLogger(__name__)

# ====== 管理员认证 ======
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

def verify_admin(authorization: Optional[str] = None) -> bool:
    """验证管理员身份，Header: Authorization: Basic admin:season"""
    if not authorization:
        return False
    try:
        import base64
        scheme, credentials = authorization.split(' ', 1)
        if scheme.lower() != 'basic':
            return False
        decoded = base64.b64decode(credentials).decode('utf-8')
        username, password = decoded.split(':', 1)
        return username == ADMIN_USERNAME and password == ADMIN_PASSWORD
    except Exception:
        return False

# ====== 普通用户查询限制 ======
GUEST_MAX_QUERIES = 5          # 非管理员最多查询次数
GUEST_MAX_QUERY_LEN = 200      # 非管理员单次问题最大字数
GUEST_RESET_HOURS = 24         # 计数重置周期（小时）

# { ip: { "count": int, "reset_at": float } }
_guest_usage = defaultdict(lambda: {"count": 0, "reset_at": 0})


def get_client_ip(request: Request) -> str:
    """获取客户端 IP"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_guest_limit(ip: str) -> dict:
    """
    检查普通用户查询限额，返回 {"allowed": bool, "remaining": int, "message": str}
    """
    now = time.time()
    usage = _guest_usage[ip]

    # 过期重置
    if now > usage["reset_at"]:
        usage["count"] = 0
        usage["reset_at"] = now + GUEST_RESET_HOURS * 3600

    remaining = GUEST_MAX_QUERIES - usage["count"]
    if remaining <= 0:
        return {"allowed": False, "remaining": 0,
                "message": f"今日查询次数已用完（{GUEST_MAX_QUERIES}次/天），请登录管理员账号或明天再试"}

    return {"allowed": True, "remaining": remaining, "message": ""}


def consume_guest_query(ip: str):
    """消费一次查询次数"""
    _guest_usage[ip]["count"] += 1


# ====== 配置 ======
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY', '')
dashscope.timeout = 30

# ====== 定时任务 ======
scheduler = BackgroundScheduler()


def scheduled_fetch_today_price():
    """定时拉取当天股票行情"""
    logger.info("定时任务开始：拉取当天股票行情")
    try:
        result = sa.fetch_and_save_today_price()
        if result['success']:
            logger.info("定时任务完成：%s", result['message'])
        else:
            logger.warning("定时任务失败：%s", result['message'])
    except Exception as e:
        logger.error("定时任务异常：%s", str(e))


# 每天下午 5 点执行
scheduler.add_job(
    scheduled_fetch_today_price,
    'cron',
    hour=17,
    minute=0,
    id='fetch_today_stock_price',
    replace_existing=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    logger.info("定时任务调度器已启动，每天 17:00 自动拉取股票行情")
    yield
    scheduler.shutdown()
    logger.info("定时任务调度器已关闭")


app = FastAPI(title="个人智能助手 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== 助手注册表 ======
ASSISTANTS = {
    "docs": {
        "id": "docs",
        "name": "企业级多文档智能问答系统",
        "description": "基于 LlamaIndex + LangChain，支持 PDF/Word/TXT 多文档语义检索与智能问答",
        "icon": "📚",
        "suggestions": [
            "雇主责任险的保障范围和理赔流程是什么？",
            "介绍下平安装修保.",
            "平安商业综合责任保险的保障方案有哪些？"
        ],
        "type": "docs",
    },
    "stock": {
        "id": "stock",
        "name": "股票助手",
        "description": "A股市场数据查询与分析，支持个股走势、涨跌榜、行业对比等自然语言问答",
        "icon": "📈",
        "suggestions": sa.STOCK_SUGGESTIONS,
        "system_prompt": sa.STOCK_SYSTEM_PROMPT,
        "tools": ["exc_sql_stock"],   # 使用股票专属工具，连股票库，只允许 SELECT
        "type": "qwen",
    },
}

# 缓存已初始化的 bot 实例
_bots = {}

def get_bot(assistant_id: str):
    if assistant_id not in ASSISTANTS:
        raise HTTPException(status_code=404, detail="助手不存在")
    if assistant_id not in _bots:
        cfg = ASSISTANTS[assistant_id]
        llm_cfg = {
            'model': 'qwen-turbo-latest',
            'timeout': 30,
            'retry_count': 3,
        }
        _bots[assistant_id] = Assistant(
            llm=llm_cfg,
            name=cfg["name"],
            description=cfg["description"],
            system_message=cfg["system_prompt"],
            function_list=cfg["tools"],
        )
    return _bots[assistant_id]

# ====== 数据模型 ======
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    assistant_id: str
    messages: List[Message]

# ====== 路由 ======
@app.get("/api/assistants")
def list_assistants():
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "description": a["description"],
            "icon": a["icon"],
            "suggestions": a.get("suggestions", []),
            "type": a.get("type", "qwen"),
        }
        for a in ASSISTANTS.values()
    ]

def _extract_text(content) -> str:
    """从 qwen-agent 的 content 字段提取纯文本"""
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return content if isinstance(content, str) else ""


@app.post("/api/chat")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None, alias="authorization"),
):
    """
    通用助手流式问答（SSE）：逐步推送思考步骤 + 流式最终答案。
    事件格式：
      {"step": {type, tool, arguments, thinking}}  — 思考/工具调用
      {"step": {type, tool, result}}                — 工具执行结果
      {"delta": "文本片段"}                          — 最终答案（增量）
      {"remaining": N}                              — 剩余查询次数
      [DONE]
    """
    user_msgs = [m for m in req.messages if m.role == "user"]
    if not user_msgs:
        raise HTTPException(status_code=400, detail="缺少用户问题")
    query = user_msgs[-1].content

    is_admin = verify_admin(authorization)

    # 非管理员：字数 + 次数限制
    if not is_admin:
        if len(query) > GUEST_MAX_QUERY_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"问题长度不能超过 {GUEST_MAX_QUERY_LEN} 字（当前 {len(query)} 字），请精简问题后重试",
            )
        ip = get_client_ip(request)
        limit_info = check_guest_limit(ip)
        if not limit_info["allowed"]:
            raise HTTPException(status_code=429, detail=limit_info["message"])
        consume_guest_query(ip)
        remaining = limit_info["remaining"] - 1
    else:
        remaining = -1

    bot = get_bot(req.assistant_id)
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    async def generate():
        loop = asyncio.get_event_loop()
        import queue, threading

        q = queue.Queue()

        def _emit_msg(msg, pending_thinking_ref):
            """处理单条已确认完成的消息，返回更新后的 pending_thinking"""
            role = msg.get("role", "")
            fc = msg.get("function_call")
            content = _extract_text(msg.get("content", ""))
            pt = pending_thinking_ref

            if role == "assistant" and fc:
                try:
                    args = json.loads(fc.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {"raw": fc.get("arguments", "")}
                thinking = (pt + " " + content).strip()
                step = {
                    "type": "function_call",
                    "tool": fc.get("name", ""),
                    "arguments": args,
                }
                if thinking:
                    step["thinking"] = thinking
                q.put(json.dumps({"step": step}, ensure_ascii=False))
                return ""

            elif role == "function":
                q.put(json.dumps({"step": {
                    "type": "function_result",
                    "tool": msg.get("name", ""),
                    "result": content,
                }}, ensure_ascii=False))
                return ""

            elif role == "assistant" and not fc and content.strip():
                return content.strip()

            return pt

        def _run():
            """
            遍历 bot.run() 的增量响应，实时推送步骤和最终答案。

            关键策略：只处理"已确认完成"的消息（后面有新消息跟着的），
            最后一条消息等整个循环结束后再处理，避免读到不完整的
            function_call arguments。
            """
            try:
                processed_up_to = 0   # 已处理到的消息索引
                pending_thinking = "" # 暂存思考文本
                last_response = []

                for response in bot.run(messages):
                    last_response = response
                    # 只处理到 len-1，最后一条可能还在构建中
                    safe_to = max(processed_up_to, len(response) - 1)

                    for i in range(processed_up_to, safe_to):
                        pending_thinking = _emit_msg(
                            response[i], pending_thinking
                        )

                    processed_up_to = safe_to

                # 循环结束，处理剩余未处理的消息（现在一定是完整的）
                for i in range(processed_up_to, len(last_response)):
                    pending_thinking = _emit_msg(
                        last_response[i], pending_thinking
                    )

                # 最终文本作为答案输出
                if pending_thinking:
                    q.put(json.dumps({"delta": pending_thinking},
                                     ensure_ascii=False))

            except Exception as e:
                q.put(json.dumps({"error": str(e)}, ensure_ascii=False))
            finally:
                q.put(None)

        threading.Thread(target=_run, daemon=True).start()

        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            yield f"data: {chunk}\n\n"

        yield f"data: {json.dumps({'remaining': remaining}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ====== 文档助手专属路由 ======

@app.post("/api/docs/chat")
async def docs_chat(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None, alias="authorization"),
):
    """文档问答（流式）：LlamaIndex 检索 + LangChain 流式生成，SSE 推送"""
    if req.assistant_id != "docs":
        raise HTTPException(status_code=400, detail="该接口仅供文档助手使用")

    user_msgs = [m for m in req.messages if m.role == "user"]
    if not user_msgs:
        raise HTTPException(status_code=400, detail="缺少用户问题")
    query = user_msgs[-1].content

    is_admin = verify_admin(authorization)

    # 非管理员：字数限制 + 次数限制
    if not is_admin:
        if len(query) > GUEST_MAX_QUERY_LEN:
            raise HTTPException(
                status_code=400,
                detail=f"问题长度不能超过 {GUEST_MAX_QUERY_LEN} 字（当前 {len(query)} 字），请精简问题后重试",
            )

        ip = get_client_ip(request)
        limit_info = check_guest_limit(ip)
        if not limit_info["allowed"]:
            raise HTTPException(status_code=429, detail=limit_info["message"])

        # 扣减次数
        consume_guest_query(ip)
        remaining = limit_info["remaining"] - 1
    else:
        remaining = -1  # 管理员不限

    async def generate():
        loop = asyncio.get_event_loop()

        import queue, threading

        q = queue.Queue()

        def _run():
            try:
                for chunk in da.answer_with_sources_stream(query):
                    q.put(chunk)
            except Exception as e:
                q.put(json.dumps({"error": str(e)}, ensure_ascii=False))
            finally:
                q.put(None)

        threading.Thread(target=_run, daemon=True).start()

        while True:
            chunk = await loop.run_in_executor(None, q.get)
            if chunk is None:
                break
            yield f"data: {chunk}\n\n"

        # 附带剩余次数信息
        yield f"data: {json.dumps({'remaining': remaining}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/quota")
async def get_quota(
    request: Request,
    authorization: Optional[str] = Header(None, alias="authorization"),
):
    """查询当前用户的剩余查询次数（全局，所有助手共享）"""
    if verify_admin(authorization):
        return {"remaining": -1, "total": -1, "is_admin": True}

    ip = get_client_ip(request)
    info = check_guest_limit(ip)
    return {
        "remaining": info["remaining"],
        "total": GUEST_MAX_QUERIES,
        "is_admin": False,
    }


@app.get("/api/docs/files")
def list_docs_files():
    """列出 docs 目录中的所有文档"""
    return da.list_docs()


@app.post("/api/docs/upload")
async def upload_doc(
    files: List[UploadFile] = File(...),
    authorization: Optional[str] = Header(None, alias="authorization"),
):
    """上传文档到 docs 目录（仅管理员），支持多文件上传（最多10个），自动触发索引重建"""
    if not verify_admin(authorization):
        raise HTTPException(status_code=403, detail="无权限，仅管理员可上传文档")

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="单次最多上传 10 个文件")

    allowed = {'.pdf', '.txt', '.docx', '.md', '.csv'}
    os.makedirs(da.DOCS_DIR, exist_ok=True)

    saved = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {file.filename}（{ext}），支持 {allowed}",
            )
        dest = os.path.join(da.DOCS_DIR, file.filename)
        with open(dest, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        saved.append(file.filename)

    # 重建索引（异步，不阻塞响应）
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, da.rebuild_index)

    names = "、".join(saved)
    return {"message": f"已上传 {len(saved)} 个文件（{names}），索引重建中…"}


@app.delete("/api/docs/files/{filename}")
async def delete_doc(filename: str, authorization: Optional[str] = Header(None, alias="authorization")):
    """删除 docs 目录中的文档（仅管理员），自动触发索引重建"""
    if not verify_admin(authorization):
        raise HTTPException(status_code=403, detail="无权限，仅管理员可删除文档")
    path = os.path.join(da.DOCS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    os.remove(path)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, da.rebuild_index)

    return {"message": f"文件 {filename} 已删除，索引重建中…"}


@app.post("/api/docs/rebuild")
async def rebuild_docs_index():
    """手动触发索引重建"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, da.rebuild_index)
    return {"message": result}



# ====== 管理员登录 ======

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/admin/login")
def admin_login(req: LoginRequest):
    """管理员登录，返回 Basic Auth 凭证"""
    if req.username == ADMIN_USERNAME and req.password == ADMIN_PASSWORD:
        import base64
        token = base64.b64encode(f"{req.username}:{req.password}".encode()).decode()
        return {"success": True, "token": f"Basic {token}"}
    raise HTTPException(status_code=401, detail="用户名或密码错误")


# ====== 股票助手专属路由（需要管理员权限） ======

class FetchPriceRequest(BaseModel):
    trade_date: str  # 格式 YYYYMMDD，如 20260327

@app.post("/api/stock/fetch-names")
async def stock_fetch_names(authorization: Optional[str] = Header(None, alias="authorization")):
    """获取全量股票基本信息并写入数据库（仅管理员）"""
    if not verify_admin(authorization):
        raise HTTPException(status_code=403, detail="无权限，请先登录")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sa.fetch_and_save_stock_names)
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['message'])
    return result

@app.post("/api/stock/fetch-today")
async def stock_fetch_today(authorization: Optional[str] = Header(None, alias="authorization")):
    """获取今日股票行情并写入数据库（仅管理员）"""
    if not verify_admin(authorization):
        raise HTTPException(status_code=403, detail="无权限，请先登录")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sa.fetch_and_save_today_price)
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['message'])
    return result

@app.post("/api/stock/fetch-by-date")
async def stock_fetch_by_date(req: FetchPriceRequest, authorization: Optional[str] = Header(None, alias="authorization")):
    """获取指定日期股票行情并写入数据库（仅管理员）"""
    if not verify_admin(authorization):
        raise HTTPException(status_code=403, detail="无权限，请先登录")
    if not req.trade_date.isdigit() or len(req.trade_date) != 8:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用 YYYYMMDD，如 20260327")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, sa.fetch_and_save_price_by_date, req.trade_date)
    if not result['success']:
        raise HTTPException(status_code=500, detail=result['message'])
    return result


@app.get("/api/health")
def health():
    return {"status": "ok", "api_key_set": bool(dashscope.api_key)}
