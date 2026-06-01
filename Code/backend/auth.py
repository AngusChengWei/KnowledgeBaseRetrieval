"""
认证模块 — 密码哈希、Token 管理、FastAPI 依赖注入、角色权限控制。

安全设计:
  - 密码: PBKDF2-SHA256 哈希，60 万次迭代，随机 32 字节 salt
  - Token: secrets.token_urlsafe(32) 生成，存储在 auth_tokens 表，24h 过期
  - 登录时删除该用户所有旧 token（一个用户同一时刻只有一个有效 token）
  - 邀请码注册: 用户通过组织专属邀请码注册，自动分配组织和角色

权限层级:
  - super_admin: 平台超管，可管理所有组织、切换组织视角
  - admin: 组织管理员，只能管理自己组织的用户和知识库
  - user: 普通用户，只能访问被分配的部门知识库

FastAPI 依赖注入链:
  get_current_user → require_admin → require_super_admin
  路由通过 Depends(get_current_user) 自动获取当前用户信息
"""

import hashlib
import secrets
import re
from functools import wraps
from fastapi import HTTPException, Header, Depends

from db import get_db

# 用户名规则: 3-32 位，字母/数字/下划线/中文
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_一-鿿]{3,32}$")
_MIN_PASSWORD_LEN = 6
_ITERATIONS = 600_000  # PBKDF2 迭代次数（OWASP 推荐 >= 600,000）


def _validate_credentials(username: str, password: str):
    """校验用户名格式和密码长度，不通过直接抛 400"""
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="用户名需 3-32 位，仅支持字母、数字、下划线和中文")
    if len(password) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"密码至少 {_MIN_PASSWORD_LEN} 位")


def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """
    PBKDF2-SHA256 密码哈希。

    参数:
        password: 明文密码
        salt: 可选 salt（hex 字符串），不传则自动生成 32 字节随机 salt

    返回:
        (hex_hash, hex_salt) — 均以十六进制字符串存储
    """
    if salt is None:
        salt = secrets.token_hex(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return dk.hex(), salt


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    """验证密码: 用相同的 salt 和迭代次数重新计算哈希，比对结果"""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return dk.hex() == stored_hash


def register_user(username: str, password: str, invite_code: str = None) -> dict:
    """
    注册新用户。

    邀请码机制:
      - 每个组织有 admin_invite_code 和 user_invite_code 两个邀请码
      - 匹配 admin_invite_code → 注册为 admin 角色
      - 匹配 user_invite_code → 注册为 user 角色
      - 邀请码同时确定用户的 org_id

    注册后不自动登录，需调用 login_user 获取 token。
    """
    _validate_credentials(username, password)
    db = get_db()

    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")

    # 根据邀请码确定组织和角色
    org_id = None
    role = 'user'
    if not invite_code or not invite_code.strip():
        raise HTTPException(status_code=400, detail="请填写邀请码")
    invite_code = invite_code.strip()
    org_row = db.execute(
        "SELECT id, admin_invite_code, user_invite_code FROM organizations WHERE admin_invite_code = ? OR user_invite_code = ?",
        (invite_code, invite_code)
    ).fetchone()
    if not org_row:
        raise HTTPException(status_code=400, detail="邀请码无效")
    org_id = org_row["id"]

    _check_org_active(db, org_id)

    if invite_code == org_row["admin_invite_code"]:
        role = 'admin'
    else:
        role = 'user'

    pw_hash, salt = hash_password(password)
    cur = db.execute(
        "INSERT INTO users (username, password_hash, salt, role, org_id, created_at) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
        (username, pw_hash, salt, role, org_id)
    )
    db.commit()
    return {"user_id": cur.lastrowid, "username": username}


def _check_org_active(db, org_id: int):
    """检查组织是否被禁用，被禁用的组织下所有用户无法登录/操作"""
    if org_id is None:
        return
    org = db.execute("SELECT status FROM organizations WHERE id = ?", (org_id,)).fetchone()
    if org and org["status"] == 'disabled':
        raise HTTPException(
            status_code=403,
            detail="所属组织已被禁用，请联系系统管理员"
        )


def login_user(username: str, password: str) -> dict:
    """
    用户登录 — 验证密码，生成 token，返回用户信息。

    安全措施:
      1. 验证用户名密码
      2. 检查账号是否被禁用
      3. 检查所属组织是否被禁用
      4. 删除该用户所有旧 token（单点登录：一个用户只保留一个有效 token）
      5. 生成新 token（32 字节随机 url-safe 字符串）
      6. Token 有效期 24 小时（存储在 expires_at 字段）

    返回:
        {token, user_id, username, role, org_id, org_code, departments}
    """
    _validate_credentials(username, password)
    db = get_db()

    user = db.execute(
        "SELECT id, username, password_hash, salt, role, status, org_id FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    if not user or not verify_password(password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user["status"] == 'disabled':
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    _check_org_active(db, user["org_id"])

    # 清除旧 token，保证一个用户同一时间只有一个有效登录
    db.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user["id"],))

    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime','+24 hours'))",
        (token, user["id"])
    )
    db.commit()

    departments = get_user_departments(user["id"])

    # 查询组织信息
    org_id = user["org_id"] if "org_id" in user.keys() else None
    org_code = None
    if org_id:
        org_row = db.execute("SELECT code FROM organizations WHERE id = ?", (org_id,)).fetchone()
        org_code = org_row["code"] if org_row else None

    return {
        "token": token,
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "org_id": org_id,
        "org_code": org_code,
        "departments": departments,
    }


def logout_user(token: str):
    """
    销毁服务端 token — 从 auth_tokens 表物理删除。

    调用时机: 用户主动点击登出按钮。
    效果: 该 token 立即失效，后续携带此 token 的请求返回 401。
    """
    db = get_db()
    db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
    db.commit()


def get_current_user(authorization: str = Header(...)) -> dict:
    """
    FastAPI 依赖注入 — 从 Authorization header 解析当前登录用户。

    校验流程:
      1. 提取 Bearer token
      2. 在 auth_tokens 表中查找 token（JOIN users）
      3. 检查 token 是否过期（过期则自动清理并返回 401）
      4. 检查用户账号状态
      5. 检查所属组织状态

    返回:
        {user_id, username, role, org_id, org_code, departments}

    被所有需要登录的 API 路由使用。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证格式错误，需要 Bearer token")

    token = authorization[7:]
    db = get_db()

    row = db.execute(
        """SELECT u.id, u.username, u.role, u.status, u.org_id, t.expires_at FROM users u
           JOIN auth_tokens t ON u.id = t.user_id
           WHERE t.token = ?""",
        (token,)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="无效的登录凭证，请重新登录")

    # 检查 token 是否过期
    if row["expires_at"]:
        from datetime import datetime
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            # 自动清理过期 token
            db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            db.commit()
            raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    if row["status"] == 'disabled':
        raise HTTPException(status_code=403, detail="账号已被禁用")

    _check_org_active(db, row["org_id"])

    departments = get_user_departments(row["id"])

    # 查询组织信息
    org_id = row["org_id"]
    org_code = None
    if org_id:
        org_row = db.execute("SELECT code FROM organizations WHERE id = ?", (org_id,)).fetchone()
        org_code = org_row["code"] if org_row else None

    return {
        "user_id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "org_id": org_id,
        "org_code": org_code,
        "departments": departments,
    }


def get_user_departments(user_id: int) -> list:
    """
    获取用户关联的部门列表。

    通过 user_departments 关联表查询，返回部门 ID、name、display_name。
    用于前端显示用户可访问的部门列表，以及知识库检索时的部门过滤。
    """
    db = get_db()
    rows = db.execute(
        """SELECT d.id, d.name, d.display_name FROM departments d
           JOIN user_departments ud ON d.id = ud.department_id
           WHERE ud.user_id = ?""",
        (user_id,)
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "display_name": r["display_name"]} for r in rows]


def get_user_accessible_departments(user: dict) -> list:
    """
    获取用户可访问的部门名称列表（用于权限校验）。

    规则:
      - super_admin / admin: 可访问本组织所有部门（或全局所有部门）
      - 普通用户: 可访问自己被分配的部门 + "general" 公共知识库

    "general" 是每个组织默认的公共知识库部门，所有人都能访问。
    """
    db = get_db()
    org_id = user.get("org_id")
    if user["role"] in ('super_admin', 'admin'):
        if org_id:
            rows = db.execute("SELECT name FROM departments WHERE org_id = ?", (org_id,)).fetchall()
        else:
            rows = db.execute("SELECT name FROM departments").fetchall()
        return [r["name"] for r in rows]
    dept_names = [d["name"] for d in user["departments"]]
    if 'general' not in dept_names:
        dept_names.append('general')
    return dept_names


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI 依赖注入 — 要求管理员及以上权限。

    用法: 在路由参数中添加 `user: dict = Depends(require_admin)`
    非 admin/super_admin 访问会直接返回 403。
    """
    if user["role"] not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI 依赖注入 — 要求超级管理员权限。

    用法: 在路由参数中添加 `user: dict = Depends(require_super_admin)`
    仅 super_admin 角色可访问，admin 和 user 返回 403。
    """
    if user["role"] != 'super_admin':
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


def get_menus_for_role(role: str) -> list:
    """
    根据角色返回前端侧边栏菜单结构。

    菜单层级:
      - user: 智能问答 + 我的会话 + 文件分析
      - admin: user 菜单 + 知识库管理 + 用户/部门管理 + 审计日志
      - super_admin: admin 菜单 + 组织管理

    前端 /auth/me 接口获取此数据后渲染侧边栏导航。
    """
    base_menus = [
        {"key": "smart-qa", "label": "智能问答", "icon": "chat"},
        {"key": "my-sessions", "label": "我的会话", "icon": "history"},
    ]
    analysis_menus = [
        {"key": "analysis-data", "label": "数据文件校验", "icon": "analysis"},
        {"key": "analysis-compliance", "label": "文档合规检查", "icon": "list"},
    ]
    knowledge_menus = [
        {"key": "company-kb", "label": "公司知识库", "icon": "book"},
        {"key": "dept-kb", "label": "部门知识库", "icon": "folder"},
        {"key": "knowledge-export", "label": "知识库导出", "icon": "upload"},
    ]
    admin_menus = [
        {"key": "user-manage", "label": "用户管理", "icon": "users"},
        {"key": "dept-manage", "label": "部门管理", "icon": "building"},
        {"key": "audit-log", "label": "审计日志", "icon": "shield"},
        {"key": "user-sessions", "label": "用户会话", "icon": "history"},
        {"key": "company-settings", "label": "公司设置", "icon": "setting"},
    ]
    super_admin_menus = [
        {"key": "org-manage", "label": "组织管理", "icon": "office"},
    ]

    if role == 'super_admin':
        return base_menus + analysis_menus + knowledge_menus + admin_menus + super_admin_menus
    elif role == 'admin':
        return base_menus + analysis_menus + knowledge_menus + admin_menus
    else:
        return base_menus + analysis_menus
