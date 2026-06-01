"""
认证相关路由 — 注册、登录、登出、当前用户信息、部门列表。

核心设计:
  - 登录成功后返回 token（随机字符串，存入数据库，24h 有效）
  - 登出时必须销毁服务端 token，防止 token 泄漏后被继续使用
  - /auth/me 返回用户完整信息（角色、菜单权限、可访问部门），前端据此渲染 UI
  - 部门列表按组织隔离，超管可通过 X-Current-Org-Id header 切换视角
"""

from fastapi import APIRouter, Depends, Request

from models import RegisterRequest, LoginRequest, MessageResponse
from auth import get_current_user, get_menus_for_role, get_user_accessible_departments
from dependencies import get_effective_org_id

router = APIRouter()


@router.post("/auth/register")
async def register(request: RegisterRequest):
    """
    注册新用户并自动登录。

    流程:
      1. 根据邀请码自动分配组织和角色（invite_code 在 organizations 表中）
      2. 注册成功后立即调用 login_user 返回 token
      3. 无需额外登录步骤
    """
    from auth import register_user, login_user
    register_user(request.username, request.password, invite_code=request.invite_code)
    result = login_user(request.username, request.password)
    return result


@router.post("/auth/login")
async def login(request: LoginRequest):
    """
    用户登录 — 验证用户名密码，返回 token + 用户信息。

    登录成功后记录审计日志，用于安全追溯。
    """
    from auth import login_user
    from audit import log_action
    result = login_user(request.username, request.password)
    log_action(result["user_id"], "login", "auth", f"用户 {request.username} 登录")
    return result


@router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """
    获取当前登录用户的完整信息。

    返回值包含:
      - user_id, username, role: 基本身份
      - org_id, org_code: 所属组织（多租户隔离依据）
      - departments: 用户可访问的部门列表
      - menus: 前端侧边栏菜单（根据角色动态生成）

    前端每次刷新页面时调用此接口恢复登录态。
    """
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "org_id": user.get("org_id"),
        "org_code": user.get("org_code"),
        "departments": user["departments"],
        "menus": get_menus_for_role(user["role"]),
    }


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(request: Request, user: dict = Depends(get_current_user)):
    """
    用户登出 — 从 Authorization header 提取 token 并销毁。

    为什么必须销毁 token:
      - token 存储在 auth_tokens 表中，不销毁则 24h 内仍可用于 API 调用
      - 防止 token 泄露后被恶意使用（如浏览器本地存储被 XSS 窃取）
      - 用户主动登出应立即使 token 失效
    """
    from auth import logout_user
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        logout_user(token)
    return MessageResponse(status="ok")


@router.get("/departments")
async def get_departments(request: Request, user: dict = Depends(get_current_user)):
    """
    获取用户可访问的部门列表。

    过滤逻辑:
      - 超管: 能看到所有部门（或当前切换组织下的所有部门）
      - 普通用户/admin: 只能看到自己被分配的部门（通过 user_departments 关联表）

    部门数据按 org_id 隔离，超管通过 X-Current-Org-Id header 切换组织视角。
    """
    from db import get_db
    db = get_db()
    accessible = get_user_accessible_departments(user)
    effective_org_id = get_effective_org_id(user, request)
    if effective_org_id:
        rows = db.execute("SELECT id, name, display_name, description FROM departments WHERE org_id = ?", (effective_org_id,)).fetchall()
    else:
        rows = db.execute("SELECT id, name, display_name, description FROM departments").fetchall()
    departments = []
    for r in rows:
        if user["role"] == 'super_admin' or r["name"] in accessible:
            departments.append({
                "id": r["id"],
                "name": r["name"],
                "display_name": r["display_name"],
                "description": r["description"],
            })
    return {"departments": departments}
