"""
Embedding 模块 — 封装阿里云 DashScope 通用文本向量 API。

技术细节:
  - 模型: text-embedding-v3（DashScope 最新通用向量模型）
  - 向量维度: 1024 维
  - 批量限制: 单次 API 调用最多 10 条文本
  - 返回的向量按 text_index 排序确保与输入顺序一致

调用模式:
  - get_embedding: 单条文本向量化（用于用户问题）
  - get_embeddings_batch: 批量向量化（用于知识库文档切块），自动分批

异步设计:
  - 使用 asyncio.get_running_loop().run_in_executor() 在线程池中执行同步 API 调用
  - 避免阻塞 FastAPI 的事件循环
"""

import asyncio
from typing import List

import dashscope
from dashscope import TextEmbedding

import config

# 设置 API Key（模块加载时执行一次）
dashscope.api_key = config.DASHSCOPE_API_KEY


async def get_embedding(text: str) -> List[float]:
    """
    将单个文本转换为 1024 维向量。

    典型用途: 将用户问题向量化，用于 ChromaDB 相似度检索。
    内部调用 _call_embedding_api([text])，在线程池中执行。
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _call_embedding_api, [text])
    return result[0]


async def get_embeddings_batch(texts: List[str], batch_size: int = 10) -> List[List[float]]:
    """
    批量将文本转换为向量。

    参数:
        texts: 待向量化的文本列表
        batch_size: 每批处理条数（DashScope 上限为 10）

    典型用途: 知识库重建时批量向量化所有文档切块。
    自动按 batch_size 分批调用 API，避免超过单次请求限制。
    """
    all_embeddings = []
    loop = asyncio.get_running_loop()

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = await loop.run_in_executor(None, _call_embedding_api, batch)
        all_embeddings.extend(batch_embeddings)
        print(f"[Embedding] 已处理 {min(i + batch_size, len(texts))}/{len(texts)} 条")

    return all_embeddings


def _call_embedding_api(texts: List[str]) -> List[List[float]]:
    """
    同步调用 DashScope TextEmbedding API。

    参数:
        texts: 文本列表（最多 10 条）

    返回:
        向量列表，每个向量为 1024 个 float 的 list，按 text_index 排序

    错误处理: status_code != 200 时抛出异常，由上层异步函数处理。
    """
    response = TextEmbedding.call(
        model=config.EMBEDDING_MODEL,
        input=texts
    )

    if response.status_code != 200:
        raise Exception(
            f"Embedding API 调用失败: status={response.status_code}, "
            f"message={response.message}"
        )

    # API 返回的 embeddings 顺序可能与输入不一致，按 text_index 排序
    embeddings_data = response.output["embeddings"]
    embeddings_data.sort(key=lambda x: x["text_index"])
    return [item["embedding"] for item in embeddings_data]
