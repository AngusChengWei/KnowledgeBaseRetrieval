"""PDF 生成模块：支持 AI 问答报告生成和知识库文档导出"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fpdf import FPDF

import config


def _get_font_path() -> tuple:
    """
    获取可用的中文字体路径和字体名称。
    优先级: 配置路径 > fc-list 检测 > 预设路径 > 递归扫描(中文优先) > None
    返回 (None, None) 表示未找到中文字体。
    """
    # 1. 检查配置路径
    if os.path.exists(config.PDF_FONT_PATH):
        return config.PDF_FONT_PATH, config.PDF_FONT_NAME

    # 2. 使用 fc-list 查找系统中文字体（Linux/Mac 需安装 fontconfig）
    try:
        import subprocess
        result = subprocess.run(
            ["fc-list", ":lang=zh", "-f", "%{file}|%{family}\n"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split("\n"):
                parts = line.split("|", 1)
                if len(parts) == 2:
                    fp, fn = parts[0], parts[1].split(",")[0].strip()
                    if os.path.exists(fp):
                        return fp, fn.replace(" ", "")
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    # 3. Windows 系统字体备选
    windows_fonts = [
        (r"C:\Windows\Fonts\msyh.ttc", "MicrosoftYaHei"),
        (r"C:\Windows\Fonts\simhei.ttf", "SimHei"),
        (r"C:\Windows\Fonts\yahei.ttf", "MicrosoftYaHei"),
        (r"C:\Windows\Fonts\simsun.ttc", "SimSun"),
        (r"C:\Windows\Fonts\msyhbd.ttc", "MicrosoftYaHei"),
        (r"C:\Windows\Fonts\deng.ttf", "DengXian"),
    ]
    for font_path, font_name in windows_fonts:
        if os.path.exists(font_path):
            return font_path, font_name

    # 4. Linux/Mac 系统字体备选（扩展列表）
    linux_fonts = [
        # DroidSansFallback
        ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", "DroidSansFallback"),
        # Noto Sans CJK (不同发行版不同路径)
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "NotoSansCJK"),
        ("/usr/share/fonts/noto-cjk/NotoSansCJKsc-Regular.otf", "NotoSansCJKsc"),
        ("/usr/share/fonts/noto-cjk/NotoSansSC-Regular.otf", "NotoSansSC"),
        ("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf", "NotoSansSC"),
        ("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf", "NotoSansSC"),
        # WenQuanYi Micro Hei（最常用的 Linux 中文点阵字体）
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WenQuanYiMicroHei"),
        ("/usr/share/fonts/wqy-microhei/wqy-microhei.ttc", "WenQuanYiMicroHei"),
        # WenQuanYi Zen Hei
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WenQuanYiZenHei"),
        ("/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc", "WenQuanYiZenHei"),
        # 其他常见位置
        ("/usr/share/fonts/truetype/arphic/uming.ttc", "ARPLUMing"),
        ("/usr/share/fonts/truetype/arphic/ukai.ttc", "ARPLUKai"),
        # macOS
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "STHeiti"),
    ]
    for font_path, font_name in linux_fonts:
        if os.path.exists(font_path):
            return font_path, font_name

    # 5. 递归扫描字体目录，优先返回支持中文的字体
    CJK_KEYWORDS = [
        "cjk", "noto", "wqy", "wenquan", "chinese", "sc", "tc",
        "heiti", "songti", "ming", "hei", "song", "fang",
        "kai", "yahei", "simsun", "simhei", "droid", "arphic",
        "uming", "ukai", "pingfang", "stheit", "hans",
    ]

    scan_dirs = ["/usr/share/fonts", "/usr/local/share/fonts", "/usr/share/fontconfig"]
    candidates_cjk = []
    candidates_other = []

    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for root, _dirs, files in os.walk(scan_dir):
            for f in files:
                if not f.lower().endswith((".ttf", ".ttc", ".otf")):
                    continue
                fp = os.path.join(root, f)
                fn = os.path.splitext(f)[0].replace("-", "").replace(" ", "")
                if any(kw in f.lower() for kw in CJK_KEYWORDS):
                    candidates_cjk.append((fp, fn))
                else:
                    candidates_other.append((fp, fn))

    if candidates_cjk:
        return candidates_cjk[0]

    # 6. 仍然找不到中文字体，返回 None
    #     调用方会回退到 Helvetica（抛出清晰异常提示安装中文字体）
    return None, None


class PDFGenerator:
    """PDF 生成器基类"""

    def __init__(self):
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=25)
        # 注册中文字体
        font_path, font_name = _get_font_path()
        if font_path:
            self.pdf.add_font(font_name, "", font_path, uni=True)
            self.pdf.add_font(font_name, "B", font_path, uni=True)
            self.font_name = font_name
        else:
            # 无中文字体时使用 fpdf2 内置字体（仅支持拉丁字符）
            self.font_name = "Helvetica"
        self._add_metadata()

    def _add_metadata(self):
        """添加 PDF 元数据"""
        self.pdf.set_title("企业AI知识助手 - 文档导出")
        self.pdf.set_author("企业AI知识助手系统")
        self.pdf.set_creator("KnowledgeBaseRetrieval")

    def _write_title(self, title: str):
        """写入标题"""
        self.pdf.add_page()
        self.pdf.set_font(self.font_name, "", 20)
        self.pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
        self.pdf.ln(5)

    def _write_separator(self):
        """写入分隔线"""
        self.pdf.set_draw_color(180, 180, 180)
        self.pdf.line(10, self.pdf.get_y(), 200, self.pdf.get_y())
        self.pdf.ln(5)

    def _write_text_block(self, text: str, size: int = 11, bold: bool = False, indent: float = 0):
        """写入文本块（自动换行，处理中文）"""
        style = "B" if bold else ""
        self.pdf.set_font(self.font_name, style, size)
        # 分段处理
        for line in text.split("\n"):
            if line.strip():
                self.pdf.set_x(10 + indent * 5)
                self.pdf.multi_cell(190 - indent * 5, 6, _clean_text(line.strip()))
                self.pdf.ln(1)
            else:
                self.pdf.ln(3)

    def _write_footer(self):
        """在每页底部写入生成信息"""
        self.pdf.set_y(-20)
        self.pdf.set_font(self.font_name, "", 8)
        self.pdf.set_text_color(128, 128, 128)
        self.pdf.cell(
            0, 10,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  企业AI知识助手系统",
            new_x="LMARGIN", new_y="NEXT", align="C"
        )


def generate_report_pdf(
    question: str,
    answer: str,
    sources: Optional[List[dict]] = None,
    title: str = "AI 问答报告"
) -> bytes:
    """
    生成 AI 问答报告 PDF。

    参数:
        question: 用户问题
        answer: AI 回答内容
        sources: 引用来源列表 [{"filename": "...", "chunk": "..."}, ...]
        title: 报告标题

    返回:
        PDF 文件字节流
    """
    gen = PDFGenerator()
    pdf = gen.pdf

    # 封面
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font(gen.font_name, "", 24)
    pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    pdf.set_font(gen.font_name, "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 8, f"系统: 企业AI知识助手系统",
             new_x="LMARGIN", new_y="NEXT", align="C")

    # 用户问题
    pdf.add_page()
    pdf.set_font(gen.font_name, "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "用户问题", new_x="LMARGIN", new_y="NEXT")
    gen._write_separator()
    pdf.set_font(gen.font_name, "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 6, _clean_text(question))
    pdf.ln(5)

    # AI 回答
    pdf.set_font(gen.font_name, "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "AI 回答", new_x="LMARGIN", new_y="NEXT")
    gen._write_separator()
    pdf.set_font(gen.font_name, "", 11)
    pdf.set_text_color(60, 60, 60)
    for paragraph in answer.split("\n"):
        if paragraph.strip():
            pdf.multi_cell(0, 6, _clean_text(paragraph.strip()))
            pdf.ln(1)
        else:
            pdf.ln(3)

    # 引用来源
    if sources:
        pdf.add_page()
        pdf.set_font(gen.font_name, "B", 14)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 10, "引用来源", new_x="LMARGIN", new_y="NEXT")
        gen._write_separator()
        for i, source in enumerate(sources, 1):
            pdf.set_font(gen.font_name, "B", 11)
            pdf.set_text_color(30, 80, 160)
            pdf.cell(0, 8, f"[{i}] {source.get('filename', '未知')}",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(gen.font_name, "", 10)
            pdf.set_text_color(80, 80, 80)
            chunk_text = source.get('chunk', '')[:300]
            pdf.multi_cell(0, 5, _clean_text(chunk_text))
            pdf.ln(3)

    # 页脚
    gen._write_footer()

    return bytes(pdf.output())


def export_documents_pdf(
    documents: List[dict],
    title: str = "知识库文档导出"
) -> bytes:
    """
    将知识库文档导出为 PDF。

    参数:
        documents: 文档列表 [{"filename": "...", "content": "..."}, ...]
        title: 导出标题

    返回:
        PDF 文件字节流
    """
    gen = PDFGenerator()
    pdf = gen.pdf

    # 封面
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font(gen.font_name, "", 24)
    pdf.cell(0, 15, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    pdf.set_font(gen.font_name, "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 8, f"文档数量: {len(documents)} 份",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.cell(0, 8, f"系统: 企业AI知识助手系统",
             new_x="LMARGIN", new_y="NEXT", align="C")

    # 目录
    pdf.add_page()
    pdf.set_font(gen.font_name, "B", 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, "目  录", new_x="LMARGIN", new_y="NEXT", align="C")
    gen._write_separator()
    for i, doc in enumerate(documents, 1):
        pdf.set_font(gen.font_name, "", 11)
        pdf.set_text_color(30, 80, 160)
        pdf.cell(0, 8, f"  {i}. {doc['filename']}",
                 new_x="LMARGIN", new_y="NEXT")
        content_preview = doc.get('content', '')[:60].replace("\n", " ")
        pdf.set_font(gen.font_name, "", 9)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, f"      {content_preview}...",
                 new_x="LMARGIN", new_y="NEXT")

    # 文档正文
    for doc in documents:
        pdf.add_page()
        pdf.set_font(gen.font_name, "B", 16)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 12, doc['filename'], new_x="LMARGIN", new_y="NEXT")
        gen._write_separator()
        pdf.set_font(gen.font_name, "", 11)
        pdf.set_text_color(60, 60, 60)
        for paragraph in doc.get('content', '').split("\n"):
            if paragraph.strip():
                pdf.multi_cell(0, 6, _clean_text(paragraph.strip()))
                pdf.ln(1)
            else:
                pdf.ln(3)

    # 页脚
    gen._write_footer()

    return bytes(pdf.output())


def _clean_text(text: str) -> str:
    """清理文本中的特殊字符，确保 PDF 兼容"""
    if not text:
        return ""
    # 替换 PDF 不支持的 Unicode 字符
    text = text.replace("\u2014", "--")  # em dash
    text = text.replace("\u2013", "-")   # en dash
    text = text.replace("\u2018", "'")   # left single quote
    text = text.replace("\u2019", "'")   # right single quote
    text = text.replace("\u201c", '"')   # left double quote
    text = text.replace("\u201d", '"')   # right double quote
    text = text.replace("\u2026", "...") # ellipsis
    text = text.replace("\u00a0", " ")   # non-breaking space
    # 移除控制字符 (除换行符 \n)
    text = "".join(c if c == "\n" or (ord(c) >= 32 and ord(c) != 127) else "" for c in text)
    # 移除常见 emoji 和装饰符号 (Unicode 区块: U+1F000-U+1FFFF, U+2600-U+27BF, U+2700-U+27BF, 等)
    text = "".join(c for c in text if not _is_unsupported_char(c))
    return text


def _is_unsupported_char(c: str) -> bool:
    """判断字符是否为 PDF 渲染不支持的装饰性字符"""
    cp = ord(c)
    # 杂项符号 (Miscellaneous Symbols) U+2600-U+26FF
    if 0x2600 <= cp <= 0x26FF:
        return True
    # 装饰符号 (Dingbats) U+2700-U+27BF
    if 0x2700 <= cp <= 0x27BF:
        return True
    # 补充箭头-A (Supplemental Arrows-A) U+27F0-U+27FF
    if 0x27F0 <= cp <= 0x27FF:
        return True
    # 补充箭头-B (Supplemental Arrows-B) U+2900-U+297F
    if 0x2900 <= cp <= 0x297F:
        return True
    # 杂项数学符号-B (Miscellaneous Mathematical Symbols-B) U+2980-U+29FF
    if 0x2980 <= cp <= 0x29FF:
        return True
    # Emoji 区块 (U+1F000+)
    if 0x1F000 <= cp <= 0x1FFFF:
        return True
    # 额外的 emoji / 装饰字符
    if 0x2300 <= cp <= 0x23FF:  # 杂项技术符号
        return True
    if 0x25A0 <= cp <= 0x25FF:  # 几何图形（方块、圆圈、三角等）
        return True
    if 0x2B00 <= cp <= 0x2BFF:  # 杂项符号和箭头
        return True
    if 0xFE00 <= cp <= 0xFE0F:  # 变体选择符（emoji 修饰符）
        return True
    if 0x200D == cp:  # 零宽连字（ZWJ，用于组合 emoji）
        return True
    if 0xFE0F == cp or 0x20E3 == cp:  # emoji 修饰符
        return True
    return False
