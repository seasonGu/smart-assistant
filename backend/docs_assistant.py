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
    """配置 LlamaIndex 全局 LLM 和 Embedding"""
    from llama_index.core import Settings
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
    Settings.embed_model = DashScopeEmbedding(
        model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V2,
    )


def _build_index(force_rebuild: bool = False):
    """构建或加载向量索引"""
    from llama_index.core import (
        VectorStoreIndex,
        StorageContext,
        load_index_from_storage,
    )

    # 尝试从磁盘加载
    if not force_rebuild and os.path.exists(STORAGE_DIR):
        try:
            storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
            index = load_index_from_storage(storage_context)
            print("[DocsAssistant] 从本地存储加载索引成功")
            return index
        except Exception as e:
            print(f"[DocsAssistant] 加载索引失败: {e}，将重新构建")

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
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=STORAGE_DIR)
    print(f"[DocsAssistant] 索引已保存到 {STORAGE_DIR}")
    return index


def get_index(force_rebuild: bool = False):
    """获取全局索引（懒加载）"""
    global _index, _index_loaded
    if not _index_loaded or force_rebuild:
        _setup_llamaindex()
        _index = _build_index(force_rebuild)
        _index_loaded = True
    return _index


def retrieve_docs(query: str, top_k: int = 5) -> List[dict]:
    """用 LlamaIndex 检索相关文档片段，返回 [{"text": ..., "file": ..., "score": ...}]"""
    from langchain_core.documents import Document as LCDocument

    index = get_index()
    if index is None:
        return []

    retriever = index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)

    results = []
    for node in nodes:
        results.append({
            "text": node.text,
            "file": node.metadata.get("file_name", "未知文档"),
            "score": round(node.score, 4) if node.score else None,
        })
    return results


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
    """强制重建索引（新增文档后调用）"""
    global _index, _index_loaded
    _index_loaded = False
    import shutil
    if os.path.exists(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    _index = get_index(force_rebuild=True)
    if _index is None:
        return "docs 目录为空，无法构建索引"
    return f"索引重建成功，共索引 {len(list_docs())} 个文档"
