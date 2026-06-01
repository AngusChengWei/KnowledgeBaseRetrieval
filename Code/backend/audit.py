"""
审计日志模块 — 记录系统所有关键操作，用于安全追溯和合规审计。

记录内容:
  - 谁（user_id + username）
  - 做了什么（action）
  - 对什么资源（resource）
  - 详情（detail，最多 500 字符）
  - 从哪里（ip_address）
  - 哪个组织（org_id）
  - 什么时候（created_at，自动时间戳）

操作类型标签:
  ACTION_LABELS 字典维护所有操作类型的中文显示名称。
  前端审计日志页面通过 action_label 字段展示中文标签。

容错设计:
  log_action 失败时记录到 logger.error，不抛出异常。
  审计日志失败不应阻断主业务流程。
"""

from logger import get_logger
from db import get_db

_logger = get_logger(__name__)

# 操作类型 → 中文标签映射（前端审计日志页面使用）
ACTION_LABELS = {
    # 认证
    "login": "用户登录",
    # AI 问答
    "ask_question": "智能问答",
    # 知识库管理
    "upload_document": "上传文档",
    "delete_document": "删除文档",
    "rebuild_knowledge_base": "重建知识库",
    "rebuild_file_vectors": "重建文件向量",
    "delete_file_vectors": "删除文件向量",
    "import_url": "导入URL",
    # 导出
    "export_report_pdf": "导出PDF报告",
    "export_docs_zip": "导出文档ZIP",
    # 文件分析
    "analyze_data": "数据分析",
    "analyze_compliance": "合规检查",
    # 用户管理
    "create_user": "创建用户",
    "update_user_role": "修改用户角色",
    "update_user_org": "修改用户组织",
    "toggle_user_status": "变更用户状态",
    "update_user_departments": "修改用户部门",
    # 部门管理
    "create_department": "创建部门",
    "update_department": "更新部门",
    "delete_department": "删除部门",
    # 组织管理
    "create_organization": "创建组织",
    "update_organization": "更新组织",
    "delete_organization": "禁用组织",
    "regenerate_invite_codes": "重生成邀请码",
    # 公司设置
    "update_my_org": "修改公司信息",
    "regenerate_user_invite_code": "重生成用户邀请码",
}


def get_action_label(action: str) -> str:
    """
    获取操作类型对应的中文标签。

    如果 action 不在映射表中（如旧数据或自定义操作），返回原始 action 值。
    """
    return ACTION_LABELS.get(action, action)


def log_action(user_id: int, action: str, resource: str = "", detail: str = "", ip_address: str = "", org_id: int = None):
    """
    记录一条审计日志。

    参数:
        user_id: 操作人用户 ID
        action: 操作类型（如 "login", "ask_question"）
        resource: 操作资源（如 "auth", "knowledge", "admin"）
        detail: 操作详情（自由文本，最多 500 字符）
        ip_address: 客户端 IP（可选）
        org_id: 所属组织 ID（可选，不传则从用户记录中自动获取）

    容错: 日志记录失败时打印错误日志但不抛异常，确保不影响主业务流程。
    """
    try:
        db = get_db()
        row = db.execute("SELECT username, org_id FROM users WHERE id = ?", (user_id,)).fetchone()
        username = row["username"] if row else ""
        if org_id is None and row:
            org_id = row["org_id"]

        db.execute(
            """INSERT INTO audit_logs (user_id, username, action, resource, detail, ip_address, org_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))""",
            (user_id, username, action, resource, detail[:500], ip_address, org_id)
        )
        db.commit()
    except Exception as e:
        _logger.error(f"审计日志记录失败 (user={user_id}, action={action}): {e}")
