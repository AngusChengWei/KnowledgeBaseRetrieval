"""
文本分块模块 — 将长文档切分为适合向量检索的文本块。

两种分块策略:
  1. Markdown 语义分块: 按 #/##/### 标题将文档分成结构化段落
     - 每个块携带所属章节标题作为上下文
     - 超长段落按换行二次切分
  2. 固定大小滑动窗口分块: 用于 PDF/DOCX/TXT 等无结构文档
     - chunk_size 控制块大小，chunk_overlap 控制相邻块的重叠

分块参数对检索效果的影响:
  - CHUNK_SIZE 太小 → 信息碎片化，缺乏上下文
  - CHUNK_SIZE 太大 → 检索精度下降，噪音增加
  - CHUNK_OVERLAP 太小 → 关键信息可能被切分在边界处
  - CHUNK_OVERLAP 太大 → 冗余信息增多

推荐值: CHUNK_SIZE=500, CHUNK_OVERLAP=50
"""

import re
from typing import List, Dict


def split_documents(
    documents: List[Dict[str, str]],
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[Dict]:
    """
    将多个文档切分为文本块。

    参数:
        documents: [{"filename": "xxx.pdf", "content": "..."}]
        chunk_size: 每个块的最大字符数
        chunk_overlap: 相邻块的重叠字符数

    返回:
        [{"text": "块内容", "metadata": {"filename": "xxx.pdf", "chunk_index": 0, "section": "..."}}, ...]

    Markdown 文件特殊处理: 按标题层级分块，保留章节结构信息。
    """
    all_chunks = []

    for doc in documents:
        filename = doc["filename"]
        content = doc["content"]

        # Markdown 文件使用语义分块（按标题层级切分）
        if filename.lower().endswith(".md"):
            chunks = _split_markdown_by_headers(content, chunk_size)
        else:
            chunks = _split_text_to_dicts(content, chunk_size, chunk_overlap)

        # 为每个块附加元数据
        for i, chunk_info in enumerate(chunks):
            metadata = {"filename": filename, "chunk_index": i}
            if isinstance(chunk_info, dict):
                metadata["section"] = chunk_info.get("section", "")
                text = chunk_info["text"]
            else:
                text = chunk_info
            all_chunks.append({"text": text, "metadata": metadata})

    print(f"[文本分块] 共生成 {len(all_chunks)} 个文本块")
    return all_chunks


def _split_markdown_by_headers(content: str, max_chunk_size: int = 500) -> List[Dict[str, str]]:
    """
    按 Markdown 标题（#/##/###/####）将文档分成语义段落。

    策略:
      1. 用正则匹配标题行，将文档按标题边界切分
      2. 维护标题层级栈，为每个段落生成 "章节 > 子章节" 路径
      3. 块内容前附加章节标题作为上下文（如 "[人事制度 > 年假] 正文..."）
      4. 超长段落按换行二次切分

    这样检索时，即使只命中段落的一部分，也能知道它属于哪个章节。
    """
    header_pattern = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)

    sections = []
    last_pos = 0
    current_headers = []  # 标题层级栈，如 ["人事制度", "年假政策"]

    for match in header_pattern.finditer(content):
        # 保存前一段内容（标题行之前的部分）
        if last_pos < match.start():
            text = content[last_pos:match.start()].strip()
            if text:
                section_title = " > ".join(current_headers) if current_headers else ""
                sections.append({"text": text, "section": section_title})

        # 更新标题栈: 截断到当前层级，追加新标题
        level = len(match.group(1))
        title = match.group(2).strip()
        current_headers = current_headers[:level - 1]
        current_headers.append(title)

        last_pos = match.end()

    # 最后一段（最后一个标题之后的内容）
    if last_pos < len(content):
        text = content[last_pos:].strip()
        if text:
            section_title = " > ".join(current_headers) if current_headers else ""
            sections.append({"text": text, "section": section_title})

    # 二次处理: 超长段落按换行切分，每个子块前附加章节标题
    result = []
    for section in sections:
        section_prefix = f"[{section['section']}] " if section['section'] else ""
        full_text = section_prefix + section['text']

        if len(full_text) <= max_chunk_size:
            result.append({"text": full_text, "section": section['section']})
        else:
            sub_chunks = _split_long_section(full_text, max_chunk_size)
            for sub in sub_chunks:
                result.append({"text": sub, "section": section['section']})

    return result


def _split_long_section(text: str, max_size: int) -> List[str]:
    """
    对超长段落进行二次切分 — 优先按换行分割。

    策略:
      1. 按换行符拆分为段落
      2. 贪心拼接: 当前块 + 下一段落 ≤ max_size → 拼入
      3. 超出 → 当前块结束，下一段落开始新块
      4. 单个段落超长 → 强制按固定大小切分
    """
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 1 <= max_size:
            current_chunk += ("\n" + para if current_chunk else para)
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # 单段落超长 → 强制切分
            if len(para) > max_size:
                for i in range(0, len(para), max_size - 50):
                    chunks.append(para[i:i + max_size - 50])
                current_chunk = ""
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _split_text_to_dicts(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    固定大小滑动窗口分块 — 用于无结构文档（PDF/DOCX/TXT）。

    算法:
      - 窗口大小 = chunk_size
      - 每次滑动步长 = chunk_size - overlap
      - 即相邻窗口有 overlap 个字符的重叠

    例如 chunk_size=500, overlap=50:
      块1: text[0:500]
      块2: text[450:950]
      块3: text[900:1400]
    """
    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk)

        start = start + chunk_size - overlap

    return chunks
