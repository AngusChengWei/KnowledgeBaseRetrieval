"""
Pydantic 请求/响应模型 — 定义所有 API 接口的输入输出格式。

FastAPI 利用 Pydantic 自动完成:
  1. 请求体 JSON → Python 对象转换
  2. 字段类型校验（类型不对自动返回 422 错误）
  3. 生成 OpenAPI/Swagger 文档

字段名不加 Optional 表示必填，加上表示可选。
"""

from pydantic import BaseModel
from typing import Optional


# ============ 认证相关 ============

class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: Optional[str] = None  # 根据邀请码自动分配组织和角色


class LoginRequest(BaseModel):
    username: str
    password: str


# ============ 智能问答 ============

class AskRequest(BaseModel):
    session_id: str        # 会话 ID（UUID），承载多轮对话上下文
    question: str           # 用户输入的问题
    department: str = "general"  # 要从哪个部门的知识库检索


class SourceItem(BaseModel):
    """问答的参考来源 — 哪份文档的哪个片段"""
    filename: str           # 来源文档名
    chunk: str              # 命中的文本片段（截取前 200 字）


class AskResponse(BaseModel):
    answer: str             # AI 生成的回答
    sources: list[SourceItem]  # 引用的知识库来源
    session_id: str


# ============ 通用响应 ============

class RebuildResponse(BaseModel):
    status: str
    doc_count: int          # 处理的文档数
    chunk_count: int        # 切分后的文本块数


class SessionResponse(BaseModel):
    session_id: str


class HealthResponse(BaseModel):
    status: str


class UploadResponse(BaseModel):
    status: str
    uploaded_files: list[str]
    failed_files: list[str]


class MessageResponse(BaseModel):
    """简单操作结果（如登出）"""
    status: str


# ============ 管理后台 ============

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"      # 角色: super_admin / admin / user


class UpdateUserRoleRequest(BaseModel):
    role: str


class UpdateUserOrgRequest(BaseModel):
    org_id: int


class UpdateUserDeptRequest(BaseModel):
    department_ids: list[int]


class CreateDepartmentRequest(BaseModel):
    name: str               # 内部标识（字母/数字），如 "hr"
    display_name: str        # 显示名称，如 "人事部"
    description: str = ""


class UpdateDepartmentRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None


class CreateOrgRequest(BaseModel):
    code: str               # 组织编码（唯一标识）
    display_name: str
    description: str = ""


class UpdateOrgRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None   # active / disabled


class UpdateMyOrgRequest(BaseModel):
    display_name: Optional[str] = None


# ============ PDF 导出 ============

class ReportPdfRequest(BaseModel):
    session_id: str = ""
    question: str
    answer: str
    sources: list[SourceItem] = []


class ExportDocsPdfRequest(BaseModel):
    department: str = "general"
    filenames: list[str] = []   # 要导出的文件名列表，空表示导出全部


# ============ 文件分析 ============

class AnalysisTaskStatus(BaseModel):
    task_id: int
    status: str             # pending / processing / completed / failed
    filename: str
    file_type: str          # data / compliance
    analysis_type: str
    created_at: str


class AnalysisResultResponse(BaseModel):
    task_id: int
    status: str
    result: dict            # 分析结果 JSON（结构取决于分析类型）
