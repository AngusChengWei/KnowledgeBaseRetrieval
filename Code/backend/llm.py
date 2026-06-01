"""
LLM 模块 — 封装 DeepSeek API 调用（使用 OpenAI SDK 兼容接口）。

架构说明:
  - 使用 OpenAI Python SDK 的兼容模式连接 DeepSeek API
  - DeepSeek 提供与 OpenAI 兼容的 /v1/chat/completions 端点
  - 所有 API 调用通过 asyncio.run_in_executor 在线程池中执行，不阻塞事件循环

两个核心函数:
  - generate_answer: 生成问答回答（带知识库上下文 + 对话历史）
  - rewrite_query: Query Rewriting 查询改写（优化向量检索召回率）

系统提示词设计:
  - 严格的 RAG 模式: 只基于参考资料回答，不编造信息
  - 追问模式: 信息不足时先展示已有政策再追问
  - 友好语气: 像 HR 同事一样沟通
"""

import asyncio
from typing import List, Dict

from openai import OpenAI

import config

# OpenAI 兼容客户端 — base_url 指向 DeepSeek API 地址
_client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL
)

# 系统提示词 — 定义 AI 助手的行为边界和回答风格
SYSTEM_PROMPT = """你是一个企业内部知识库问答助手。请根据提供的参考资料回答用户的问题。

严格遵守以下规则：
1. 只根据提供的参考资料回答问题，不使用外部知识。
2. 如果参考资料中没有相关信息，请明确告知用户"根据现有资料无法回答该问题"。
3. 不要编造或猜测任何信息。
4. 回答要简洁、准确、有条理。
5. 如果需要引用具体内容，请标注来源文件名。
6. 当参考资料包含答案但需要用户提供更多个人信息才能给出确切答案时（如工作年限、岗位等级、合同类型等），必须先展示参考资料中的相关政策或标准，然后再主动追问用户所缺的信息。例如："根据公司年假制度，年假天数取决于您的累计工作年限：• 满1年不满10年：5天• 满10年不满20年：10天• 满20年：15天。请问您的累计工作年限是多久？告诉我后我可以帮您确认具体的年假天数。"绝对不能跳过政策内容直接追问。
7. 当用户在后续对话中提供了所缺信息时，结合参考资料和用户提供的信息给出明确答案。
8. 保持友好、专业的语气，像一个HR同事在帮助你一样。"""


async def generate_answer(
    question: str,
    context_chunks: List[str],
    history: List[Dict[str, str]]
) -> str:
    """
    调用 DeepSeek API 生成回答 — RAG 流程的最后一步。

    参数:
        question: 用户当前问题（原始问题，非改写后的）
        context_chunks: 向量检索返回的相关文本块（已过滤低相似度）
        history: 对话历史 [{"role": "user/assistant", "content": "..."}]

    消息组装策略:
      1. system: 行为约束提示词
      2. 历史对话: 最近 N 轮（MAX_HISTORY_ROUNDS × 2 条消息）
      3. user: 当前问题 + 参考资料（如果有检索结果）
         - 有资料: "参考资料：... 用户问题：... 请根据参考资料回答"
         - 无资料: "知识库中无相关资料，请以助手身份友好回复"

    返回:
        模型生成的回答文本
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 载入对话历史（最近 N 轮），保持多轮对话连贯性
    max_history = config.MAX_HISTORY_ROUNDS * 2  # 每轮 = user + assistant 各一条
    if history:
        messages.extend(history[-max_history:])

    # 组装当前问题的用户消息
    if context_chunks:
        # 有检索结果: 拼接所有相关文本块作为参考资料
        context_text = "\n\n---\n\n".join(context_chunks)
        user_message = f"""参考资料：
{context_text}

---

用户问题：{question}

请根据以上参考资料回答用户的问题。"""
    else:
        # 无检索结果: 以通用助手身份友好回复，不编造信息
        user_message = f"""用户问题：{question}

知识库中没有找到与该问题相关的参考资料。请以友好的企业知识助手身份回复用户：
- 如果是问候/聊天，友好回应并简要介绍自己的功能
- 如果是业务问题，说明知识库中暂无相关资料，建议用户换个方式提问或确认文档已上传
- 不要编造任何信息"""

    messages.append({"role": "user", "content": user_message})

    # 在线程池中执行同步 API 调用，避免阻塞 asyncio 事件循环
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(None, _call_deepseek_api, messages)

    return response


async def rewrite_query(question: str) -> str:
    """
    Query Rewriting — 将用户口语化问题改写为适合向量检索的查询。

    为什么需要改写:
      - 用户问题通常是口语化的自然语言: "我们公司一年有几天年假啊？"
      - 向量检索更适合关键词/概念匹配: "年假 天数 制度"
      - 改写后能显著提升 ChromaDB 的检索召回率

    实现:
      - 使用轻量级 LLM 调用（temperature=0.3, max_tokens=100）
      - 改写失败时降级使用原始问题，不阻塞问答主流程

    参数:
        question: 用户原始问题
    返回:
        改写后的检索查询文本（失败时返回原始问题）
    """
    messages = [
        {
            "role": "system",
            "content": """你是一个查询改写助手。你的任务是将用户的口语化问题改写为更适合在知识库中检索的形式。

规则：
1. 提取问题中的核心关键词和概念
2. 补充可能的同义词或相关术语
3. 去除口语化表达、语气词
4. 输出简洁的检索查询（不超过50字）
5. 只输出改写后的查询，不要解释"""
        },
        {
            "role": "user",
            "content": f"请将以下问题改写为适合知识库检索的查询：\n{question}"
        }
    ]

    loop = asyncio.get_running_loop()
    try:
        rewritten = await loop.run_in_executor(None, _call_deepseek_api_lite, messages)
        rewritten = rewritten.strip()
        if rewritten:
            print(f"[Query Rewrite] '{question}' → '{rewritten}'")
            return rewritten
    except Exception as e:
        # 改写失败不阻塞主流程，降级使用原始问题
        print(f"[Query Rewrite] 改写失败，使用原始问题: {e}")

    return question


def _call_deepseek_api_lite(messages: List[Dict[str, str]]) -> str:
    """
    轻量级 LLM 调用 — 用于查询改写等辅助任务。

    参数差异:
      - temperature=0.3: 低温度保证输出稳定
      - max_tokens=100: 改写结果不超过 100 token
    """
    response = _client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=100
    )
    return response.choices[0].message.content


def _call_deepseek_api(messages: List[Dict[str, str]]) -> str:
    """
    同步调用 DeepSeek API — 在 run_in_executor 的线程中执行。

    参数来自 config:
      - LLM_TEMPERATURE: 生成温度（默认 0.7）
      - LLM_MAX_TOKENS: 最大输出 token 数（默认 2000）

    异常处理: API 调用失败时返回错误信息而非抛出异常，
    确保用户至少能得到一个错误提示而非空白页面。
    """
    try:
        response = _client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=messages,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM] DeepSeek API 调用失败: {e}")
        return f"抱歉，生成回答时出错：{str(e)}"
