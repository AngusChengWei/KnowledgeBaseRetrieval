"""
向量存储模块 — 封装 ChromaDB 操作，支持多组织+多部门集合隔离。

集合命名规则:
  {CHROMA_COLLECTION_NAME}_{org_code}_{department}
  例如: "kb_default_general", "kb_acme_hr"

  这样每个组织的每个部门有独立的向量集合，实现数据隔离。

ChromaDB 配置:
  - 持久化存储: PersistentClient，数据保存在 CHROMA_PERSIST_DIR
  - 距离度量: hnsw:space = cosine（余弦距离）
  - 索引算法: HNSW（分层可导航小世界图），适合高维向量近似最近邻搜索

核心操作:
  - rebuild_collection: 全量重建（先建临时集合，成功后替换）
  - upsert_document_chunks: 增量更新（先删后写单文件向量）
  - search_similar: 单部门检索（余弦相似度 = 1 - 余弦距离）
  - search_similar_multi: 多部门检索（跨部门去重合并）

URL 文档:
  - URL 导入的网页内容也存储在 ChromaDB 中（source_type="url"）
  - 重建时需要先提取 URL 向量暂存，重建后恢复
  - extract_url_chunks / add_chunks 专门处理此场景
"""

from typing import List, Dict

import chromadb

import config

# ChromaDB 持久化客户端 — 数据存储在磁盘上，进程重启后不丢失
_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)


def _get_collection_name(department: str, org_code: str = "default") -> str:
    """
    生成 ChromaDB 集合名称。

    命名格式: {前缀}_{org_code}_{department}
    例如: kb_default_hr → 默认组织人事部的向量集合
    """
    return f"{config.CHROMA_COLLECTION_NAME}_{org_code}_{department}"


def _get_collection(department: str = "general", org_code: str = "default"):
    """
    获取或创建指定组织+部门的 ChromaDB 集合。

    使用 get_or_create_collection 确保集合一定存在。
    距离度量使用 cosine（余弦距离），检索时 similarity = 1 - distance。
    """
    collection_name = _get_collection_name(department, org_code)
    return _client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )


def rebuild_collection(
    texts: List[str],
    embeddings: List[List[float]],
    metadatas: List[Dict],
    department: str = "general",
    org_code: str = "default"
) -> None:
    """
    全量重建向量集合 — 用于知识库重建操作。

    安全策略（防止数据丢失）:
      1. 先创建临时集合 {name}_new
      2. 将所有向量写入临时集合
      3. 删除旧集合
      4. 将数据从临时集合复制到正式集合
      5. 删除临时集合

    如果在新集合构建过程中失败，旧集合仍然完好。
    比"先删后建"模式更安全。

    批量写入: 每批 5000 条，避免单次写入数据量过大。
    """
    collection_name = _get_collection_name(department, org_code)
    tmp_name = f"{collection_name}_new"

    # 清理可能残留的临时集合（上次重建异常中断）
    try:
        _client.delete_collection(tmp_name)
    except Exception:
        pass

    # 步骤 1: 创建临时集合并写入数据
    collection = _client.create_collection(
        name=tmp_name,
        metadata={"hnsw:space": "cosine"}
    )

    ids = [f"chunk_{i}" for i in range(len(texts))]

    batch_size = 5000
    for i in range(0, len(texts), batch_size):
        end = min(i + batch_size, len(texts))
        collection.add(
            ids=ids[i:end],
            documents=texts[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end]
        )

    # 步骤 2: 删除旧集合，将数据写入正式集合
    try:
        _client.delete_collection(collection_name)
    except Exception:
        pass

    # ChromaDB 不支持 rename，通过重新创建正式集合并复制数据来实现
    final_collection = _client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    for i in range(0, len(texts), batch_size):
        end = min(i + batch_size, len(texts))
        final_collection.add(
            ids=ids[i:end],
            documents=texts[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end]
        )

    # 步骤 3: 清理临时集合
    try:
        _client.delete_collection(tmp_name)
    except Exception:
        pass

    print(f"[向量库] 重建完成: {collection_name}，共 {len(texts)} 条向量")


def upsert_document_chunks(
    texts: List[str],
    embeddings: List[List[float]],
    metadatas: List[Dict],
    filename: str,
    department: str = "general",
    org_code: str = "default"
) -> int:
    """
    增量更新单个文件的向量 — upsert = update + insert。

    流程:
      1. 按 filename 删除旧向量（where={"filename": filename}）
      2. 写入新向量

    ID 格式: {filename_md5[:8]}_chunk_{i}
    与全量重建的 "chunk_{i}" 格式不同，避免 ID 冲突。

    适用于: 单文件内容修改后重新向量化，或 URL 导入新内容。
    """
    import hashlib
    collection = _get_collection(department, org_code)

    # 先删除该文件的旧向量
    try:
        collection.delete(where={"filename": filename})
    except Exception:
        pass

    # 生成稳定唯一 ID: 文件名 MD5 前 8 位 + chunk 序号
    fhash = hashlib.md5(filename.encode()).hexdigest()[:8]
    ids = [f"{fhash}_chunk_{i}" for i in range(len(texts))]

    batch_size = 5000
    for i in range(0, len(texts), batch_size):
        end = min(i + batch_size, len(texts))
        collection.add(
            ids=ids[i:end],
            documents=texts[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end]
        )

    print(f"[向量库] 增量更新: {filename} -> {len(texts)} 条")
    return len(texts)


def delete_document_chunks(
    filename: str,
    department: str = "general",
    org_code: str = "default"
) -> None:
    """
    删除指定文件在向量库中的所有 chunk。

    通过 ChromaDB 的 where 过滤实现，不影响集合内其他文档的向量。
    适用于: 删除知识库文档时同步清理对应的向量数据。
    """
    collection = _get_collection(department, org_code)
    try:
        collection.delete(where={"filename": filename})
        print(f"[向量库] 已移除向量: {filename}")
    except Exception as e:
        print(f"[向量库] 移除向量失败: {e}")


def search_similar(
    query_embedding: List[float],
    top_k: int = 3,
    department: str = "general",
    org_code: str = "default"
) -> List[Dict]:
    """
    在指定组织+部门的向量集合中检索最相似的文本块。

    参数:
        query_embedding: 查询向量（1024 维）
        top_k: 返回 top-K 个最相似的结果
        department: 目标部门
        org_code: 目标组织代码

    返回:
        [{text, metadata, similarity}, ...]
        similarity = 1 - cosine_distance，值越大越相关

    ChromaDB 使用余弦距离（cosine distance），范围 [0, 2]。
    转换为相似度: similarity = 1 - distance，范围 [-1, 1]。
    通常有效结果在 0.5 ~ 1.0 之间。
    """
    collection = _get_collection(department, org_code)

    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    # 余弦距离 → 余弦相似度
    items = []
    if results["documents"] and results["documents"][0]:
        for i in range(len(results["documents"][0])):
            similarity = 1 - results["distances"][0][i]
            items.append({
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "similarity": similarity
            })

    return items


def search_similar_multi(
    query_embedding: List[float],
    top_k_per_dept: int = 3,
    departments: list = None,
    org_code: str = "default"
) -> List[Dict]:
    """
    跨多个部门检索最相似的文本块。

    使用场景:
      - 用户选择了多个部门的知识库进行检索
      - 文件分析时需要综合多个部门的知识库

    去重策略: 以 text 前 100 字符为 key，相同内容的块保留相似度最高的。
    结果按相似度降序排列。
    """
    if not departments:
        departments = ["general"]

    all_items = {}
    for dept in departments:
        try:
            items = search_similar(
                query_embedding,
                top_k=top_k_per_dept,
                department=dept,
                org_code=org_code
            )
            for item in items:
                item["department"] = dept
                # 按 text 前 100 字符去重：相同内容取最高相似度
                key = item["text"][:100]
                if key not in all_items or item["similarity"] > all_items[key]["similarity"]:
                    all_items[key] = item
        except Exception as e:
            print(f"[向量检索] 部门 {dept} 检索失败: {e}")
            continue

    return sorted(all_items.values(), key=lambda x: x["similarity"], reverse=True)


def list_url_documents(
    department: str = "general",
    org_code: str = "default"
) -> List[Dict]:
    """
    获取指定集合中所有 URL 导入的文档列表（去重汇总）。

    通过 ChromaDB 的 where 过滤 source_type="url" 的向量，
    然后按 filename 分组统计 chunk_count。

    返回:
        [{filename, display_title, source_ref, source_type, chunk_count}, ...]

    用于知识库文档列表页面展示 URL 导入的网页内容。
    """
    collection = _get_collection(department, org_code)
    if collection.count() == 0:
        return []

    try:
        results = collection.get(
            where={"source_type": "url"},
            include=["metadatas"]
        )
    except Exception:
        return []

    if not results or not results.get("metadatas"):
        return []

    # 按 filename 去重汇总
    url_docs = {}
    for meta in results["metadatas"]:
        key = meta.get("filename", "")
        if not key:
            continue
        if key not in url_docs:
            url_docs[key] = {
                "filename": key,
                "display_title": meta.get("display_title", key),
                "source_ref": meta.get("source_ref", key),
                "source_type": "url",
                "chunk_count": 0
            }
        url_docs[key]["chunk_count"] += 1

    return list(url_docs.values())


def extract_url_chunks(
    department: str = "general",
    org_code: str = "default"
) -> List[Dict]:
    """
    提取集合中所有 URL 条目的完整数据（含向量和元数据）。

    用于知识库重建时的 URL 数据保全:
      1. 重建前调用此函数，提取所有 URL 向量暂存
      2. 全量重建文档向量
      3. 调用 add_chunks 将暂存的 URL 向量恢复到新集合

    安全检查: 过滤掉 embedding=None 的 chunk（ChromaDB 某些配置下不返回向量数据）。
    """
    collection = _get_collection(department, org_code)
    if collection.count() == 0:
        return []
    try:
        results = collection.get(
            where={"source_type": "url"},
            include=["documents", "embeddings", "metadatas"]
        )
    except Exception:
        return []
    if not results or not results.get("documents"):
        return []
    chunks = []
    for i in range(len(results["documents"])):
        embedding = results["embeddings"][i] if results.get("embeddings") is not None else None
        if embedding is None:
            print(f"[向量库] 警告: URL chunk 缺少 embedding，已跳过 (filename={results['metadatas'][i].get('filename', 'unknown')})")
            continue
        chunks.append({
            "text": results["documents"][i],
            "embedding": embedding,
            "metadata": results["metadatas"][i] if results.get("metadatas") is not None else {}
        })
    return chunks


def add_chunks(
    chunks: List[Dict],
    department: str = "general",
    org_code: str = "default"
) -> int:
    """
    批量添加预先计算好的向量块到集合中。

    用于重建知识库后恢复 URL 向量数据。
    chunks 格式: [{"text": str, "embedding": [...], "metadata": {...}}, ...]

    ID 格式: {filename_md5[:8]}_restore_{i}，避免与全量重建的 ID 冲突。
    """
    if not chunks:
        return 0
    collection = _get_collection(department, org_code)
    import hashlib
    ids = []
    texts = []
    embeddings = []
    metadatas = []
    for i, c in enumerate(chunks):
        key = c["metadata"].get("filename", f"url_{i}")
        fhash = hashlib.md5(key.encode()).hexdigest()[:8]
        ids.append(f"{fhash}_restore_{i}")
        texts.append(c["text"])
        embeddings.append(c["embedding"])
        metadatas.append(c["metadata"])

    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        collection.add(
            ids=ids[i:end],
            documents=texts[i:end],
            embeddings=embeddings[i:end],
            metadatas=metadatas[i:end]
        )
    print(f"[向量库] 恢复 URL 向量: {len(chunks)} 条")
    return len(chunks)


def get_document_content(
    filename: str,
    department: str = "general",
    org_code: str = "default"
) -> List[Dict]:
    """
    获取指定文档的所有向量块内容（按 chunk_index 排序拼接还原）。

    用于预览 URL 导入的网页提取结果，或检查文件被切分后的实际内容。
    从 ChromaDB 中按 filename 过滤查询，按 chunk_index 排序。
    """
    collection = _get_collection(department, org_code)
    if collection.count() == 0:
        return []

    try:
        results = collection.get(
            where={"filename": filename},
            include=["documents", "metadatas"]
        )
    except Exception:
        return []

    if not results or not results.get("documents"):
        return []

    chunks = []
    for i, doc in enumerate(results["documents"]):
        meta = results["metadatas"][i] if results.get("metadatas") else {}
        chunks.append({"text": doc, "metadata": meta})

    # 按 chunk_index 排序，还原文档原始顺序
    chunks.sort(key=lambda x: x["metadata"].get("chunk_index", 0))
    return chunks


def update_document_title(
    filename: str,
    new_title: str,
    department: str = "general",
    org_code: str = "default"
) -> int:
    """
    更新指定文档所有 chunk 的 display_title 元数据。

    用于重命名 URL 导入的文档显示标题。
    通过 ChromaDB 的 collection.update() 批量更新元数据。

    返回: 更新的 chunk 数量（0 表示未找到该文档）。
    """
    collection = _get_collection(department, org_code)
    if collection.count() == 0:
        return 0

    try:
        results = collection.get(
            where={"filename": filename},
            include=["metadatas"]
        )
    except Exception:
        return 0

    if not results or not results.get("ids"):
        return 0

    ids = results["ids"]
    metadatas = results["metadatas"]

    # 更新每个 chunk 的 display_title
    updated_metadatas = []
    for meta in metadatas:
        meta["display_title"] = new_title
        updated_metadatas.append(meta)

    collection.update(ids=ids, metadatas=updated_metadatas)
    return len(ids)
