"""
配置管理模块 — 从 .env 文件加载所有配置参数。

使用 python-dotenv 加载 .env 文件，支持:
  - 本地开发: 在 backend/.env 中配置真实 API Key
  - 部署: 通过环境变量注入，不依赖 .env 文件

所有配置项都有合理的默认值，最小化部署时的必填配置。
必填配置: DASHSCOPE_API_KEY, DEEPSEEK_API_KEY（否则 embedding 和 LLM 不可用）
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（优先级低于系统环境变量）
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ============ 数据库配置 ============

DB_PATH = os.getenv(
    "DB_PATH",
    str(Path(__file__).parent / "data" / "app.db")
)

# ============ API 配置 ============

# 阿里云 DashScope Embedding API — 文本转向量
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

# DeepSeek API — 兼容 OpenAI SDK 接口
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ============ 知识库配置 ============

# 文档存储目录（按 org_code/department 子目录组织）
KNOWLEDGE_DOCS_DIR = os.getenv(
    "KNOWLEDGE_DOCS_DIR",
    str(Path(__file__).parent / "knowledge_docs")
)

# ChromaDB 向量数据持久化目录
CHROMA_PERSIST_DIR = os.getenv(
    "CHROMA_PERSIST_DIR",
    str(Path(__file__).parent / "chroma_db")
)

# ChromaDB 集合名称前缀（完整名称为 {prefix}_{org_code}_{department}）
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "knowledge_base")

# ============ 分块参数 ============

# 文本块大小（字符数），影响检索粒度
# 太小: 信息不完整；太大: 检索精度下降
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))

# 相邻块之间的重叠字符数，防止关键信息被切分到两个块的边界
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# ============ 检索参数 ============

# 向量检索返回的候选数量
TOP_K = int(os.getenv("TOP_K", "3"))

# 相似度阈值，低于此值的检索结果被过滤（余弦相似度范围 [-1, 1]）
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))

# ============ LLM 参数 ============

# 生成温度: 0.0=确定性强, 1.0=创造性高。知识库问答建议低温度
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# 最大输出 token 数
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

# ============ 会话参数 ============

# 多轮对话保留的最大历史轮数（每轮 = 用户问题 + AI 回答）
MAX_HISTORY_ROUNDS = int(os.getenv("MAX_HISTORY_ROUNDS", "10"))

# ============ 上传限制 ============

# 单文件最大大小（MB）
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))

# ============ 部门配置（已废弃，部门由数据库动态管理） ============

# 保留仅用于 db.py 初始化默认部门时的 fallback
_DEFAULT_DEPARTMENTS = ["general", "hr", "tech", "finance"]
_DEFAULT_DEPARTMENT_NAMES = {
    "general": "公共知识库",
    "hr": "人事部",
    "tech": "技术部",
    "finance": "财务部",
}

# ============ PDF 生成配置 ============

# PDF 中文字体路径（使用 Noto Sans SC 支持中文渲染）
PDF_FONT_PATH = os.getenv(
    "PDF_FONT_PATH",
    str(Path(__file__).parent / "fonts" / "NotoSansSC-Regular.ttf")
)
PDF_FONT_NAME = "NotoSansSC"

# ============ CORS 配置 ============

# 允许的跨域来源（逗号分隔）
# 开发环境: http://localhost:5173（Vite 默认端口）
# 生产环境: 替换为实际部署域名
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# ============ 文件分析配置 ============

# 文件分析临时上传目录（分析完成后自动清理）
ANALYSIS_TEMP_DIR = os.getenv(
    "ANALYSIS_TEMP_DIR",
    str(Path(__file__).parent / "data" / "analysis_temp")
)
