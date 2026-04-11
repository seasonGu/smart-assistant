"""
企业级多文档智能问答系统 —— 数据层 + 编排层
LlamaIndex 负责：文档加载、分块、向量索引、语义检索
LangChain  负责：LCEL 问答链、报告生成链
"""

import os
from typing import List, Optional

DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY', '')

# ====== LlamaIndex 全局索引（懒加载，单例） ======
_index = None
_index_loaded = False

DOCS_DIR = os.path.join(os.path.dirname(__file__), 'docs')
STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'docs_storage')

# ====== Milvus Lite 配置 ======
# Milvus Lite 是 Milvus 官方的嵌入式版本，像 SQLite 一样一个本地文件即可运行
# 未来迁移到 Milvus Standalone / Zilliz Cloud 时，只需把 MILVUS_URI 改成服务端点
MILVUS_URI = os.getenv(
    'MILVUS_URI',
    os.path.join(STORAGE_DIR, 'milvus_lite.db'),
)
# Collection 名字里带版本后缀，换 embedding 模型或分块策略时换个名字即可重建
# v2: TEXT_EMBEDDING_V3(1024d) + SentenceSplitter(512/80) + gte-rerank
MILVUS_COLLECTION = os.getenv('MILVUS_COLLECTION', 'smart_assistant_docs_v2')
MILVUS_DIM = 1024  # TEXT_EMBEDDING_V3 向量维度

# ====== RapidOCR 单例（懒加载） ======
_ocr_engine = None


def _get_ocr_engine():
    """获取 RapidOCR 引擎（单例，避免重复加载模型）"""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


# ====== 图片型 PDF 本地 OCR 识别 ======

def _is_image_pdf_page(page) -> bool:
    """判断 PDF 页面是否为图片型（文本极少或为空）"""
    text = page.get_text("text").strip()
    return len(text) < 20


def _ocr_pdf_page(page, page_num: int) -> str:
    """使用 RapidOCR（本地）识别 PDF 页面图片中的文字"""
    import numpy as np
    from PIL import Image
    import io

    # 将 PDF 页面渲染为图片
    pix = page.get_pixmap(dpi=200)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    img_array = np.array(img)

    print(f"  [OCR] 正在识别第 {page_num + 1} 页（图片型）...")

    ocr = _get_ocr_engine()
    result, _ = ocr(img_array)

    if not result:
        return ""

    # result 格式: [[box, text, score], ...]
    lines = [item[1] for item in result]
    return "\n".join(lines)


def _load_pdf_with_ocr(filepath: str) -> List:
    """
    智能加载 PDF：文本型页面直接提取，图片型页面用本地 RapidOCR。
    返回 LlamaIndex Document 列表。
    """
    import fitz  # PyMuPDF
    from llama_index.core import Document

    filename = os.path.basename(filepath)
    doc = fitz.open(filepath)
    documents = []
    has_ocr_pages = False

    for page_num in range(len(doc)):
        page = doc[page_num]

        if _is_image_pdf_page(page):
            has_ocr_pages = True
            text = _ocr_pdf_page(page, page_num)
        else:
            text = page.get_text("text")

        if text.strip():
            documents.append(Document(
                text=text,
                metadata={
                    "file_name": filename,
                    "page_label": str(page_num + 1),
                    "source": filepath,
                },
            ))

    doc.close()

    if has_ocr_pages:
        print(f"  [OCR] {filename} 包含图片型页面，已使用本地 OCR 完成识别")

    return documents


def _load_all_documents() -> List:
    """加载 docs 目录中的所有文档，PDF 使用智能 OCR 加载"""
    from llama_index.core import SimpleDirectoryReader

    pdf_files = []
    non_pdf_files = []

    for f in os.listdir(DOCS_DIR):
        filepath = os.path.join(DOCS_DIR, f)
        if not os.path.isfile(filepath):
            continue
        if f.lower().endswith('.pdf'):
            pdf_files.append(filepath)
        elif f.lower().endswith(('.txt', '.docx', '.md', '.csv')):
            non_pdf_files.append(filepath)

    documents = []

    # PDF 文件：使用自定义 OCR 加载器
    for pdf_path in pdf_files:
        print(f"[DocsAssistant] 加载 PDF: {os.path.basename(pdf_path)}")
        try:
            docs = _load_pdf_with_ocr(pdf_path)
            documents.extend(docs)
            print(f"  -> 提取 {len(docs)} 个页面")
        except Exception as e:
            print(f"  -> 加载失败: {e}")

    # 非 PDF 文件：使用 SimpleDirectoryReader
    if non_pdf_files:
        try:
            reader = SimpleDirectoryReader(input_files=non_pdf_files)
            non_pdf_docs = reader.load_data()
            documents.extend(non_pdf_docs)
            print(f"[DocsAssistant] 加载 {len(non_pdf_files)} 个非 PDF 文档，共 {len(non_pdf_docs)} 个片段")
        except Exception as e:
            print(f"[DocsAssistant] 非 PDF 文档加载失败: {e}")

    return documents


def _setup_llamaindex():
    """配置 LlamaIndex 全局 LLM、Embedding 和分块策略"""
    from llama_index.core import Settings
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.llms.dashscope import DashScope
    from llama_index.embeddings.dashscope import (
        DashScopeEmbedding,
        DashScopeTextEmbeddingModels,
    )

    Settings.llm = DashScope(
        model="deepseek-v3",
        api_key=DASHSCOPE_API_KEY,
        temperature=0.1,
        top_p=0.8,
    )
    # 使用 V3 embedding（中文长文本效果显著优于 V2）
    Settings.embed_model = DashScopeEmbedding(
        model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3,
    )
    # 显式控制分块：512 token 一块，相邻块 80 token 重叠，避免答案被切断
    Settings.node_parser = SentenceSplitter(
        chunk_size=512,
        chunk_overlap=80,
    )


def _get_milvus_vector_store(overwrite: bool = False):
    """构造 MilvusVectorStore（Milvus Lite 模式，本地文件存储）"""
    from llama_index.vector_stores.milvus import MilvusVectorStore

    return MilvusVectorStore(
        uri=MILVUS_URI,
        collection_name=MILVUS_COLLECTION,
        dim=MILVUS_DIM,
        overwrite=overwrite,
        similarity_metric="COSINE",
        # HNSW 索引：中小规模 RAG 的经典选择，召回率高、查询快
        # M=16 控制图的度数、efConstruction=200 控制建图时的搜索宽度
        index_config={
            "index_type": "HNSW",
            "metric_type": "COSINE",
            "params": {"M": 16, "efConstruction": 200},
        },
        search_config={"ef": 64},
    )


def _milvus_has_data() -> bool:
    """检查 Milvus collection 是否已有数据（用于判断是否需要从头构建）"""
    try:
        from pymilvus import MilvusClient

        client = MilvusClient(uri=MILVUS_URI)
        if not client.has_collection(MILVUS_COLLECTION):
            return False
        stats = client.get_collection_stats(MILVUS_COLLECTION)
        row_count = stats.get("row_count", 0) if isinstance(stats, dict) else 0
        return row_count > 0
    except Exception as e:
        print(f"[DocsAssistant] 检查 Milvus collection 失败: {e}")
        return False


def _build_index(force_rebuild: bool = False):
    """构建或加载向量索引（Milvus Lite 后端）"""
    from llama_index.core import VectorStoreIndex, StorageContext

    # 确保 STORAGE_DIR 存在（Milvus Lite 需要一个目录来放 .db 文件）
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # 非强制重建 且 collection 已有数据 → 直接接管现有索引
    if not force_rebuild and _milvus_has_data():
        try:
            vector_store = _get_milvus_vector_store(overwrite=False)
            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
            print(f"[DocsAssistant] 从 Milvus 加载已有索引 (collection={MILVUS_COLLECTION})")
            return index
        except Exception as e:
            print(f"[DocsAssistant] 加载 Milvus 索引失败: {e}，将重新构建")
            force_rebuild = True

    # 从文档目录构建
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        print(f"[DocsAssistant] 已创建 docs 目录: {DOCS_DIR}")
        return None

    files = [f for f in os.listdir(DOCS_DIR)
             if f.lower().endswith(('.pdf', '.txt', '.docx', '.md', '.csv'))]
    if not files:
        print("[DocsAssistant] docs 目录中暂无文档")
        return None

    print(f"[DocsAssistant] 发现 {len(files)} 个文档，正在构建索引...")
    documents = _load_all_documents()
    if not documents:
        print("[DocsAssistant] 未能提取到任何文档内容")
        return None

    # force_rebuild=True 时 overwrite=True，会 drop 掉旧 collection 再重建
    vector_store = _get_milvus_vector_store(overwrite=True)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
    )
    print(
        f"[DocsAssistant] 索引已写入 Milvus "
        f"(uri={MILVUS_URI}, collection={MILVUS_COLLECTION})"
    )
    return index


def get_index(force_rebuild: bool = False):
    """获取全局索引（懒加载）"""
    global _index, _index_loaded
    if not _index_loaded or force_rebuild:
        _setup_llamaindex()
        _index = _build_index(force_rebuild)
        _index_loaded = True
    return _index


def _rerank_with_dashscope(query: str, candidates: List[dict], top_n: int) -> List[dict]:
    """
    用 DashScope gte-rerank 对粗召回结果做精排。
    失败时退化为按原始向量分数取前 top_n（不阻塞主流程）。
    """
    if not candidates:
        return []

    try:
        import dashscope
        from http import HTTPStatus

        resp = dashscope.TextReRank.call(
            model="gte-rerank",
            query=query,
            documents=[c["text"] for c in candidates],
            top_n=top_n,
            return_documents=False,
            api_key=DASHSCOPE_API_KEY,
        )

        if resp.status_code != HTTPStatus.OK:
            print(f"[Rerank] 调用失败 status={resp.status_code} msg={resp.message}，降级使用向量分数")
            return candidates[:top_n]

        results = []
        for item in resp.output.results:
            doc = dict(candidates[item.index])
            doc["rerank_score"] = round(float(item.relevance_score), 4)
            results.append(doc)
        return results
    except Exception as e:
        print(f"[Rerank] 异常 {e}，降级使用向量分数")
        return candidates[:top_n]


def retrieve_docs(
    query: str,
    top_k: int = 5,
    recall_k: int = 30,
    use_rerank: bool = True,
) -> List[dict]:
    """
    两阶段检索：
      1) 向量召回 recall_k 条候选（bi-encoder，快但粗）
      2) gte-rerank 精排取 top_k 条（cross-encoder，慢但准）
    返回 [{"text", "file", "score", "rerank_score"?}, ...]
    """
    index = get_index()
    if index is None:
        return []

    # 阶段 1：向量粗召回
    retriever = index.as_retriever(similarity_top_k=recall_k if use_rerank else top_k)
    nodes = retriever.retrieve(query)

    candidates = []
    for node in nodes:
        candidates.append({
            "text": node.text,
            "file": node.metadata.get("file_name", "未知文档"),
            "score": round(node.score, 4) if node.score else None,
        })

    # 阶段 2：rerank 精排
    if use_rerank:
        return _rerank_with_dashscope(query, candidates, top_n=top_k)
    return candidates[:top_k]


# ====== QA 链单例（避免每次请求重复创建） ======
_qa_chain = None


def get_qa_chain():
    """获取 QA 链（单例）"""
    global _qa_chain
    if _qa_chain is None:
        from langchain_community.chat_models import ChatTongyi
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = ChatTongyi(
            model_name="deepseek-v3",
            dashscope_api_key=DASHSCOPE_API_KEY,
            streaming=True,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个专业的企业文档分析助手。
请根据以下检索到的文档内容，准确、详细地回答用户问题。
如果文档中没有相关信息，请如实说明，不要编造内容。
请用中文回复，语言简洁专业。

检索到的文档内容：
{context}"""),
            ("human", "{question}")
        ])

        _qa_chain = prompt | llm | StrOutputParser()
    return _qa_chain


def answer_with_sources_stream(query: str, history: Optional[List[dict]] = None):
    """
    流式问答流程：检索 → 流式生成
    返回 generator，yield 每个 token；最后 yield sources
    """
    import json

    # 1. LlamaIndex 检索
    docs = retrieve_docs(query, top_k=5)
    if not docs:
        yield json.dumps({"delta": "📂 docs 目录中暂无文档，请先上传文档后再提问。"}, ensure_ascii=False)
        return

    # 2. 拼接上下文
    context = "\n\n".join(
        f"[来源: {d['file']}]\n{d['text']}"
        for d in docs
    )

    # 3. 流式生成
    chain = get_qa_chain()
    for chunk in chain.stream({"context": context, "question": query}):
        if chunk:
            yield json.dumps({"delta": chunk}, ensure_ascii=False)

    # 4. 最后发送来源信息
    yield json.dumps({"sources": docs}, ensure_ascii=False)


def answer_with_sources(query: str, history: Optional[List[dict]] = None):
    """
    非流式问答流程（兼容旧接口）
    返回 (answer: str, sources: List[dict])
    """
    docs = retrieve_docs(query, top_k=5)
    if not docs:
        return "📂 docs 目录中暂无文档，请先上传文档后再提问。", []

    context = "\n\n".join(
        f"[来源: {d['file']}]\n{d['text']}"
        for d in docs
    )

    chain = get_qa_chain()
    answer = chain.invoke({"context": context, "question": query})

    return answer, docs


def list_docs() -> List[dict]:
    """列出 docs 目录中的所有文档"""
    if not os.path.exists(DOCS_DIR):
        return []
    files = []
    for f in os.listdir(DOCS_DIR):
        if f.lower().endswith(('.pdf', '.txt', '.docx', '.md', '.csv')):
            path = os.path.join(DOCS_DIR, f)
            files.append({
                "name": f,
                "size": os.path.getsize(path),
                "modified": os.path.getmtime(path),
            })
    return sorted(files, key=lambda x: x["modified"], reverse=True)


def rebuild_index() -> str:
    """
    强制重建索引（新增文档后调用）。
    Milvus 模式下无需 rmtree 本地目录：_get_milvus_vector_store(overwrite=True)
    会在底层 drop 掉旧 collection 再重建。
    """
    global _index, _index_loaded
    _index_loaded = False
    _index = get_index(force_rebuild=True)
    if _index is None:
        return "docs 目录为空，无法构建索引"
    return f"索引重建成功，共索引 {len(list_docs())} 个文档"
