"""
FastAPI 依赖注入函数 — 多租户组织隔离的核心逻辑。

设计思路:
  - 每个用户属于一个组织（org_id），数据按组织隔离
  - 超管可以通过 HTTP Header "X-Current-Org-Id" 切换视角查看其他组织
  - 普通管理员和用户只能看到自己所属组织的数据
  - 这些函数被路由处理函数重复使用，抽离出来避免代码重复
"""

import string
import random
from pathlib import Path
from typing import Optional

from fastapi import Request, HTTPException


def generate_invite_code() -> str:
    """生成 8 位随机字母数字邀请码，用于新用户注册"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def get_effective_org_id(user: dict, request: Request) -> Optional[int]:
    """
    解析当前请求的有效组织 ID。

    返回值含义:
      - 普通用户/admin → 返回 user["org_id"]（只能看自己的组织）
      - 超管 + 携带 X-Current-Org-Id header → 返回 header 中的 org_id（切换视角）
      - 超管 + 未携带 header → 返回 None（None 表示查看全局/全部数据）
    """
    if user["role"] == 'super_admin':
        header_org = request.headers.get("X-Current-Org-Id")
        if header_org:
            try:
                return int(header_org)
            except (ValueError, TypeError):
                pass
        return None
    return user.get("org_id")


def get_effective_org_context(user: dict, request: Request) -> tuple:
    """
    获取完整的组织上下文 (org_id, org_code)。

    org_code 用于构建 ChromaDB 集合名称和文件目录路径，
    超管切换组织时需要额外查询目标组织的 code，普通用户直接用自己登录时的 org_code。
    """
    effective_org_id = get_effective_org_id(user, request)
    if effective_org_id and effective_org_id != user.get("org_id"):
        # 超管切换到了其他组织 → 需要查目标组织的 code
        from db import get_db
        db = get_db()
        row = db.execute("SELECT code FROM organizations WHERE id = ?", (effective_org_id,)).fetchone()
        org_code = row["code"] if row else "default"
        return effective_org_id, org_code
    return effective_org_id, user.get("org_code") or "default"


def validate_department(department: str, org_id: int = None):
    """
    验证部门名称是否在数据库中存在（按组织隔离）。
    如果 org_id 为 None（超管未选择组织），则跨组织查询。
    """
    from db import get_db
    db = get_db()
    if org_id:
        row = db.execute("SELECT id FROM departments WHERE name = ? AND org_id = ?", (department, org_id)).fetchone()
    else:
        row = db.execute("SELECT id FROM departments WHERE name = ?", (department,)).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail=f"无效的部门: {department}")


def get_docs_dir(department: str, org_code: str = "default") -> Path:
    """
    获取知识库文档的磁盘目录路径。

    目录结构: {KNOWLEDGE_DOCS_DIR}/{org_code}/{department}/
    例如: knowledge_docs/default/hr/  → 默认组织人事部的文档
    """
    import config
    return Path(config.KNOWLEDGE_DOCS_DIR) / org_code / department
