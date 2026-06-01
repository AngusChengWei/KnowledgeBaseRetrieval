"""
管理后台路由 — 用户管理、部门管理、组织管理、审计日志、会话查看。

权限层级:
  - super_admin: 平台最高权限，可管理所有组织和用户，可切换组织视角
  - admin: 组织管理员，只能管理自己组织内的用户和部门
  - user: 普通用户，无管理后台访问权限

多租户隔离:
  - 所有查询通过 get_effective_org_id() 获取当前组织上下文
  - 普通 admin 的 org_id 来自用户记录，无法切换
  - 超管通过 X-Current-Org-Id header 切换组织视角
  - 超管不传 header 时 org_id=None → 查看全局数据

审计日志:
  - 所有管理操作（创建/修改/删除用户、部门、组织）都记录到 audit_logs 表
  - log_action() 自动附加操作人 username 和 org_id
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Query, Body

from models import (
    CreateUserRequest, CreateDepartmentRequest, CreateOrgRequest,
)
from auth import require_admin, require_super_admin
from dependencies import get_effective_org_id, generate_invite_code

router = APIRouter()


# ============ 管理员会话查看 ============

@router.get("/admin/sessions")
async def admin_list_all_sessions(
    request: Request,
    user_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(require_admin)
):
    """
    管理员查看所有用户会话列表，支持分页和按用户筛选。

    返回字段:
      - departments: 会话关联的所有部门（JSON 数组）
      - is_deleted: 用户是否已删除该会话（软删除标记）
      - username: 会话所属用户

    按 org_id 隔离，admin 只能看到自己组织下的会话。
    """
    from db import get_db
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)

    # 动态构建 WHERE 条件（user_id 筛选 + org_id 隔离）
    conditions = []
    params = []
    if user_id:
        conditions.append("cs.user_id = ?")
        params.append(user_id)
    if effective_org_id:
        conditions.append("cs.org_id = ?")
        params.append(effective_org_id)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # 先查总数用于分页
    total_row = db.execute(
        f"SELECT COUNT(*) as cnt FROM chat_sessions cs JOIN users u ON cs.user_id = u.id {where_clause}",
        params
    ).fetchone()
    total = total_row["cnt"]

    offset = (page - 1) * page_size
    rows = db.execute(
        f"""SELECT cs.id, cs.department, cs.departments, cs.title, cs.created_at, cs.updated_at, cs.user_id, u.username, cs.is_deleted
            FROM chat_sessions cs JOIN users u ON cs.user_id = u.id
            {where_clause}
            ORDER BY cs.updated_at DESC
            LIMIT ? OFFSET ?""",
        params + [page_size, offset]
    ).fetchall()
    sessions = []
    for r in rows:
        depts = []
        if r["departments"]:
            try:
                depts = json.loads(r["departments"])
            except Exception:
                depts = []
        if not depts:
            depts = [r["department"]]
        sessions.append({
            "session_id": r["id"],
            "department": r["department"],
            "departments": depts,
            "title": r["title"] or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "user_id": r["user_id"],
            "username": r["username"],
            "is_deleted": bool(r["is_deleted"]),
        })
    return {"sessions": sessions, "total": total, "page": page, "page_size": page_size}


@router.get("/admin/sessions/{session_id}/messages")
async def admin_get_session_messages(session_id: str, request: Request, user: dict = Depends(require_admin)):
    """
    管理员查看指定会话的消息历史。

    与普通用户的 /sessions/{id}/messages 的区别:
      - 管理员不需要是会话所有者
      - 但仍需 org_id 校验，不能跨组织查看
    """
    from db import get_db
    from session import get_session_messages as get_msgs
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)
    if effective_org_id:
        session_row = db.execute(
            "SELECT id FROM chat_sessions WHERE id = ? AND org_id = ?",
            (session_id, effective_org_id)
        ).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="会话不存在或不属于当前组织")
    messages = get_msgs(db, session_id)
    for msg in messages:
        if msg["sources"]:
            try:
                msg["sources"] = json.loads(msg["sources"])
            except (json.JSONDecodeError, TypeError):
                msg["sources"] = []
        else:
            msg["sources"] = []
    return {"messages": messages, "session_id": session_id}


# ============ 用户管理 ============

@router.post("/admin/users")
async def admin_create_user(request: CreateUserRequest, http_request: Request, user: dict = Depends(require_admin)):
    """
    管理员创建新用户。

    自动行为:
      - 新用户自动绑定到当前管理员的 org_id（同组织）
      - 除非是超管，否则不能创建 super_admin 角色用户
      - 注册成功后通过 UPDATE 修正角色和组织归属

    使用 http_request（非 request）参数名避免与 CreateUserRequest 的 request 字段冲突。
    """
    from auth import register_user
    from db import get_db
    if request.role == 'super_admin' and user["role"] != 'super_admin':
        raise HTTPException(status_code=403, detail="只有超级管理员才能创建超管用户")
    result = register_user(request.username, request.password)
    db = get_db()
    org_id = get_effective_org_id(user, http_request)
    if request.role != 'user' or org_id:
        updates = []
        params_params = []
        if request.role != 'user':
            updates.append("role = ?")
            params_params.append(request.role)
        if org_id:
            updates.append("org_id = ?")
            params_params.append(org_id)
        params_params.append(result["user_id"])
        db.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params_params)
        db.commit()
    from audit import log_action
    log_action(user["user_id"], "create_user", "admin", f"创建用户 {request.username}，角色: {request.role}")
    return {"message": "用户创建成功", "user_id": result["user_id"]}


@router.get("/admin/users")
async def admin_list_users(request: Request, user: dict = Depends(require_admin)):
    """
    获取用户列表（按组织隔离）。

    权限规则:
      - 超管 + 特定 org_id → 只看该组织用户
      - 超管 + 无 org_id → 看全部用户
      - 普通 admin → 只看自己组织的非超管用户（不能看到或操作超管）
    """
    from db import get_db
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)
    is_super = user["role"] == 'super_admin'
    if is_super and effective_org_id:
        rows = db.execute(
            "SELECT id, username, role, status, org_id, created_at FROM users WHERE org_id = ? ORDER BY id", (effective_org_id,)
        ).fetchall()
    elif is_super:
        rows = db.execute(
            "SELECT id, username, role, status, org_id, created_at FROM users ORDER BY id"
        ).fetchall()
    elif effective_org_id:
        rows = db.execute(
            "SELECT id, username, role, status, org_id, created_at FROM users WHERE org_id = ? AND role != 'super_admin' ORDER BY id", (effective_org_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, username, role, status, org_id, created_at FROM users WHERE role != 'super_admin' ORDER BY id"
        ).fetchall()
    users = []
    for r in rows:
        from auth import get_user_departments
        depts = get_user_departments(r["id"])
        org_name = None
        if r["org_id"]:
            org_row = db.execute("SELECT display_name FROM organizations WHERE id = ?", (r["org_id"],)).fetchone()
            org_name = org_row["display_name"] if org_row else None
        users.append({
            "id": r["id"],
            "username": r["username"],
            "role": r["role"],
            "status": r["status"],
            "org_id": r["org_id"],
            "org_name": org_name,
            "departments": depts,
            "created_at": r["created_at"],
        })
    return {"users": users}


@router.post("/admin/users/{user_id}")
async def admin_manage_user(
    user_id: int,
    action: str = Query(...),
    body: dict = Body(None),
    http_request: Request = None,
    user: dict = Depends(require_admin)
):
    """
    用户管理操作（统一入口，通过 action 参数区分）。

    支持的操作:
      - update_role: 修改用户角色（仅超管，role 取值: super_admin/admin/user）
      - update_org: 修改用户所属组织（仅超管，会自动清空用户部门分配）
      - toggle_status: 启用/禁用用户（切换 active/disabled）
      - update_departments: 修改用户可访问的部门列表（替换模式，非追加）
    """
    from db import get_db
    from audit import log_action
    db = get_db()
    body = body or {}

    if action == "update_role":
        if user["role"] != 'super_admin':
            raise HTTPException(status_code=403, detail="仅超级管理员可修改角色")
        role = body.get("role", "")
        if role not in ('super_admin', 'admin', 'user'):
            raise HTTPException(status_code=400, detail="无效的角色")
        cur = db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        db.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="用户不存在")
        log_action(user["user_id"], "update_user_role", "admin",
                   f"用户ID={user_id}, 新角色={role}")
        return {"status": "success"}

    elif action == "update_org":
        if user["role"] != 'super_admin':
            raise HTTPException(status_code=403, detail="仅超级管理员可修改组织")
        org_id_val = body.get("org_id")
        if not org_id_val:
            raise HTTPException(status_code=400, detail="缺少 org_id")
        org_row = db.execute("SELECT id, display_name FROM organizations WHERE id = ?", (org_id_val,)).fetchone()
        if not org_row:
            raise HTTPException(status_code=400, detail="组织不存在")
        user_row = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="用户不存在")
        db.execute("UPDATE users SET org_id = ? WHERE id = ?", (org_id_val, user_id))
        # 切换组织后清空部门分配，因为旧部门的 dept_id 可能在新组织中不存在
        db.execute("DELETE FROM user_departments WHERE user_id = ?", (user_id,))
        db.commit()
        log_action(user["user_id"], "update_user_org", "admin",
                   f"用户ID={user_id}, 新组织={org_row['display_name']}(ID={org_id_val})")
        return {"status": "success"}

    elif action == "toggle_status":
        effective_org_id = get_effective_org_id(user, http_request)
        if effective_org_id:
            row = db.execute("SELECT status, role FROM users WHERE id = ? AND org_id = ?", (user_id, effective_org_id)).fetchone()
        else:
            row = db.execute("SELECT status, role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        if row["role"] == 'super_admin' and user["role"] != 'super_admin':
            raise HTTPException(status_code=403, detail="无权操作超级管理员")
        new_status = 'disabled' if row["status"] == 'active' else 'active'
        db.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
        db.commit()
        log_action(user["user_id"], "toggle_user_status", "admin",
                   f"用户ID={user_id}, 新状态={new_status}")
        return {"status": "success", "new_status": new_status}

    elif action == "update_departments":
        department_ids = body.get("department_ids", [])
        effective_org_id = get_effective_org_id(user, http_request)
        if effective_org_id:
            row = db.execute("SELECT id FROM users WHERE id = ? AND org_id = ?", (user_id, effective_org_id)).fetchone()
        else:
            row = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        # 校验部门 ID 是否都属于当前组织（防止跨组织越权）
        if effective_org_id and department_ids:
            valid_depts = db.execute(
                f"SELECT id FROM departments WHERE id IN ({','.join('?' * len(department_ids))}) AND org_id = ?",
                list(department_ids) + [effective_org_id]
            ).fetchall()
            valid_ids = {r['id'] for r in valid_depts}
            invalid = [d for d in department_ids if d not in valid_ids]
            if invalid:
                raise HTTPException(status_code=400, detail=f"部门ID {invalid} 不属于当前组织")
        # 替换模式：先清空再重新插入
        db.execute("DELETE FROM user_departments WHERE user_id = ?", (user_id,))
        for dept_id in department_ids:
            db.execute(
                "INSERT OR IGNORE INTO user_departments (user_id, department_id) VALUES (?, ?)",
                (user_id, dept_id)
            )
        db.commit()
        log_action(user["user_id"], "update_user_departments", "admin",
                   f"用户ID={user_id}, 部门IDs={department_ids}")
        return {"status": "success"}

    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


# ============ 部门管理 ============

@router.get("/admin/departments")
async def admin_list_departments(request: Request, user: dict = Depends(require_admin)):
    """
    获取所有部门列表（管理接口，按组织隔离）。

    与 /departments（用户接口）的区别:
      - 管理接口不过滤用户的可访问部门，返回组织下全部部门
      - 包含 org_name 字段，便于超管跨组织查看时识别归属
    """
    from db import get_db
    db = get_db()
    effective_org_id = get_effective_org_id(user, request)
    if effective_org_id:
        rows = db.execute(
            """SELECT d.id, d.name, d.display_name, d.description, d.org_id, d.created_at,
                      o.display_name as org_name
               FROM departments d LEFT JOIN organizations o ON d.org_id = o.id
               WHERE d.org_id = ? ORDER BY d.id""", (effective_org_id,)
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT d.id, d.name, d.display_name, d.description, d.org_id, d.created_at,
                      o.display_name as org_name
               FROM departments d LEFT JOIN organizations o ON d.org_id = o.id
               ORDER BY d.id"""
        ).fetchall()
    return {"departments": [dict(r) for r in rows]}


@router.post("/admin/departments")
async def admin_create_department(
    request_body: CreateDepartmentRequest,
    request: Request,
    user: dict = Depends(require_admin)
):
    """
    创建新部门。

    部门绑定到当前有效组织（admin 自动绑定自己组织，超管通过 header 指定）。
    name 字段: 内部标识（字母/数字），如 "hr"、"sale"
    display_name 字段: 前端显示名称，如 "人事部"、"销售部"
    """
    from db import get_db
    from audit import log_action
    db = get_db()
    org_id = get_effective_org_id(user, request)
    try:
        cur = db.execute(
            "INSERT INTO departments (name, display_name, description, org_id, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
            (request_body.name, request_body.display_name, request_body.description, org_id)
        )
        db.commit()
    except Exception:
        raise HTTPException(status_code=409, detail="部门名称已存在")
    log_action(user["user_id"], "create_department", "admin",
               f"部门={request_body.name} ({request_body.display_name})")
    return {"status": "success", "id": cur.lastrowid}


@router.post("/admin/departments/{dept_id}")
async def admin_manage_department(
    dept_id: int,
    action: str = Query(...),
    body: dict = Body(None),
    http_request: Request = None,
    user: dict = Depends(require_admin)
):
    """
    部门管理操作。

    支持的操作:
      - update: 修改部门的 display_name 和/或 description（部分更新）
      - delete: 删除部门（仅超管，且不能删除 "general" 公共知识库）
    """
    from db import get_db
    from audit import log_action
    db = get_db()

    if action == "update":
        effective_org_id = get_effective_org_id(user, http_request)
        if effective_org_id:
            row = db.execute("SELECT id FROM departments WHERE id = ? AND org_id = ?", (dept_id, effective_org_id)).fetchone()
        else:
            row = db.execute("SELECT id FROM departments WHERE id = ?", (dept_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="部门不存在")
        body = body or {}
        if body.get("display_name"):
            db.execute("UPDATE departments SET display_name = ? WHERE id = ?",
                       (body["display_name"], dept_id))
        if body.get("description") is not None:
            db.execute("UPDATE departments SET description = ? WHERE id = ?",
                       (body["description"], dept_id))
        db.commit()
        log_action(user["user_id"], "update_department", "admin", f"部门ID={dept_id}")
        return {"status": "success"}

    elif action == "delete":
        if user["role"] != 'super_admin':
            raise HTTPException(status_code=403, detail="仅超级管理员可删除部门")
        effective_org_id = get_effective_org_id(user, http_request)
        if effective_org_id:
            row = db.execute("SELECT name FROM departments WHERE id = ? AND org_id = ?", (dept_id, effective_org_id)).fetchone()
        else:
            row = db.execute("SELECT name FROM departments WHERE id = ?", (dept_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="部门不存在")
        if row["name"] == 'general':
            raise HTTPException(status_code=400, detail="不能删除公共知识库部门")
        db.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
        db.commit()
        log_action(user["user_id"], "delete_department", "admin", f"部门={row['name']}")
        return {"status": "success"}

    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


# ============ 组织管理（仅超级管理员） ============

@router.get("/admin/organizations")
async def admin_list_organizations(user: dict = Depends(require_super_admin)):
    """
    获取所有组织列表（仅超管可访问）。

    返回每个组织的:
      - 基本信息（code, display_name, description, status）
      - 邀请码（admin_invite_code, user_invite_code）— 用于新用户注册
      - user_count — 该组织下的用户数
    """
    from db import get_db
    db = get_db()
    rows = db.execute(
        "SELECT id, code, display_name, description, status, admin_invite_code, user_invite_code, created_at FROM organizations ORDER BY id"
    ).fetchall()
    orgs = []
    for r in rows:
        user_count = db.execute("SELECT COUNT(*) as cnt FROM users WHERE org_id = ?", (r["id"],)).fetchone()["cnt"]
        orgs.append({
            "id": r["id"],
            "code": r["code"],
            "display_name": r["display_name"],
            "description": r["description"],
            "status": r["status"],
            "admin_invite_code": r["admin_invite_code"],
            "user_invite_code": r["user_invite_code"],
            "user_count": user_count,
            "created_at": r["created_at"],
        })
    return {"organizations": orgs}


@router.post("/admin/organizations")
async def admin_create_organization(request: CreateOrgRequest, user: dict = Depends(require_super_admin)):
    """
    创建新组织（仅超管）。

    自动行为:
      - 生成 admin_invite_code 和 user_invite_code（8 位随机码）
      - 自动创建 "general" 默认部门（公共知识库）

    code 字段必须全局唯一，用于 ChromaDB 集合命名和文件目录路径。
    """
    from db import get_db
    from audit import log_action
    db = get_db()
    existing = db.execute("SELECT id FROM organizations WHERE code = ?", (request.code,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="组织编码已存在")
    cur = db.execute(
        "INSERT INTO organizations (code, display_name, description, admin_invite_code, user_invite_code, created_at) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
        (request.code, request.display_name, request.description, generate_invite_code(), generate_invite_code())
    )
    db.commit()
    org_id = cur.lastrowid
    # 每个组织默认带一个 public 知识库部门
    db.execute(
        "INSERT INTO departments (name, display_name, description, org_id, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
        ('general', '公共知识库', '全员可访问的公共知识', org_id)
    )
    db.commit()
    log_action(user["user_id"], "create_organization", "admin", f"创建组织 {request.code} ({request.display_name})")
    return {"status": "success", "id": org_id}


@router.post("/admin/organizations/{org_id}")
async def admin_manage_organization(
    org_id: int,
    action: str = Query(...),
    body: dict = Body(None),
    user: dict = Depends(require_super_admin)
):
    """
    组织管理操作（仅超管）。

    支持的操作:
      - update: 修改组织的 display_name/description/status
      - delete: 禁用组织（软删除，设置 status='disabled'，不物理删除数据）
      - regenerate_invite_codes: 重新生成管理员邀请码（用于安全轮换）
    """
    from db import get_db
    from audit import log_action
    db = get_db()

    if action == "update":
        row = db.execute("SELECT id FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="组织不存在")
        body = body or {}
        if body.get("display_name"):
            db.execute("UPDATE organizations SET display_name = ? WHERE id = ?", (body["display_name"], org_id))
        if body.get("description") is not None:
            db.execute("UPDATE organizations SET description = ? WHERE id = ?", (body["description"], org_id))
        if body.get("status") and body["status"] in ('active', 'disabled'):
            db.execute("UPDATE organizations SET status = ? WHERE id = ?", (body["status"], org_id))
        db.commit()
        log_action(user["user_id"], "update_organization", "admin", f"组织ID={org_id}")
        return {"status": "success"}

    elif action == "delete":
        row = db.execute("SELECT code FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="组织不存在")
        if row["code"] == 'default':
            raise HTTPException(status_code=400, detail="不能删除默认组织")
        # 软删除：设为 disabled 而非物理删除，保留历史数据
        db.execute("UPDATE organizations SET status = 'disabled' WHERE id = ?", (org_id,))
        db.commit()
        log_action(user["user_id"], "delete_organization", "admin", f"禁用组织={row['code']}")
        return {"status": "success"}

    elif action == "regenerate_invite_codes":
        row = db.execute("SELECT id FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="组织不存在")
        new_admin_code = generate_invite_code()
        db.execute(
            "UPDATE organizations SET admin_invite_code = ? WHERE id = ?",
            (new_admin_code, org_id)
        )
        db.commit()
        log_action(user["user_id"], "regenerate_invite_codes", "admin", f"组织ID={org_id}")
        updated = db.execute("SELECT admin_invite_code, user_invite_code FROM organizations WHERE id = ?", (org_id,)).fetchone()
        return {
            "status": "success",
            "admin_invite_code": new_admin_code,
            "user_invite_code": updated["user_invite_code"]
        }

    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


# ============ 本公司设置 ============

@router.get("/admin/my-org")
async def admin_get_my_org(request: Request, user: dict = Depends(require_admin)):
    """
    获取当前管理员所属组织的详细信息。

    用于"本公司设置"页面，显示和编辑组织基本信息。
    返回 user_invite_code 用于分享给新用户注册。
    """
    from db import get_db
    db = get_db()
    org_id = get_effective_org_id(user, request)
    if not org_id:
        raise HTTPException(status_code=400, detail="未分配组织")
    row = db.execute(
        "SELECT id, code, display_name, description, status, user_invite_code FROM organizations WHERE id = ?",
        (org_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="组织不存在")
    return dict(row)


@router.post("/admin/my-org")
async def admin_manage_my_org(
    action: str = Query(...),
    body: dict = Body(None),
    request: Request = None,
    user: dict = Depends(require_admin)
):
    """
    本公司设置操作。

    支持的操作:
      - update: 修改公司显示名称（display_name）
      - regenerate_user_invite_code: 重新生成用户邀请码（旧码立即失效）

    仅操作管理员自己所属的组织，不需要传 org_id。
    """
    from db import get_db
    from audit import log_action
    db = get_db()
    org_id = get_effective_org_id(user, request)
    if not org_id:
        raise HTTPException(status_code=400, detail="未分配组织")

    if action == "update":
        body = body or {}
        display_name = (body.get("display_name") or "").strip()
        if display_name:
            db.execute("UPDATE organizations SET display_name = ? WHERE id = ?", (display_name, org_id))
            db.commit()
            log_action(user["user_id"], "update_my_org", "admin", f"修改公司名称={display_name}")
        return {"status": "success"}

    elif action == "regenerate_user_invite_code":
        new_code = generate_invite_code()
        db.execute("UPDATE organizations SET user_invite_code = ? WHERE id = ?", (new_code, org_id))
        db.commit()
        log_action(user["user_id"], "regenerate_user_invite_code", "admin", f"组织ID={org_id}")
        return {"status": "success", "user_invite_code": new_code}

    else:
        raise HTTPException(status_code=400, detail=f"未知操作: {action}")


# ============ 审计日志 ============

@router.get("/audit/logs")
async def get_audit_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    action: Optional[str] = None,
    user: dict = Depends(require_admin)
):
    """
    获取审计日志（管理员专用，支持分页和按操作类型筛选）。

    返回的每条日志包含:
      - action_label: 操作的中文名称（如 "用户登录"、"智能问答"）
      - username: 操作人用户名
      - detail: 操作详情（JSON 字符串）
      - ip_address: 操作来源 IP

    按组织隔离，admin 只能看到自己组织的日志。
    """
    from db import get_db
    db = get_db()
    offset = (page - 1) * page_size
    effective_org_id = get_effective_org_id(user, request)

    conditions = []
    params = []
    if action:
        conditions.append("action = ?")
        params.append(action)
    if effective_org_id:
        conditions.append("org_id = ?")
        params.append(effective_org_id)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = db.execute(
        f"""SELECT id, user_id, username, action, resource, detail, ip_address, created_at
            FROM audit_logs {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?""",
        params + [page_size, offset]
    ).fetchall()
    total_row = db.execute(
        f"SELECT COUNT(*) as cnt FROM audit_logs {where_clause}", params
    ).fetchone()

    from audit import get_action_label
    logs_list = []
    for r in rows:
        d = dict(r)
        d["action_label"] = get_action_label(r["action"])  # 附加中文标签
        logs_list.append(d)

    return {
        "logs": logs_list,
        "total": total_row["cnt"],
        "page": page,
        "page_size": page_size,
    }
