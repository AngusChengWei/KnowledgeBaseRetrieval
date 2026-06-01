"""
会话管理模块 — 基于 SQLite 的多用户会话持久化。

会话（Session）是承载多轮对话的核心数据结构:
  - 每个会话绑定一个 user_id 和 org_id（多租户隔离）
  - 每个会话有一个默认 department（当前活跃的知识库部门）
  - departments 字段是 JSON 数组，记录会话使用过的所有部门历史

消息存储:
  - messages 表按 session_id 关联，role 为 'user' 或 'assistant'
  - sources 字段存储 AI 回答的引用来源（JSON 字符串）

线程安全:
  - update_session_department 使用 threading.Lock 保护
  - 并发请求修改同一会话的 departments 时不会出现竞态条件
"""

import uuid
import json
import threading

import config
from db import get_db

# 会话更新锁 — 防止 departments 字段的 "读取→修改→写回" 竞态
_session_lock = threading.Lock()


def create_session(db, user_id: int, department: str = "general", org_id: int = None) -> str:
    """
    创建新会话，返回 UUID 格式的 session_id。

    初始 departments 列表仅包含创建时的 department。
    前端将此 session_id 用于后续 /ask 请求。
    """
    session_id = str(uuid.uuid4())
    departments_json = json.dumps([department], ensure_ascii=False)
    db.execute(
        "INSERT INTO chat_sessions (id, user_id, department, departments, org_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))",
        (session_id, user_id, department, departments_json, org_id)
    )
    db.commit()
    print(f"[会话] 创建新会话: {session_id} (user_id={user_id}, dept={department}, org_id={org_id})")
    return session_id


def session_exists(session_id: str) -> bool:
    """检查会话是否存在"""
    db = get_db()
    row = db.execute("SELECT 1 FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return row is not None


def get_history(session_id: str) -> list[dict]:
    """
    获取会话的对话历史（最近 N 轮）。

    返回格式: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    按时间正序排列（reversed 反转 DB 的 DESC 查询结果）。

    用于 LLM 的多轮对话上下文，限制为 MAX_HISTORY_ROUNDS 轮。
    """
    db = get_db()
    max_messages = config.MAX_HISTORY_ROUNDS * 2  # user + assistant 各算一条
    rows = db.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, max_messages)
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_message(db, session_id: str, role: str, content: str, sources: str = None):
    """
    向会话添加一条消息。

    同时更新会话的 updated_at 时间戳，用于前端按最近活跃排序。
    sources 仅用于 assistant 消息，存储引用来源的 JSON 字符串。
    """
    db.execute(
        "INSERT INTO messages (session_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
        (session_id, role, content, sources)
    )
    # 更新会话时间戳
    db.execute("UPDATE chat_sessions SET updated_at = datetime('now','localtime') WHERE id = ?", (session_id,))
    db.commit()


def update_session_department(db, session_id: str, department: str):
    """
    更新会话的当前知识库部门，并追加到历史部门列表。

    线程安全: 使用 _session_lock 保护读取→修改→写回整个操作，
    防止并发请求导致 departments 数据丢失。

    用途: 用户在对话中切换部门检索时，记录所有使用过的部门。
    """
    with _session_lock:
        db.execute(
            "UPDATE chat_sessions SET department = ? WHERE id = ?",
            (department, session_id)
        )
        # 读取现有 departments 列表
        row = db.execute("SELECT departments FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        existing = []
        if row and row["departments"]:
            try:
                existing = json.loads(row["departments"])
            except (json.JSONDecodeError, TypeError):
                existing = []
        # 追加新部门（去重）
        if department not in existing:
            existing.append(department)
            db.execute(
                "UPDATE chat_sessions SET departments = ? WHERE id = ?",
                (json.dumps(existing, ensure_ascii=False), session_id)
            )
        db.commit()


def rename_session(db, session_id: str, user_id: int, title: str) -> bool:
    """
    重命名会话（验证所有权）。

    返回 True 表示重命名成功，False 表示会话不存在或不属于该用户。
    """
    cur = db.execute(
        "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
        (title.strip(), session_id, user_id)
    )
    db.commit()
    return cur.rowcount > 0


def list_user_sessions(db, user_id: int, org_id: int = None) -> list[dict]:
    """
    列出用户的会话列表（排除已删除的）。

    按 updated_at 降序，最近活跃的会话在前。
    org_id 用于超管查看特定组织的会话。
    """
    if org_id:
        rows = db.execute(
            """SELECT id, department, departments, title, created_at, updated_at
               FROM chat_sessions
               WHERE user_id = ? AND org_id = ? AND is_deleted = 0
               ORDER BY updated_at DESC""",
            (user_id, org_id)
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT id, department, departments, title, created_at, updated_at
               FROM chat_sessions
               WHERE user_id = ? AND is_deleted = 0
               ORDER BY updated_at DESC""",
            (user_id,)
        ).fetchall()
    result = []
    for r in rows:
        depts = []
        if r["departments"]:
            try:
                depts = json.loads(r["departments"])
            except (json.JSONDecodeError, TypeError):
                depts = []
        if not depts:
            depts = [r["department"]]
        result.append({
            "session_id": r["id"],
            "department": r["department"],
            "departments": depts,
            "title": r["title"] or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        })
    return result


def get_session_messages(db, session_id: str) -> list[dict]:
    """
    获取指定会话的全部消息（按时间正序）。

    返回包含 sources 原始 JSON 字符串，由调用方解析。
    """
    rows = db.execute(
        "SELECT role, content, sources, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "sources": r["sources"],
            "created_at": r["created_at"]
        }
        for r in rows
    ]


def delete_session(db, session_id: str, user_id: int) -> bool:
    """
    软删除会话 — 设置 is_deleted=1，不物理删除数据。

    管理员仍可通过管理后台查看已删除会话的消息历史。
    返回 True 表示删除成功。
    """
    cur = db.execute(
        "UPDATE chat_sessions SET is_deleted = 1 WHERE id = ? AND user_id = ?",
        (session_id, user_id)
    )
    db.commit()
    return cur.rowcount > 0


def get_session_owner(session_id: str) -> int | None:
    """
    获取会话的所有者 user_id。

    用于权限校验：确保只有会话所有者能查看和操作自己的会话。
    返回 None 表示会话不存在。
    """
    db = get_db()
    row = db.execute("SELECT user_id FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    return row["user_id"] if row else None
