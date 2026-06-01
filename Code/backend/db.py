"""
数据库模块 — SQLite 连接管理与表初始化。

设计要点:
  - 单例连接: 全局一个 sqlite3.Connection，所有请求复用
  - WAL 模式: Write-Ahead Logging，允许并发读写（读不阻塞写）
  - check_same_thread=False: FastAPI 多线程环境下，同一连接可在不同线程使用
  - row_factory=sqlite3.Row: 查询结果用列名访问（row["column"]），不用索引

启动流程:
  1. main.py startup 事件调用 init_db()
  2. init_db() 按顺序执行: 建表 → 迁移 → 默认数据
  3. 迁移函数检查字段是否存在，不存在才 ALTER TABLE ADD COLUMN
  4. 兼容旧版数据库升级，不会重复创建或丢失数据

表结构概览:
  - organizations: 组织（多租户顶层维度）
  - users: 用户（绑定 org_id）
  - auth_tokens: 登录 token（24h 过期）
  - departments: 部门（绑定 org_id）
  - user_departments: 用户-部门多对多关联
  - chat_sessions: 对话会话（绑定 user + org）
  - messages: 对话消息（绑定 session）
  - audit_logs: 审计日志（所有关键操作）
  - analysis_tasks: 文件分析任务
"""

import sqlite3
import os
from pathlib import Path

import config

_conn: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """
    返回持久化的 SQLite 连接（懒初始化，首次调用时创建）。

    配置:
      - WAL 模式: 写入不阻塞读取，适合 Web 服务场景
      - foreign_keys=ON: 启用外键约束（级联删除等）
      - check_same_thread=False: 允许跨线程使用同一连接
    """
    global _conn
    if _conn is None:
        db_path = config.DB_PATH
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db():
    """
    初始化数据库 — 应用启动时调用一次。

    执行顺序:
      1. 建表（CREATE TABLE IF NOT EXISTS，幂等）
      2. 迁移（为旧表添加新字段，兼容升级）
      3. 默认数据（组织、部门、管理员账号）

    所有操作都是幂等的，多次调用不会出错。
    """
    db = get_db()
    db.executescript("""
        -- 销售组织表（顶层维度）
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'disabled')),
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 用户表
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('super_admin', 'admin', 'user')),
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'disabled')),
            org_id INTEGER REFERENCES organizations(id),
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 部门表（每家公司独立部门，同名可属于不同公司）
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            org_id INTEGER REFERENCES organizations(id),
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 用户-部门关联表（多对多）
        CREATE TABLE IF NOT EXISTS user_departments (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, department_id)
        );

        -- 知识库表
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            kb_type TEXT NOT NULL DEFAULT 'company' CHECK(kb_type IN ('company', 'department', 'user')),
            department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL,
            owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            org_id INTEGER REFERENCES organizations(id),
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 对话会话表
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department TEXT NOT NULL DEFAULT 'general',
            org_id INTEGER REFERENCES organizations(id),
            title TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (datetime('now','localtime')),
            updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 消息表
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            sources TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 审计日志表
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            username TEXT DEFAULT '',
            action TEXT NOT NULL,
            resource TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            org_id INTEGER REFERENCES organizations(id),
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );

        -- 文件分析任务表
        CREATE TABLE IF NOT EXISTS analysis_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            department TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
            result_json TEXT,
            error_message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
        );
    """)
    db.commit()

    # 迁移：为旧版 users 表添加新字段（如果不存在）
    _migrate_users_table(db)

    # 迁移：为 chat_sessions 表添加 is_deleted 字段
    _migrate_sessions_table(db)

    # 迁移：添加组织相关字段
    _migrate_add_org(db)

    # 迁移：为 auth_tokens 表添加 expires_at 字段
    _migrate_auth_tokens(db)

    # 初始化默认组织
    _init_default_org(db)

    # 初始化默认部门数据
    _init_default_departments(db)

    # 初始化默认管理员账号
    _init_default_admin(db)

    print("[数据库] 初始化完成")


def _migrate_users_table(db):
    """
    兼容旧版数据库：为 users 表添加 role 和 status 字段。

    迁移策略: 检查字段是否存在 → 不存在则 ALTER TABLE ADD COLUMN。
    旧数据自动获得默认值: role='user', status='active'。
    """
    try:
        cursor = db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'role' not in columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
            db.commit()
            print("[数据库迁移] users 表添加 role 字段")
        if 'status' not in columns:
            db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            db.commit()
            print("[数据库迁移] users 表添加 status 字段")
    except Exception as e:
        print(f"[数据库迁移] 跳过: {e}")


def _migrate_sessions_table(db):
    """
    为 chat_sessions 表添加 is_deleted、title、departments、org_id 字段。

    is_deleted: 软删除标记（0=正常, 1=已删除），管理员仍可查看已删除会话
    title: 用户自定义会话标题
    departments: JSON 数组，会话关联的所有部门历史
    org_id: 组织隔离字段
    """
    try:
        cursor = db.execute("PRAGMA table_info(chat_sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'is_deleted' not in columns:
            db.execute("ALTER TABLE chat_sessions ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")
            db.commit()
            print("[数据库迁移] chat_sessions 表添加 is_deleted 字段")
        if 'title' not in columns:
            db.execute("ALTER TABLE chat_sessions ADD COLUMN title TEXT DEFAULT ''")
            db.commit()
            print("[数据库迁移] chat_sessions 表添加 title 字段")
        if 'departments' not in columns:
            db.execute("ALTER TABLE chat_sessions ADD COLUMN departments TEXT DEFAULT ''")
            db.commit()
            print("[数据库迁移] chat_sessions 表添加 departments 字段")
        if 'org_id' not in columns:
            db.execute("ALTER TABLE chat_sessions ADD COLUMN org_id INTEGER REFERENCES organizations(id)")
            db.commit()
            print("[数据库迁移] chat_sessions 表添加 org_id 字段")
    except Exception as e:
        print(f"[数据库迁移] 跳过: {e}")


def _migrate_auth_tokens(db):
    """
    为 auth_tokens 表添加 expires_at 字段。

    旧 token 的 expires_at 为 NULL，在 get_current_user 中会检查并处理。
    新 token 创建时自动设置 24h 过期时间。
    """
    try:
        cursor = db.execute("PRAGMA table_info(auth_tokens)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'expires_at' not in columns:
            db.execute("ALTER TABLE auth_tokens ADD COLUMN expires_at TIMESTAMP")
            db.commit()
            print("[数据库迁移] auth_tokens 表添加 expires_at 字段")
    except Exception as e:
        print(f"[数据库迁移] 跳过: {e}")


def _migrate_add_org(db):
    """
    为现有表添加 org_id 字段（兼容旧数据库升级到多租户版本）。

    处理内容:
      1. users、departments、audit_logs、knowledge_bases 添加 org_id
      2. organizations 添加 admin_invite_code、user_invite_code
      3. 移除 departments.name 的 UNIQUE 约束（允许不同组织有同名部门）
         - SQLite 不支持直接 DROP CONSTRAINT，需重建表
         - 重建时保留所有数据
    """
    try:
        # users 表
        cursor = db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'org_id' not in columns:
            db.execute("ALTER TABLE users ADD COLUMN org_id INTEGER REFERENCES organizations(id)")
            db.commit()
            print("[数据库迁移] users 表添加 org_id 字段")

        # departments 表
        cursor = db.execute("PRAGMA table_info(departments)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'org_id' not in columns:
            db.execute("ALTER TABLE departments ADD COLUMN org_id INTEGER REFERENCES organizations(id)")
            db.commit()
            print("[数据库迁移] departments 表添加 org_id 字段")

        # 移除 departments.name 的 UNIQUE 约束 — 允许不同组织有同名部门
        try:
            indexes = db.execute("PRAGMA index_list(departments)").fetchall()
            has_unique_name = False
            for idx in indexes:
                if idx[2] == 1:  # unique=1
                    idx_info = db.execute(f"PRAGMA index_info({idx[1]})").fetchall()
                    if len(idx_info) == 1:
                        col_info = db.execute("PRAGMA table_info(departments)").fetchall()
                        col_names = {row[0]: row[1] for row in col_info}
                        if col_names.get(idx_info[0][1]) == 'name':
                            has_unique_name = True
                            break
            if has_unique_name:
                # SQLite 无法直接删除 UNIQUE 约束，需通过重建表来实现
                db.execute("PRAGMA foreign_keys = OFF")
                db.execute("""CREATE TABLE IF NOT EXISTS departments_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    org_id INTEGER REFERENCES organizations(id),
                    created_at TIMESTAMP DEFAULT (datetime('now','localtime'))
                )""")
                db.execute("INSERT INTO departments_new SELECT * FROM departments")
                db.execute("DROP TABLE departments")
                db.execute("ALTER TABLE departments_new RENAME TO departments")
                db.execute("PRAGMA foreign_keys = ON")
                db.commit()
                print("[数据库迁移] 重建 departments 表，移除 name UNIQUE 约束")
        except Exception as idx_err:
            print(f"[数据库迁移] 索引处理跳过: {idx_err}")

        # audit_logs 表
        cursor = db.execute("PRAGMA table_info(audit_logs)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'org_id' not in columns:
            db.execute("ALTER TABLE audit_logs ADD COLUMN org_id INTEGER REFERENCES organizations(id)")
            db.commit()
            print("[数据库迁移] audit_logs 表添加 org_id 字段")

        # knowledge_bases 表
        cursor = db.execute("PRAGMA table_info(knowledge_bases)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'org_id' not in columns:
            db.execute("ALTER TABLE knowledge_bases ADD COLUMN org_id INTEGER REFERENCES organizations(id)")
            db.commit()
            print("[数据库迁移] knowledge_bases 表添加 org_id 字段")

        # organizations 表添加邀请码字段
        cursor = db.execute("PRAGMA table_info(organizations)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'admin_invite_code' not in columns:
            db.execute("ALTER TABLE organizations ADD COLUMN admin_invite_code TEXT")
            db.commit()
            print("[数据库迁移] organizations 表添加 admin_invite_code 字段")
        if 'user_invite_code' not in columns:
            db.execute("ALTER TABLE organizations ADD COLUMN user_invite_code TEXT")
            db.commit()
            print("[数据库迁移] organizations 表添加 user_invite_code 字段")
    except Exception as e:
        print(f"[数据库迁移] 跳过: {e}")


def _init_default_org(db):
    """
    初始化默认组织 "default"。

    自动行为:
      1. 创建 default 组织（如不存在）
      2. 为没有邀请码的组织补充生成邀请码
      3. 将无组织的旧数据关联到默认组织（兼容旧版升级）
      4. 为所有组织补充 "general" 公共知识库部门
    """
    import string, random

    def _gen_code():
        return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    row = db.execute("SELECT id FROM organizations WHERE code = 'default'").fetchone()
    if not row:
        db.execute(
            "INSERT INTO organizations (code, display_name, description, admin_invite_code, user_invite_code, created_at) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
            ('default', '默认公司', '系统默认组织', _gen_code(), _gen_code())
        )
        db.commit()
        print("[数据库] 创建默认组织: default")

    # 为没有邀请码的组织补充生成
    orgs_without_codes = db.execute(
        "SELECT id FROM organizations WHERE admin_invite_code IS NULL OR user_invite_code IS NULL"
    ).fetchall()
    for org in orgs_without_codes:
        db.execute(
            "UPDATE organizations SET admin_invite_code = COALESCE(admin_invite_code, ?), user_invite_code = COALESCE(user_invite_code, ?) WHERE id = ?",
            (_gen_code(), _gen_code(), org["id"])
        )
    if orgs_without_codes:
        db.commit()
        print(f"[数据库] 为 {len(orgs_without_codes)} 个组织补充邀请码")

    # 将旧数据关联到默认组织（兼容旧版无组织字段的数据）
    org = db.execute("SELECT id FROM organizations WHERE code = 'default'").fetchone()
    org_id = org["id"] if org else 1
    db.execute("UPDATE users SET org_id = ? WHERE org_id IS NULL", (org_id,))
    db.execute("UPDATE departments SET org_id = ? WHERE org_id IS NULL", (org_id,))
    db.execute("UPDATE chat_sessions SET org_id = ? WHERE org_id IS NULL", (org_id,))
    db.execute("UPDATE audit_logs SET org_id = ? WHERE org_id IS NULL", (org_id,))
    db.execute("UPDATE knowledge_bases SET org_id = ? WHERE org_id IS NULL", (org_id,))
    db.commit()

    # 为所有缺少 general 部门的组织补充创建
    all_orgs = db.execute("SELECT id FROM organizations").fetchall()
    for o in all_orgs:
        has_general = db.execute(
            "SELECT id FROM departments WHERE name = 'general' AND org_id = ?", (o["id"],)
        ).fetchone()
        if not has_general:
            db.execute(
                "INSERT INTO departments (name, display_name, description, org_id, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                ('general', '公共知识库', '全员可访问的公共知识', o["id"])
            )
    db.commit()

def _init_default_departments(db):
    """
    初始化默认部门（绑定到 default 组织）。

    预设部门:
      - general: 公共知识库（所有人可访问）
      - hr: 人事部（人事制度与规范）
      - tech: 技术部（技术文档与规范）
      - finance: 财务部（财务制度与流程）
    """
    org = db.execute("SELECT id FROM organizations WHERE code = 'default'").fetchone()
    org_id = org["id"] if org else 1
    default_depts = [
        ('general', '公共知识库', '全员可访问的公共知识'),
        ('hr', '人事部', '人事制度与规范'),
        ('tech', '技术部', '技术文档与规范'),
        ('finance', '财务部', '财务制度与流程'),
    ]
    for name, display_name, desc in default_depts:
        existing = db.execute(
            "SELECT id FROM departments WHERE name = ? AND org_id = ?", (name, org_id)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO departments (name, display_name, description, org_id, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                (name, display_name, desc, org_id)
            )
    db.commit()


def _init_default_admin(db):
    """
    初始化默认超级管理员账号。

    规则:
      - 如果已存在 super_admin 用户 → 跳过
      - 如果存在 username='admin' 但角色不是 super_admin → 升级为 super_admin
      - 如果不存在 → 创建 admin/admin123

    默认密码仅用于初始部署，生产环境应立即修改。
    """
    org = db.execute("SELECT id FROM organizations WHERE code = 'default'").fetchone()
    org_id = org["id"] if org else 1
    row = db.execute("SELECT id FROM users WHERE role = 'super_admin'").fetchone()
    if not row:
        existing = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if existing:
            db.execute("UPDATE users SET role = 'super_admin', org_id = ? WHERE username = 'admin'", (org_id,))
            db.commit()
            print("[数据库] 已将 admin 用户升级为超级管理员")
        else:
            from auth import hash_password
            pw_hash, salt = hash_password('admin123')
            db.execute(
                "INSERT INTO users (username, password_hash, salt, role, org_id, created_at) VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))",
                ('admin', pw_hash, salt, 'super_admin', org_id)
            )
            db.commit()
            print("[数据库] 创建默认管理员: admin / admin123")
