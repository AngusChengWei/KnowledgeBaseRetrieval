"""
会话管理 + 智能问答 + 文档管理路由 — 系统最核心的业务模块。

核心流程 (/ask):
  1. 用户发送问题 → Query Rewriting 改写优化检索词
  2. 改写后的问题 → DashScope embedding 转换为 1024 维向量
  3. 向量 → ChromaDB 按 org_code+department 检索 top-K 相似文本块
  4. 低于阈值的块被过滤 → 剩余块作为 LLM 的上下文
  5. LLM（DeepSeek/OpenAI）结合历史对话 + 检索上下文生成回答
  6. 回答 + 引用来源存入消息历史

文档管理支持:
  - 文件上传（PDF/DOCX/XLSX/TXT/MD）→ 磁盘存储
  - URL 导入（Playwright 渲染 SPA 页面）→ 提取内容 → 向量化
  - 知识库重建：重新读取所有文档 → 切分 → 向量化 → 替换 ChromaDB 集合
"""

import json
import os
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Query, Body
from typing import List

from models import (
    AskRequest, AskResponse, SourceItem, SessionResponse,
    UploadResponse, RebuildResponse,
)
from auth import get_current_user, require_admin, get_user_accessible_departments
from dependencies import (
    get_effective_org_id, get_effective_org_context,
    validate_department, get_docs_dir,
)

router = APIRouter()


# ============ 会话路由 ============

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: Request,
    department: str = Query(default="general"),
    user: dict = Depends(get_current_user)
):
    """
    创建新会话 — 每个会话绑定一个默认部门，承载多轮对话上下文。

    会话存储在 chat_sessions 表，包含 org_id 用于多租户隔离。
    返回的 session_id（UUID）用于后续 /ask 请求的 session_id 参数。
    """
    from db import get_db
    from session import create_session as create_s
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)
    session_id = create_s(db, user["user_id"], department, org_id=effective_org_id)
    return SessionResponse(session_id=session_id)


@router.get("/sessions")
async def list_sessions(request: Request, user: dict = Depends(get_current_user)):
    """
    列出当前用户的会话列表。

    普通用户只能看到自己的会话，超管可查看当前组织下所有用户会话。
    按 updated_at 降序排列，最近活跃的会话在前。
    """
    from db import get_db
    from session import list_user_sessions
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)
    sessions = list_user_sessions(db, user["user_id"], org_id=effective_org_id)
    return {"sessions": sessions}


@router.post("/sessions/{session_id}")
async def manage_session(
    session_id: str,
    action: str = Query(...),
    body: dict = Body(None),
    user: dict = Depends(get_current_user)
):
    """
    会话操作（统一入口，通过 action 参数区分）。

    支持的操作:
      - delete: 软删除会话（is_deleted=1），消息历史保留用于审计
      - rename: 修改会话标题（限制 50 字），前端显示用
    """
    from db import get_db

    if action == "delete":
        from session import delete_session as delete_s
        db = get_db()
        if not delete_s(db, session_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="会话不存在或无权操作")
        return {"status": "success", "message": "会话已删除"}

    elif action == "rename":
        from session import rename_session
        title = (body or {}).get("title", "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        if len(title) > 50:
            raise HTTPException(status_code=400, detail="标题不能超过50字")
        db = get_db()
        if not rename_session(db, session_id, user["user_id"], title):
            raise HTTPException(status_code=404, detail="会话不存在或无权操作")
        return {"status": "success", "message": "重命名成功"}

    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user: dict = Depends(get_current_user)):
    """
    获取指定会话的完整消息历史。

    安全校验:
      1. 会话必须存在（404）
      2. 当前用户必须是会话所有者（403），防止越权查看他人对话

    返回的 sources 字段从 JSON 字符串解析为对象数组。
    """
    from db import get_db
    from session import get_session_messages as get_msgs, get_session_owner
    db = get_db()
    owner = get_session_owner(session_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if owner != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    messages = get_msgs(db, session_id)
    for msg in messages:
        if msg["sources"]:
            try:
                msg["sources"] = json.loads(msg["sources"])
            except (json.JSONDecodeError, TypeError):
                msg["sources"] = []
        else:
            msg["sources"] = []
    return {"messages": messages, "session_id": session_id}


# ============ 问答路由 ============

@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest, raw_request: Request, user: dict = Depends(get_current_user)):
    """
    智能问答核心接口 — 完整的 RAG（检索增强生成）流程。

    处理步骤:
      1. Query Rewriting — LLM 改写用户问题，优化检索效果
      2. Embedding — 将改写后的问题转为 1024 维向量
      3. 向量检索 — ChromaDB 按余弦相似度查找最相关的文本块
      4. 相似度过滤 — 低于 SIMILARITY_THRESHOLD 的结果被丢弃
      5. 历史对话 — 加载当前会话的历史消息作为 LLM 上下文
      6. LLM 生成 — 将检索上下文 + 历史 + 问题发给 DeepSeek 生成回答
      7. 保存消息 — 用户问题和 AI 回答（含引用来源）存入 chat_messages

    无相关检索结果时：LLM 以通用助手身份友好回复（如"知识库中暂无相关信息"）。
    """
    from db import get_db
    from session import get_history, add_message, get_session_owner, update_session_department
    from embedding import get_embedding
    from vector_store import search_similar
    from llm import generate_answer, rewrite_query
    from audit import log_action
    import config

    # 多租户隔离：解析当前有效的组织 ID 和 code
    effective_org_id, org_code = get_effective_org_context(user, raw_request)
    validate_department(request.department, effective_org_id)

    # 权限校验：用户只能在自己被分配的部门知识库中检索
    accessible = get_user_accessible_departments(user)
    if request.department not in accessible:
        raise HTTPException(status_code=403, detail="无权访问该部门知识库")

    # 会话归属校验：防止用户通过别人的 session_id 越权
    owner = get_session_owner(request.session_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")
    if owner != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此会话")

    db = get_db()

    # 更新会话的活跃部门（用户可能在对话中切换部门检索）
    update_session_department(db, request.session_id, request.department)

    # 步骤 1: Query Rewriting — LLM 改写用户问题，提取关键检索词
    rewritten_question = await rewrite_query(request.question)

    # 步骤 2: 向量化 — DashScope text-embedding-v3 → 1024 维向量
    question_embedding = await get_embedding(rewritten_question)

    # 步骤 3: 向量检索 — ChromaDB 余弦相似度搜索，返回 top-K
    results = search_similar(question_embedding, top_k=config.TOP_K, department=request.department, org_code=org_code)

    for i, r in enumerate(results):
        print(f"[检索] Top{i+1}: similarity={r['similarity']:.4f}, source={r.get('metadata', {}).get('filename', 'unknown')}")
        print(f"       内容片段: {r['text'][:80]}...")

    # 步骤 4: 相似度过滤 — 低于阈值的检索结果视为不相关，避免 LLM 被噪音干扰
    filtered_results = [
        r for r in results
        if r["similarity"] >= config.SIMILARITY_THRESHOLD
    ]
    print(f"[检索] 阈值={config.SIMILARITY_THRESHOLD}, 过滤后保留 {len(filtered_results)}/{len(results)} 条")

    # 保存用户消息到数据库
    add_message(db, request.session_id, "user", request.question)

    # 步骤 5: 加载历史对话（用于多轮对话上下文）
    history = get_history(request.session_id)

    # 步骤 6: 无相关检索结果 → LLM 通用模式回复
    if not filtered_results:
        answer = await generate_answer(
            question=request.question,
            context_chunks=[],
            history=history
        )
        add_message(db, request.session_id, "assistant", answer)
        return AskResponse(answer=answer, sources=[], session_id=request.session_id)

    # 步骤 7: 有检索结果 → 带知识库上下文调用 LLM 生成回答
    context_chunks = [r["text"] for r in filtered_results]
    answer = await generate_answer(
        question=request.question,
        context_chunks=context_chunks,
        history=history
    )

    # 步骤 8: 构造引用来源（取每个匹配块的前 200 字作为摘要）
    sources = [
        SourceItem(filename=r["metadata"].get("filename", "未知"), chunk=r["text"][:200])
        for r in filtered_results
    ]

    # 步骤 9: 保存 AI 回复（含 sources JSON，用于前端展示引用）
    sources_json = json.dumps([s.model_dump() for s in sources], ensure_ascii=False)
    add_message(db, request.session_id, "assistant", answer, sources=sources_json)

    # 步骤 10: 记录审计日志
    log_action(user["user_id"], "ask_question", "ai",
               f"部门={request.department}, 问题={request.question[:50]}")

    return AskResponse(answer=answer, sources=sources, session_id=request.session_id)


# ============ 文档管理路由 ============

@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    上传知识库文档到指定部门（需管理员权限）。

    文件处理:
      - 支持格式: PDF, DOCX, DOC, TXT, MD, XLSX, XLS
      - 大小限制: MAX_UPLOAD_SIZE_MB（默认 50MB）
      - 存储路径: {KNOWLEDGE_DOCS_DIR}/{org_code}/{department}/{filename}
      - 按组织隔离，不同组织的文件存储在不同目录

    上传后需要调用 /rebuild 将文档内容向量化才能被检索到。
    """
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    accessible = get_user_accessible_departments(user)
    if department not in accessible:
        raise HTTPException(status_code=403, detail="无权操作该部门知识库")

    docs_dir = get_docs_dir(department, org_code)
    docs_dir.mkdir(parents=True, exist_ok=True)

    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls"}
    max_size = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    uploaded = []
    failed = []

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in supported_extensions:
            failed.append(f"{file.filename} (不支持的格式)")
            continue

        try:
            content = await file.read()
            if len(content) > max_size:
                failed.append(f"{file.filename} (文件超过{config.MAX_UPLOAD_SIZE_MB}MB限制)")
                continue
            file_path = docs_dir / file.filename
            with open(file_path, "wb") as f:
                f.write(content)
            uploaded.append(file.filename)
        except Exception as e:
            failed.append(f"{file.filename} ({str(e)})")

    if uploaded:
        log_action(user["user_id"], "upload_document", "knowledge",
                   f"部门={department}, 文件={','.join(uploaded)}")

    return UploadResponse(
        status="success" if uploaded else "failed",
        uploaded_files=uploaded,
        failed_files=failed
    )


@router.get("/documents")
async def list_documents(
    request: Request,
    department: str = Query(default="general"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(require_admin)
):
    """
    列出指定部门知识库中的文档，支持分页。

    返回两类文档:
      - file: 上传到磁盘的物理文件（PDF/DOCX 等）
      - url: 通过 URL 导入的网页内容（向量存储在 ChromaDB 中）

    分页参数: page（页码，从 1 开始）, page_size（每页条数，默认 50，最大 200）
    """
    from vector_store import list_url_documents

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    docs_dir = get_docs_dir(department, org_code)
    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls"}
    documents = []
    if docs_dir.exists():
        for f in docs_dir.iterdir():
            if f.is_file() and f.suffix.lower() in supported_extensions:
                documents.append({
                    "filename": f.name,
                    "size": f.stat().st_size,
                    "source_type": "file"
                })

    # URL 导入的文档存储在 ChromaDB 向量元数据中，不在磁盘上
    url_docs = list_url_documents(department=department, org_code=org_code)
    for ud in url_docs:
        documents.append({
            "filename": ud["filename"],
            "display_title": ud["display_title"],
            "source_ref": ud["source_ref"],
            "source_type": "url",
            "size": ud["chunk_count"]
        })

    # 内存分页（两类文档合并后在内存中切片）
    total = len(documents)
    start = (page - 1) * page_size
    end = start + page_size
    return {"documents": documents[start:end], "total": total, "page": page, "page_size": page_size}


@router.post("/documents/{filename}")
async def manage_document(
    filename: str,
    action: str = Query(...),
    department: str = Query(default="general"),
    request: Request = None,
    user: dict = Depends(require_admin)
):
    """
    文档操作 — 目前仅支持删除。

    删除流程:
      1. 校验操作权限（管理员 + 部门归属）
      2. 删除磁盘上的物理文件
      3. 删除 ChromaDB 中该文件的所有向量数据（容错：文件删除成功即使向量删除失败）
      4. 记录审计日志
    """
    if action == "delete":
        from audit import log_action

        effective_org_id, org_code = get_effective_org_context(user, request)
        validate_department(department, effective_org_id)

        accessible = get_user_accessible_departments(user)
        if department not in accessible:
            raise HTTPException(status_code=403, detail="无权操作该部门知识库")

        file_path = get_docs_dir(department, org_code) / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        os.remove(file_path)

        # 清理向量数据：即使失败也不影响文件删除的主流程
        try:
            from vector_store import delete_document_chunks
            delete_document_chunks(filename, department=department, org_code=org_code)
        except Exception:
            pass

        log_action(user["user_id"], "delete_document", "knowledge",
                   f"部门={department}, 文件={filename}")
        return {"status": "success", "message": f"已删除 {filename}"}
    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild_knowledge_base(
    request: Request,
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    重建指定部门的知识库向量索引。

    完整流程:
      1. 提取当前集合中的 URL 向量数据（临时保存，避免丢失）
      2. 加载文档目录下所有文件 → document_loader 解析文本内容
      3. 文本切分 → text_splitter 按 CHUNK_SIZE/CHUNK_OVERLAP 滑动窗口切块
      4. 批量向量化 → DashScope embedding API（每批最多 10 条）
      5. 重建 ChromaDB 集合 → 先建临时集合，成功后替换旧集合（防数据丢失）
      6. 恢复 URL 向量数据

    注意: 这是一个全量重建操作，会重新处理所有文档，大知识库可能耗时较长。
    """
    from document_loader import load_documents
    from text_splitter import split_documents
    from embedding import get_embeddings_batch
    from vector_store import rebuild_collection, extract_url_chunks, add_chunks
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    # 提取并暂存 URL 向量（避免重建时丢失网页导入的内容）
    url_chunks = extract_url_chunks(department=department, org_code=org_code)
    if url_chunks:
        print(f"[重建] 已保存 {len(url_chunks)} 条 URL 向量，重建后将恢复")

    docs_dir = str(get_docs_dir(department, org_code))
    documents = load_documents(docs_dir)
    if not documents and not url_chunks:
        raise HTTPException(status_code=400, detail="文档目录为空，请先添加文档")

    # 文档 → 文本块
    chunks = split_documents(documents, config.CHUNK_SIZE, config.CHUNK_OVERLAP) if documents else []

    # 文本块 → 向量（批量调用 embedding API）
    texts = [chunk["text"] for chunk in chunks]
    embeddings = await get_embeddings_batch(texts) if texts else []

    metadatas = [chunk["metadata"] for chunk in chunks]

    # 先建临时集合 → 成功后替换旧集合（防止中途失败导致数据丢失）
    rebuild_collection(texts, embeddings, metadatas, department=department, org_code=org_code)

    # 恢复 URL 向量到新集合
    url_count = 0
    if url_chunks:
        url_count = add_chunks(url_chunks, department=department, org_code=org_code)

    total_count = len(chunks) + url_count
    log_action(user["user_id"], "rebuild_knowledge_base", "knowledge",
               f"部门={department}, 文档数={len(documents)}, URL条目={len(url_chunks)}, 分块总数={total_count}")

    return RebuildResponse(
        status="success",
        doc_count=len(documents),
        chunk_count=total_count
    )


@router.post("/rebuild-file")
async def rebuild_file_vectors(
    request: Request,
    filename: str = Query(...),
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    重建单个文件的向量（增量更新，不影响其他文档）。

    与 /rebuild（全量）的区别:
      - /rebuild 删除整个集合重建，所有文档一起处理
      - /rebuild-file 仅更新指定文件的向量，其他文档的向量保持不变

    适用于: 修改了单个文件后，只重建该文件的向量而无需全量重建。
    """
    from document_loader import load_single_document
    from text_splitter import split_documents
    from embedding import get_embeddings_batch
    from vector_store import upsert_document_chunks
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    file_path = get_docs_dir(department, org_code) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    doc = load_single_document(file_path)
    if not doc:
        raise HTTPException(status_code=400, detail="文件内容为空或解析失败")

    chunks = split_documents([doc], config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    texts = [c["text"] for c in chunks]
    embeddings = await get_embeddings_batch(texts)
    metadatas = [c["metadata"] for c in chunks]

    # upsert = update + insert：先删除该文件旧向量，再写入新向量
    count = upsert_document_chunks(
        texts, embeddings, metadatas, filename,
        department=department, org_code=org_code
    )
    log_action(user["user_id"], "rebuild_file_vectors", "knowledge",
               f"部门={department}, 文件={filename}, 分块数={count}")
    return {"status": "success", "chunk_count": count}


@router.post("/vectors")
async def manage_file_vectors(
    action: str = Query(...),
    filename: str = Query(...),
    department: str = Query(default="general"),
    request: Request = None,
    user: dict = Depends(require_admin)
):
    """
    向量数据管理 — 目前仅支持删除。

    删除文件的向量数据但不删除原始文件。
    适用于: 文件内容有问题需要从检索结果中移除，但保留源文件用于后续修正。
    """
    if action == "delete":
        from vector_store import delete_document_chunks
        from audit import log_action

        effective_org_id, org_code = get_effective_org_context(user, request)
        validate_department(department, effective_org_id)

        delete_document_chunks(filename, department=department, org_code=org_code)
        log_action(user["user_id"], "delete_file_vectors", "knowledge",
                   f"部门={department}, 文件={filename}")
        return {"status": "success"}
    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@router.post("/import-url")
async def import_url(
    request: Request,
    url: str = Query(...),
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    通过 URL 导入网页内容到知识库（增量写入，不影响其他文档）。

    工作流程:
      1. url_loader 使用 Playwright 无头浏览器渲染页面（支持 SPA）
      2. 提取页面正文内容（去除导航、页脚等噪音）
      3. 文本切分 → 向量化 → 写入 ChromaDB（标记 source_type="url"）

    增量操作: 仅添加新向量，不删除或影响已有文档的向量。
    """
    from url_loader import load_url_document
    from text_splitter import split_documents
    from embedding import get_embeddings_batch
    from vector_store import upsert_document_chunks
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    try:
        doc = await load_url_document(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"[URL加载] 网页抓取异常 [{error_type}]: {error_msg}")
        raise HTTPException(status_code=502, detail=f"网页抓取失败 [{error_type}]: {error_msg}")

    chunks = split_documents(
        [{"filename": doc["filename"], "content": doc["content"]}],
        config.CHUNK_SIZE,
        config.CHUNK_OVERLAP
    )

    # 为 URL 导入的块打上特殊标记，便于前端区分和后续管理
    for chunk in chunks:
        chunk["metadata"]["source_type"] = "url"
        chunk["metadata"]["source_ref"] = doc["source_ref"]
        chunk["metadata"]["display_title"] = doc["display_title"]

    texts = [c["text"] for c in chunks]
    embeddings = await get_embeddings_batch(texts)
    metadatas = [c["metadata"] for c in chunks]

    count = upsert_document_chunks(
        texts, embeddings, metadatas,
        filename=doc["filename"],
        department=department,
        org_code=org_code
    )

    log_action(
        user["user_id"], "import_url", "knowledge",
        f"部门={department}, URL={url[:200]}, 标题={doc['display_title']}, 分块数={count}"
    )

    return {
        "status": "success",
        "title": doc["display_title"],
        "source_url": doc["source_ref"],
        "chunk_count": count
    }


@router.get("/document-content")
async def get_doc_content(
    request: Request,
    filename: str = Query(...),
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    获取指定文档在向量库中的完整文本内容。

    用于预览 URL 导入的网页提取结果，或检查文件被切分后的实际内容。
    从 ChromaDB 中按 filename 查询所有 chunk，拼成完整文本返回。
    """
    from vector_store import get_document_content

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    chunks = get_document_content(filename, department=department, org_code=org_code)
    if not chunks:
        raise HTTPException(status_code=404, detail="未找到该文档的向量数据")

    full_text = "\n\n".join(c["text"] for c in chunks)
    meta = chunks[0]["metadata"] if chunks else {}

    return {
        "filename": filename,
        "display_title": meta.get("display_title", ""),
        "source_type": meta.get("source_type", "file"),
        "source_ref": meta.get("source_ref", ""),
        "chunk_count": len(chunks),
        "content": full_text
    }


@router.patch("/document-title")
async def update_doc_title(
    request: Request,
    filename: str = Query(...),
    title: str = Query(...),
    department: str = Query(default="general"),
    user: dict = Depends(require_admin)
):
    """
    修改文档的显示标题。

    仅更新 ChromaDB 向量元数据中的 display_title 字段，
    不修改磁盘上的原始文件。
    适用于 URL 导入的文档重命名。
    """
    from vector_store import update_document_title

    if not title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")

    effective_org_id, org_code = get_effective_org_context(user, request)
    validate_department(department, effective_org_id)

    count = update_document_title(
        filename, title.strip(),
        department=department, org_code=org_code
    )
    if count == 0:
        raise HTTPException(status_code=404, detail="未找到该文档")

    return {"status": "success", "updated_chunks": count, "new_title": title.strip()}
