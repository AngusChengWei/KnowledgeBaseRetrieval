# 任务：修复真实 Bug 清单

## 任务说明

这份清单整理了项目中**真实存在、可复现、影响用户**的 bug。每个 bug 都标注了：
- 严重程度（🔴高 / 🟡中 / 🟢低）
- 难度（⭐⭐⭐⭐⭐ 5星制）
- 适合程度（✅ 适合 / ⚠️ 需带教指导 / ❌ 不适合）

**推荐顺序**：按"难度由低到高 + 影响由大到小"排序，让先建立信心。

---

## 🌟 第一批：简单 Bug（练手用，1-2 天）

### Bug 1: Login 页面图标不显示 🔴 ⭐ ✅

**位置**: [Code/ai-assistant/src/views/Login.vue:23,33,44,53](../Code/ai-assistant/src/views/Login.vue#L23)

**现象**: 登录页的用户名、密码、邀请码输入框前面应该有图标（👤🔒🎫），但实际什么都没有。

**原因**: Element Plus 2.x 的 `prefix-icon` 属性需要传**组件引用**，但代码传的是**字符串**。

```vue
<!-- ❌ 错误写法（当前代码）-->
<el-input prefix-icon="User" />

<!-- ✅ 正确写法 -->
<script setup>
import { User, Lock, Ticket } from '@element-plus/icons-vue'
</script>
<el-input :prefix-icon="User" />
```

**参考**: 项目里的 [SmartQA.vue](../Code/ai-assistant/src/views/chat/SmartQA.vue) 写法是正确的，可以照着改。

**复现**: 打开 [http://localhost:5173/login](http://localhost:5173/login)，对比改前改后图标是否显示。

**学到的**: Vue 3 props 类型、Element Plus 图标按需引入。

---

### Bug 2: 401 错误用 alert() 阻塞页面 🟡 ⭐⭐ ✅

**位置**: [Code/ai-assistant/src/api/index.js:47-58](../Code/ai-assistant/src/api/index.js#L47)

**现象**: Token 过期时，浏览器弹出原生 `alert()` 对话框（丑且阻塞），然后整个页面 `window.location.href = '/'` 强制刷新（丢失任何未保存的状态）。

**额外问题**: 如果用户进入管理页面同时发起多个请求（如加载用户列表 + 部门列表 + 组织列表），全部 401 会**连续弹出 3 个 alert**，体验极差。

**修复方向**:
1. 用 Element Plus 的 `ElMessage.warning()` 替代 `alert()`
2. 用 `router.push('/login')` 替代 `window.location.href = '/'`
3. 加防抖：避免短时间内多次弹窗

**示例**:
```javascript
import { ElMessage } from 'element-plus'
import router from '@/router'

let isRedirecting = false  // 防抖标志

if (error.response?.status === 401) {
  localStorage.removeItem('ai_assistant_token')
  if (!isRedirecting && !window.location.pathname.includes('/login')) {
    isRedirecting = true
    ElMessage.warning('登录已过期，请重新登录')
    router.push('/login').finally(() => {
      setTimeout(() => { isRedirecting = false }, 1000)
    })
  }
}
```

**学到的**: SPA 路由 vs 浏览器跳转的区别、UX 一致性、防抖技巧。

---

### Bug 3: pdf_generator.py 冗余的 except 子句 🟢 ⭐ ✅

**位置**: [Code/backend/pdf_generator.py:37](../Code/backend/pdf_generator.py#L37)

**现象**: `except (FileNotFoundError, subprocess.TimeoutExpired, Exception):` 这种写法有问题。因为 `Exception` 已经覆盖了前两个具体异常类型，前两个写了等于没写。

**修复**: 要么只用 `Exception`，要么只列具体异常：
```python
# 方案A：只捕获具体异常（推荐）
except (FileNotFoundError, subprocess.TimeoutExpired):

# 方案B：兜底捕获所有（如果确实想这样）
except Exception:
```

**学到的**: Python 异常类继承体系。

---

### Bug 4: 删除无用的导入 🟢 ⭐ ✅

涉及 3 处：

| 位置 | 问题 |
|------|------|
| [Code/backend/auth.py:23](../Code/backend/auth.py#L23) | `from functools import wraps` 导入但从未使用 |
| [Code/backend/url_loader.py:515](../Code/backend/url_loader.py#L515) | except 块里 `import traceback` 后没用它 |
| [Code/backend/config.py:93-99](../Code/backend/config.py#L93-L99) | `_DEFAULT_DEPARTMENTS` 注释说"已废弃"，确认无人引用后可删 |

**任务要求**: 用 IDE 的"查找引用"功能确认真的没人用，再删除。学会**安全删除**的思维。

---

## 🌟 第二批：中等难度（理解业务，3-5 天）

### Bug 5: 管理员无法创建用户 🔴 ⭐⭐ ✅

**位置**: [Code/backend/routes/admin.py:151](../Code/backend/routes/admin.py#L151) 附近

**现象**: 管理员在用户管理页点击"新增用户"提交后，后端返回 400 错误"请填写邀请码"。**整个管理员创建用户功能完全无法使用**。

**根本原因**:

[`admin_create_user`](../Code/backend/routes/admin.py) 调用了 `register_user(request.username, request.password)`，但没有传 `invite_code` 参数。

而 [`auth.py:87-88`](../Code/backend/auth.py#L87) 强制要求邀请码：
```python
if not invite_code or not invite_code.strip():
    raise HTTPException(status_code=400, detail="请填写邀请码")
```

**复现**:
1. 用 admin / admin123 登录
2. 进入"用户管理"页面
3. 点击"新增用户"，填写用户名密码，提交
4. 看到错误："请填写邀请码"

**修复思路**（两个方案选一个）：

**方案A**：让 `register_user` 接受一个内部模式参数
```python
def register_user(username, password, invite_code=None, _internal_org_id=None):
    if _internal_org_id is None:  # 外部调用必须有邀请码
        if not invite_code or not invite_code.strip():
            raise HTTPException(400, "请填写邀请码")
        # ... 邀请码逻辑
        org_id = ...
    else:
        # 内部管理员调用：直接指定 org_id
        org_id = _internal_org_id
    # ... 后续插入逻辑
```

**方案B**（更推荐）：管理员创建用户不复用 `register_user`，直接写专用函数

新建 `auth.py` 中的 `admin_create_user_directly(username, password, role, org_id)`，绕过邀请码逻辑直接插入。

**学到的**: 区分"用户自助注册"和"管理员创建用户"是两种不同的业务流程，不应该硬塞到一个函数里。

---

### Bug 6: 超级管理员可以禁用自己（自锁定） 🔴 ⭐⭐ ✅

**位置**: 
- 后端：[Code/backend/routes/admin.py:286-301](../Code/backend/routes/admin.py#L286) `toggle_status` action
- 后端：[Code/backend/routes/admin.py:252-264](../Code/backend/routes/admin.py#L252) `update_role` action  
- 前端：[Code/ai-assistant/src/views/admin/Users.vue:81-88](../Code/ai-assistant/src/views/admin/Users.vue#L81)

**现象**: 超级管理员可以点击自己那一行的"禁用"按钮把自己禁用，或者把自己的角色改成 user。下次请求立即被踢出系统，**且没人能恢复**（除非有另一个超管，或者手动改数据库）。

**复现**:
1. 用 super_admin 登录
2. 在用户管理页面找到自己
3. 点击"禁用"按钮
4. 退出登录
5. 再尝试登录 → 失败"账号已被禁用"
6. **系统失控**

**修复**:

后端校验（必须）：
```python
# admin_manage_user 函数里
if user_id == user["user_id"]:  # 操作自己
    if action == "toggle_status":
        raise HTTPException(400, "不能禁用自己的账号")
    if action == "update_role" and body.get("role") != "super_admin":
        raise HTTPException(400, "不能降级自己的角色")
```

前端禁用按钮（UX 优化）：
```vue
<el-button
  :disabled="row.id === authStore.user?.user_id"
  @click="toggleStatus(row)"
>
  {{ row.status === 'active' ? '禁用' : '启用' }}
</el-button>
```

**学到的**: 权限设计中的"防自杀"原则、前后端双重校验的重要性。

---

### Bug 7: 转移组织后用户仍然是禁用状态 🟡 ⭐⭐ ✅

**位置**: [Code/backend/routes/admin.py:266-284](../Code/backend/routes/admin.py#L266)

**现象**: 场景如下——超管把一个组织设为"禁用"后（此时该组织下的所有用户都无法登录，因为 `_check_org_active` 会拦截），超管决定把这些用户转移到另一个生效中的组织。使用修改用户时的"转移组织"操作成功后，用户的归属组织已经变了，但**还是登录不了**。

**根本原因**: [`update_org`](../Code/backend/routes/admin.py#L278) 只更新了 `org_id`，没有把用户自己的 `status` 重置为 `active`。

```python
# 当前代码 — 只改组织，不改状态
db.execute("UPDATE users SET org_id = ? WHERE id = ?", (org_id_val, user_id))
db.execute("DELETE FROM user_departments WHERE user_id = ?", (user_id,))
```

问题是：把用户从已禁用的组织转移到新组织，本质上是一种**激活操作**（恢复用户在新组织中的工作能力）。但代码只改了归属组织，没有把用户的个人状态也恢复。

**复现**:

1. 创建组织 B，把组织 B 禁用（`organizations.status = 'disabled'`）
2. 组织 B 下的用户 A（`users.status = 'active'`）无法登录（`_check_org_active` 报 403）
3. 超管在用户管理页点击"转移组织"，把用户 A 移到组织 C（活跃）
4. 操作成功，但检查用户 A 的 `status` 字段——它没有被重置为 `active`！它之前是什么现在还是什么

**修复**: 在 `update_org` 里加上状态重置：

```python
elif action == "update_org":
    ...
    db.execute(
        "UPDATE users SET org_id = ?, status = 'active' WHERE id = ?",
        (org_id_val, user_id)
    )
    #                 ^^^^^^^^^^^^^^^^^ 新增：用户移到新组织时自动激活
    db.execute("DELETE FROM user_departments WHERE user_id = ?", (user_id,))
    db.commit()
```

这样用户移到新组织后会自动激活，如果超管不需要用户使用，可以再去手动禁用。

**学到的**: 状态一致性——当实体的"环境"（组织）改变时，其状态是否需要自动归位？这是一个常见的设计问题。

---

### Bug 8: 组织被禁用后用户卡死 🔴 ⭐⭐ ✅

**位置**: [Code/ai-assistant/src/api/index.js:47-58](../Code/ai-assistant/src/api/index.js#L47)

**现象**:
1. 用户 A 已登录正在使用
2. 超管禁用了用户 A 的组织
3. 用户 A 任何操作都返回 **403**（不是 401），错误信息"所属组织已被禁用"
4. 前端 axios 拦截器**只处理 401**，对 403 没反应
5. 用户 A 看到一堆错误弹窗，但页面不跳转、无法重新登录、**完全卡死**
6. 只能手动清 localStorage 才能恢复

**修复**: 拦截 403 中包含"禁用"关键字的错误，引导用户重新登录。

```javascript
if (error.response?.status === 403) {
  const detail = error.response.data?.detail || ''
  if (detail.includes('禁用') || detail.includes('已被')) {
    localStorage.removeItem('ai_assistant_token')
    ElMessage.warning(detail)
    router.push('/login')
  }
}
```

**复现**:
1. 用 admin（属于组织 X）登录
2. 用 super_admin 在另一个浏览器禁用组织 X
3. 回到 admin 浏览器点任意按钮
4. 看到错误弹窗但页面不动

**学到的**: HTTP 状态码语义、错误恢复设计。

---

### Bug 9: 审计日志的用户名搜索完全错误 🔴 ⭐⭐ ✅

**位置**: [Code/ai-assistant/src/views/admin/AuditLog.vue:85-92](../Code/ai-assistant/src/views/admin/AuditLog.vue#L85)

**现象**:
1. 审计日志页面共 120 条记录，分 6 页
2. 用户在搜索框输入"admin"
3. 期望：显示所有用户名包含 "admin" 的日志
4. 实际：
   - 顶部显示"共 120 条"（错误，应该是过滤后的数量）
   - 当前页可能显示 3 条（页面内过滤）
   - 点击下一页可能显示 0 条（每页都重新从后端拉，再过滤）
   - 翻到第 5 页可能又有几条
   - **用户根本搞不清楚有多少匹配**

**根本原因**: 后端 `/audit/logs` 接口不支持用户名筛选，前端只能拿到当前页数据后用 JS 过滤，但 `total` 还是后端返回的总数。

**修复**（选一个方案）：

**方案A**（推荐）：后端增加 username 筛选参数

修改 [Code/backend/routes/admin.py](../Code/backend/routes/admin.py) 中的 `get_audit_logs`，接受 `username` 查询参数：
```python
@router.get("/audit/logs")
async def get_audit_logs(
    page: int = 1,
    page_size: int = 20,
    action: str = '',
    username: str = '',   # 新增
    ...
):
    where_clauses = []
    params = []
    if action:
        where_clauses.append("action = ?")
        params.append(action)
    if username:
        where_clauses.append("username LIKE ?")
        params.append(f"%{username}%")
    # ... 拼接 WHERE 子句、COUNT(*) 和 SELECT 都用同样的 WHERE
```

前端 `getAuditLogs` 调用时传入 username 参数。

**方案B**（不推荐）：保持前端过滤，但至少修正 `total` 显示

**学到的**: 分页 + 筛选必须在后端做、前后端 API 协议设计。

---

### Bug 10: 超管切换组织后上传知识库文档提示"无权操作" 🔴 ⭐⭐ ✅

**位置**:

- [Code/backend/routes/chat.py:279-281](../Code/backend/routes/chat.py#L279)（上传）
- [Code/backend/routes/chat.py:176-178](../Code/backend/routes/chat.py#L176)（问答）
- [Code/backend/routes/chat.py:395-397](../Code/backend/routes/chat.py#L395)（删除文档）
- [Code/backend/routes/export_routes.py:93-95](../Code/backend/routes/export_routes.py#L93)（知识库导出）

**现象**: 超级管理员登录后，通过顶栏切换器切换到"组织B"，进入知识库页面选择部门，上传文档 → 403 错误"无权操作该部门知识库"。超管无法在切换后的组织中上传/检索/删除任何文档，整个跨组织操作功能对超管来说实际上是坏的。

**根本原因**: 对比这两行代码即可发现问题：

```python
# 第1步：正确使用了请求 header 中的目标组织（✅）
effective_org_id, org_code = get_effective_org_context(user, request)

# 第2步：校验部门时用了目标组织（✅）
validate_department(department, effective_org_id)

# 第3步：获取可访问部门却用了超管登录时的原始组织（❌ 核心 bug！）
accessible = get_user_accessible_departments(user)    # ← 用了 user["org_id"]，不是 effective_org_id！
if department not in accessible:
    raise HTTPException(status_code=403, detail="无权操作该部门知识库")
```

**调用链**:

```text
超管登录时 org_id = 1（默认组织）
超管通过顶栏切换到组织B（org_id=2）
         ↓
get_effective_org_context(user, request)
  → 读取 X-Current-Org-Id header = 2
  → 返回 (2, "org_b_code")              ✅ 正确
         ↓
validate_department("hr", 2)
  → SELECT * FROM departments WHERE name='hr' AND org_id=2
  → 存在 → ✅ 通过
         ↓
get_user_accessible_departments(user)
  → user["role"] == "super_admin"
  → user.get("org_id") = 1               ❌ 这里用的是登录时的 org_id！
  → SELECT name FROM departments WHERE org_id = 1
  → 返回的是组织A的部门列表，不包含组织B的"hr"
  → "hr" is NOT in accessible → 403 ❌
```

**影响范围**: 这个模式在 **4 个地方**都有，全部要修：

| 位置 | 行号 | 用途 |
| ---- | ---- | ---- |
| [chat.py](../Code/backend/routes/chat.py) | 279-281 | 上传文档 |
| [chat.py](../Code/backend/routes/chat.py) | 176-178 | 问答检索 |
| [chat.py](../Code/backend/routes/chat.py) | 395-397 | 删除文档 |
| [export_routes.py](../Code/backend/routes/export_routes.py) | 93-95 | 知识库导出 |

**修复**:

方案 A（推荐 — 最小改动，最安全）：超管跳过这个校验

```python
# 在 4 个地方的 accessible 校验处都加超管跳过
if user["role"] != 'super_admin':
    accessible = get_user_accessible_departments(user)
    if department not in accessible:
        raise HTTPException(status_code=403, detail="无权操作该部门知识库")
```

因为超管在前面已经过了 `validate_department` 和 `require_admin`，这个校验对它来说是多余的。超管可以操作任何组织的任何部门。

方案 B（正确但改的多）：修改 `get_user_accessible_departments` 函数签名

```python
def get_user_accessible_departments(user: dict, effective_org_id: int = None) -> list:
    db = get_db()
    org_id = user.get("org_id")
    if user["role"] in ('super_admin', 'admin'):
        target_org = effective_org_id or org_id  # 超管用切换后的组织
        if target_org:
            rows = db.execute("SELECT name FROM departments WHERE org_id = ?", (target_org,)).fetchall()
        else:
            rows = db.execute("SELECT name FROM departments").fetchall()
        return [r["name"] for r in rows]
    ...
```

但这样需要改所有调用方，4 处都要传 `effective_org_id`。

**复现**:

1. 用超管 `admin/admin123` 登录
2. 顶栏组织切换器切换到另一个组织
3. 进入"公司知识库"
4. 选一个部门，上传任意 PDF 文档
5. 看到 403 错误

**学到的**: 多租户系统的组织上下文传递、同一个"用户"在不同组织下的身份变化。

---

### Bug 11: 超管登录后顶栏显示"默认公司"但能看到所有组织数据 🔴 ⭐⭐⭐ ✅

**位置**:

- [Code/ai-assistant/src/stores/auth.js:25-33](../Code/ai-assistant/src/stores/auth.js#L25)
- [Code/ai-assistant/src/api/index.js:36-39](../Code/ai-assistant/src/api/index.js#L36)
- [Code/backend/dependencies.py:33-40](../Code/backend/dependencies.py#L33)

**现象**: 超管登录系统后，顶栏组织切换器显示的是"默认公司"（即自己所属的组织），但实际上：

1. 进入"用户管理"页面 → 看到所有组织的所有用户混在一起
2. 进入"部门管理"页面 → 看到所有组织的所有部门
3. 点击某个用户的"编辑部门"弹窗 → 显示**所有组织的部门**（例如同时出现 5 个"公共知识库"，因为每个组织都有自己的 `general` 部门）
4. 用户感知非常混乱："明明显示我在默认公司，为什么看得到别的组织？"

如果超管手动点一下顶栏的组织切换器、再切回"默认公司"，就**正常了**（只看到默认公司的数据）。这进一步说明 bug 出在初始化阶段。

**根本原因分析（前后端三处协作问题）**:

#### 第一环：前端登录时不把组织ID写入 localStorage

`stores/auth.js` 中的 `checkAuth()` 和 `setUser()`：

```javascript
// 当前代码
if (savedOrgId) {
  currentOrgId.value = Number(savedOrgId)
} else {
  // ❌ 这里只设置 Vue state，没有写到 localStorage
  currentOrgId.value = data.org_id
  currentOrgCode.value = data.org_code
}
```

超管首次登录时 `localStorage` 里没有 `ai_assistant_current_org_id`，所以走 else 分支，但又没把值写回 localStorage。

#### 第二环：axios 拦截器只读 localStorage

`api/index.js`：

```javascript
const currentOrgId = localStorage.getItem('ai_assistant_current_org_id')
if (currentOrgId) {
  config.headers['X-Current-Org-Id'] = currentOrgId
}
```

拦截器不读 Pinia 的 `currentOrgId.value`，只读 localStorage。结果就是：**首次登录时 `X-Current-Org-Id` header 根本没发送**。

#### 第三环：后端"超管 + 无 header = 跨组织"

`dependencies.py`：

```python
if user["role"] == 'super_admin':
    header_org = request.headers.get("X-Current-Org-Id")
    if header_org:
        return int(header_org)
    return None   # ❌ 没传 header → 返回 None → 后续查询不带 WHERE org_id
```

后端 `admin_list_users` / `admin_list_departments` 看到 `effective_org_id is None` 时走"跨组织查询全部"的分支。

**完整调用链**:

```text
超管登录 → 顶栏 UI 显示"默认公司"（Vue state: currentOrgId.value = 1）
            ↓
但 localStorage 里没存 ai_assistant_current_org_id
            ↓
访问 /admin/users → axios 拦截器读 localStorage → 空 → 不附加 X-Current-Org-Id
            ↓
后端 get_effective_org_id() → header 为空 → 返回 None
            ↓
/admin/users 走 elif is_super 分支 → SELECT * FROM users（没有 WHERE org_id）→ 返回所有组织的用户 ❌
            ↓
/admin/departments 同样问题 → 返回所有组织的部门 ❌
            ↓
"编辑部门"弹窗显示 5 个"公共知识库"（每个组织各一个）
```

**复现**:

1. 数据库里至少有 2 个组织（默认公司 + 至少一个其他组织）
2. 用 `admin/admin123` 登录
3. 顶栏显示"默认公司"，**不要手动切换**
4. 进入"用户管理" → 看到所有组织的用户
5. 进入"部门管理" → 看到所有组织的部门
6. 点击任意用户的"编辑部门"按钮 → 弹窗里有多个重复的"公共知识库"
7. 现在手动点顶栏切换器：选"其他公司" → 再切回"默认公司"
8. 重新刷新数据 → 数据正常了（只显示默认公司）

**修复**:

修改 [Code/ai-assistant/src/stores/auth.js](../Code/ai-assistant/src/stores/auth.js)，让超管首次登录时把组织 ID 同步写入 localStorage：

```javascript
// checkAuth 函数中
if (savedOrgId) {
  currentOrgId.value = Number(savedOrgId)
} else {
  currentOrgId.value = data.org_id
  currentOrgCode.value = data.org_code
  // 修复：超管首次登录时同步写 localStorage，让 axios 拦截器能读到
  if (data.role === 'super_admin' && data.org_id) {
    localStorage.setItem(ORG_STORAGE_KEY, String(data.org_id))
  }
}
```

```javascript
// setUser 函数中（处理刚登录注册的场景）
function setUser(data) {
  // ... 现有代码
  currentOrgId.value = data.org_id
  currentOrgCode.value = data.org_code
  // 修复：超管登录时同步到 localStorage
  if (data.role === 'super_admin' && data.org_id) {
    localStorage.setItem(ORG_STORAGE_KEY, String(data.org_id))
  }
}
```

**为什么不在后端修复**: 后端的"超管 + 无 header = 跨组织"是个有意设计——保留这个语义是合理的（比如管理脚本可能需要跨组织查询）。问题出在前端没正确发送 header，所以前端修。

**进阶思考题（给延伸）**:

- 为什么 axios 拦截器要读 localStorage 而不是直接读 Pinia store？
- 答案：拦截器是模块级代码，运行时不一定能拿到当前的 Pinia 实例（特别是在 store 初始化前发起的请求）。localStorage 是浏览器全局存储，最稳。
- 但这也带来同步成本——所以要时刻保持 Vue state 和 localStorage 一致。这是一个**单一数据源（Single Source of Truth）** 原则的反例。

**学到的**:

- 前后端组织上下文传递的完整链路
- Vue 响应式状态 vs 浏览器存储的同步问题
- "看起来正常 + 实际跨组织"是最危险的 bug——用户不会察觉

---

### Bug 12: SmartQA 切换会话后无法发送消息 🟡 ⭐⭐ ✅

**位置**: [Code/ai-assistant/src/views/chat/SmartQA.vue:259-267](../Code/ai-assistant/src/views/chat/SmartQA.vue#L259)

**现象**:
1. 管理员把用户 A 从"hr"部门移除
2. 用户 A 登录，点击一个旧的对话（这个对话之前关联了"hr"部门）
3. 顶部部门下拉框变成**空白**（因为 "hr" 不在用户的可访问列表里）
4. 用户在下方输入框输入问题，点发送
5. 后端返回 403"无权访问该部门知识库"
6. 用户一脸懵：我什么都没改啊？

**根本原因**:
```javascript
async function switchSession(s) {
  currentSessionId.value = s.session_id
  currentDepartment.value = s.department  // ← 直接设置，不校验是否还有权限
  ...
}
```

**修复**:
```javascript
async function switchSession(s) {
  currentSessionId.value = s.session_id
  // 校验：会话的部门是否还在用户可访问列表中
  const isAccessible = departments.value.some(d => d.name === s.department)
  if (isAccessible) {
    currentDepartment.value = s.department
  } else {
    // 回退到第一个可访问的部门，并提示用户
    if (departments.value.length > 0) {
      currentDepartment.value = departments.value[0].name
      ElMessage.warning(`原部门 "${s.department}" 已不可访问，已切换到 "${departments.value[0].display_name}"`)
    }
  }
  ...
}
```

**学到的**: 数据校验要考虑"时间维度"——存储的数据可能因外部变化而失效。

---

### 任务 13（功能缺失）: 实现"密码修改 / 重置"功能 🔴 ⭐⭐⭐ ✅

**性质说明**: 这一项严格来说不是 bug（代码没坏），而是**功能缺失**——但它和 bug 一样会让用户/管理员陷入困境，所以也列入清单。建议放在第二批末尾做。

**位置**: 整个项目都没有相关代码

- 后端：[Code/backend/auth.py](../Code/backend/auth.py) 只有 `hash_password` / `verify_password`，没有任何修改密码的函数
- 后端：[Code/backend/routes/auth.py](../Code/backend/routes/auth.py) 没有修改密码的 API
- 前端：[Code/ai-assistant/src/views/admin/Users.vue](../Code/ai-assistant/src/views/admin/Users.vue) 创建用户时可以设密码，但用户列表里没有"重置密码"按钮
- 前端：[Code/ai-assistant/src/views/Layout.vue](../Code/ai-assistant/src/views/Layout.vue) 顶栏用户菜单没有"修改密码"入口

**现象**:

1. 普通用户**忘记密码**了 → 没办法自助修改，只能找管理员
2. 管理员**想帮用户重置密码** → 管理界面没有"重置密码"按钮，做不到
3. 超管**想改自己的密码**（特别是默认的 `admin/admin123`）→ 没有任何入口
4. 入职新员工 → 管理员创建账号时设了初始密码，员工**无法自己改成自己的密码**

**真实影响**:

- `admin/admin123` 这个默认密码**永远改不掉**（除非直接改数据库），这是严重的安全隐患
- 用户密码泄露后**没有补救手段**
- 离职员工的密码可能被知道，没办法快速更换

**功能需求**: 需要实现两种场景

#### 场景 A: 用户自己修改密码

**后端新增**:

```python
# auth.py 新增业务函数
def change_user_password(user_id: int, old_password: str, new_password: str) -> None:
    """
    用户自助修改密码 — 必须验证旧密码。
    """
    _validate_credentials("dummyname", new_password)  # 复用新密码长度校验
    db = get_db()
    row = db.execute(
        "SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")
    if not verify_password(old_password, row["salt"], row["password_hash"]):
        raise HTTPException(400, "原密码错误")
    new_hash, new_salt = hash_password(new_password)
    db.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
        (new_hash, new_salt, user_id)
    )
    # 安全考虑：改密后强制清除该用户所有 token，所有设备需重新登录
    db.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
    db.commit()
```

**后端 API**：在 `routes/auth.py` 新增 `POST /auth/change-password`

**前端**: 在 [Layout.vue](../Code/ai-assistant/src/views/Layout.vue) 顶栏用户名旁加"修改密码"菜单项，弹窗包含：原密码、新密码、确认新密码三个字段。提交成功后提示用户重新登录。

#### 场景 B: 管理员重置用户密码

**后端新增**:

```python
# auth.py 新增业务函数
def reset_user_password(target_user_id: int, new_password: str, operator: dict) -> None:
    """
    管理员/超管重置某个用户的密码 — 不需要旧密码，但有权限校验。

    权限规则:
      - super_admin 可以重置任何用户的密码（含其他超管和自己）
      - admin 只能重置本组织内的 user 角色用户的密码（不能重置同级 admin 或超管）
    """
    _validate_credentials("dummyname", new_password)
    db = get_db()
    target = db.execute(
        "SELECT id, role, org_id FROM users WHERE id = ?", (target_user_id,)
    ).fetchone()
    if not target:
        raise HTTPException(404, "用户不存在")

    # 权限校验
    if operator["role"] != 'super_admin':
        if target["role"] != 'user':
            raise HTTPException(403, "管理员只能重置普通用户的密码")
        if target["org_id"] != operator.get("org_id"):
            raise HTTPException(403, "不能重置其他组织用户的密码")

    new_hash, new_salt = hash_password(new_password)
    db.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
        (new_hash, new_salt, target_user_id)
    )
    # 强制目标用户重新登录
    db.execute("DELETE FROM auth_tokens WHERE user_id = ?", (target_user_id,))
    db.commit()
```

**后端 API**: 在 `routes/admin.py` 的 `admin_manage_user` 路由新增 action `reset_password`：

```python
elif action == "reset_password":
    new_pwd = body.get("new_password", "")
    if not new_pwd:
        raise HTTPException(400, "请提供新密码")
    from auth import reset_user_password
    reset_user_password(user_id, new_pwd, user)
    log_action(user["user_id"], "reset_user_password", "admin",
               f"重置用户ID={user_id}的密码")
    return {"status": "success"}
```

**前端**: 在 [Users.vue](../Code/ai-assistant/src/views/admin/Users.vue) 操作列加"重置密码"按钮（前端按钮权限：admin 仅对 user 角色显示；super_admin 对所有人显示），弹窗只有一个新密码输入框。

#### 复现步骤（功能不存在）

1. 用 `admin/admin123` 登录
2. 进入"用户管理"页面
3. 在任意用户那一行寻找"修改密码"或"重置密码"按钮 → **没有**
4. 进入顶栏用户菜单寻找"修改密码"选项 → **没有**
5. 想改默认密码 admin123 → **无法操作**

#### 验收清单

- [ ] 用户登录后能从顶栏入口修改自己的密码（必须验证原密码）
- [ ] 修改密码后所有设备都被踢出（强制重新登录）
- [ ] admin 能在用户管理页重置本组织 user 角色的密码
- [ ] admin 不能重置其他 admin / super_admin 的密码
- [ ] super_admin 能重置任何用户的密码（含自己）
- [ ] 新密码长度校验：至少 6 位（复用现有 `_MIN_PASSWORD_LEN`）
- [ ] 重置操作记入审计日志（`reset_user_password` action）
- [ ] 前端密码强度提示、两次输入一致校验

**学到的**:

- 密码学基础：旧密码验证、强制重新登录的意义
- 权限分级设计：什么角色能操作什么用户
- 审计追溯：高危操作必须留痕
- 安全设计权衡：修改密码 vs 重置密码的差异

**建议工时**: 2-3 天

---

## 🌟 第三批：高难度（需深入理解，1 周）

### Bug 14: 文件上传路径穿越漏洞 🔴 ⭐⭐⭐ ✅

**位置**: 
- [Code/backend/routes/chat.py:292-304](../Code/backend/routes/chat.py#L292)
- [Code/backend/routes/analysis.py:75](../Code/backend/routes/analysis.py#L75)

**现象**: ⚠️ **这是一个真实的安全漏洞**。攻击者可以构造特殊的文件名上传到任意目录。

**攻击示例**:
```python
# 攻击者构造请求
POST /upload
Content-Disposition: form-data; name="files"; filename="../../../../tmp/evil.pdf"

# 后端代码
file_path = docs_dir / file.filename
# 实际写入路径: /tmp/evil.pdf （逃出了 docs_dir 目录！）
```

Windows 上类似的 `..\..\..\file.pdf` 也能绕过。

**修复**: 用 `Path.name` 剥离路径部分，只保留文件名。

```python
from pathlib import Path

# ❌ 危险
file_path = docs_dir / file.filename

# ✅ 安全
safe_name = Path(file.filename).name  # 只取文件名部分，无路径
# 进一步：过滤危险字符
import re
safe_name = re.sub(r'[^\w一-鿿.\-]', '_', safe_name)
file_path = docs_dir / safe_name
```

**复现方法**:
用 curl 测试：
```bash
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "files=@test.pdf;filename=../../evil.pdf" \
  -F "department=general"
```
然后检查项目根目录是否出现了 `evil.pdf`。

**推荐做法**: 让先用 Postman 复现这个漏洞，再修复。这样能真切感受到安全问题。

**学到的**: OWASP Top 10 中的 Path Traversal、永远不要信任用户输入。

---

### Bug 15: 数据分析报告生成时缺少 await 🔴 ⭐⭐⭐ ⚠️

**位置**: 
- [Code/backend/file_analyzer.py:248-253](../Code/backend/file_analyzer.py#L248)
- [Code/backend/file_analyzer.py:391](../Code/backend/file_analyzer.py#L391) 附近（compliance 部分）

**现象**: 数据文件分析功能可能崩溃，或者会阻塞整个服务。

**根本原因**:
```python
async def _generate_data_analysis_report(...):
    ...
    try:
        report = _call_deepseek_api(messages)  # ← 这里！
        return report.strip()
```

`_call_deepseek_api` 是同步函数，在 async 函数里直接调用会**阻塞整个 FastAPI 事件循环**——意味着分析 LLM 跑的 30 秒内，其他用户的所有请求都被卡住。

正确做法（参考 [llm.py:99-101](../Code/backend/llm.py#L99) 的写法）：
```python
import asyncio

async def _generate_data_analysis_report(...):
    ...
    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, _call_deepseek_api, messages)
    return report.strip()
```

**复现**:
1. 用户 A 上传一个大 Excel 文件做数据分析
2. 用户 B 同时尝试用智能问答
3. 用户 B 的问答请求会卡住，直到用户 A 的分析完成

**学到的**: Python asyncio 基础、事件循环、阻塞 vs 非阻塞调用。

**为什么需要带教指导**: 涉及 Python 异步编程的核心概念，第一次遇到容易理解错。

---

### Bug 16: 知识库重建可能永久丢失数据 🔴 ⭐⭐⭐⭐ ❌

**位置**: [Code/backend/vector_store.py:110-134](../Code/backend/vector_store.py#L110)

**现象**: 管理员点击"重建知识库"，如果过程中出错（断网/磁盘满/服务被杀），**整个向量库可能永久丢失**。

**根本原因**:
代码注释说"如果失败，旧集合仍然完好"，但实际代码是：
```python
_client.delete_collection(collection_name)  # ← 先删除旧的
final_collection = _client.create_collection(...)  # ← 再创建新的
for i in range(0, len(texts), batch_size):
    final_collection.add(...)  # ← 如果这里失败，数据没了
```

正确做法应该是：先把新数据写入临时集合，全部成功后再原子地替换旧集合。

---

### Bug 17: search_similar_multi 去重导致丢失结果 🟡 ⭐⭐ ✅

**位置**: [Code/backend/vector_store.py:282-286](../Code/backend/vector_store.py#L282)

**现象**: 多部门检索时，前 100 个字符相同的不同文档块会被错误去重，导致搜索结果不全。

**问题代码**:
```python
key = item["text"][:100]   # 用前 100 字符做去重 key
if key not in all_items or item["similarity"] > all_items[key]["similarity"]:
    all_items[key] = item
```

**影响场景**: 公司有多个"规章制度"文档，每个文档开头都是"公司规章制度 第X条..."，前 100 字符高度相似，会被互相覆盖。

**修复**: 用完整 text 做 key，或者用 `(filename, chunk_index)` 元组做 key：
```python
key = (item["metadata"].get("filename"), item["metadata"].get("chunk_index"))
if key not in all_items or item["similarity"] > all_items[key]["similarity"]:
    all_items[key] = item
```

**学到的**: 去重 key 选择的重要性、哈希冲突。

总工期约 **4 周**（17 项任务，按由易到难安排，每天 1-2 项小任务或 1 项大任务）。

### 第 1 周：第一批 Bug（建立信心，熟悉代码库）

| Day | 任务 | 说明 |
| --- | --- | --- |
| Day 1 上午 | 通读 [CLAUDE.md](../CLAUDE.md)，本地跑通前后端 | 入门必做 |
| Day 1 下午 | Bug 1（Login 图标）+ Bug 3（冗余 except） | 两个最简单的"热身" |
| Day 2 | Bug 4（删除无用导入 3 处） | 学习"安全删除"思维：用 IDE 查引用 |
| Day 3 | Bug 2（替换 alert + 防抖） | 第一次接触前端工程化（防抖、路由跳转） |

### 第 2 周：第二批 Bug（理解业务流程）

| Day | 任务 | 说明 |
| --- | --- | --- |
| Day 4-5 | Bug 5（管理员无法创建用户） | 第一个真实的"功能完全不可用"bug，体会测试覆盖的重要性 |
| Day 6 | Bug 6（超管自禁用） | 学习"防自杀"设计原则 |
| Day 7 | Bug 7（转移组织后状态未重置） | 状态一致性思维 |
| Day 8 | Bug 8（组织禁用后用户卡死） | HTTP 状态码语义、错误恢复设计 |
| Day 9-10 | Bug 9（审计日志搜索完全错误） | 第一次接触前后端 API 协议设计 |

### 第 3 周：进阶 Bug + 综合功能

| Day | 任务 | 说明 |
| --- | --- | --- |
| Day 11 | Bug 10（超管切换组织后无权操作） | 多租户上下文传递；先理解 4 处问题模式再修 |
| Day 12-13 | **Bug 11（顶栏显示默认公司但能看所有数据）** | **本清单调试难度最高的 bug**——需要完整追踪"前端 Pinia → localStorage → axios → 后端 dependencies"四环链路；建议带教坐旁边一起调一次 |
| Day 14 | Bug 12（SmartQA 切换会话） | 数据校验的时间维度 |
| Day 15-17 | **任务 13（实现密码修改/重置功能）** | 本周的综合任务：第一次独立实现完整的前后端功能 |

### 第 4 周：第三批 Bug（深入技术 + 安全）

| Day | 任务 | 说明 |
| --- | --- | --- |
| Day 18-19 | Bug 14（路径穿越漏洞） | **必须先用 Postman 复现漏洞，再修复**；学到 Web 安全基础 |
| Day 20-21 | Bug 15（async 缺少 await） | 需带教讲解 asyncio 核心概念 |
| Day 22 | Bug 17（多部门检索去重错误） | 数据结构选择 |
| Day 23-24 | 缓冲 + 自由探索 | 给留时间自己找几个小 bug 修，或回顾总结 |

**Bug 16（知识库重建丢失数据）**：⚠️ 不推荐做，涉及 ChromaDB API 限制 + 事务设计，难度过高。让正式员工处理。

---

## 🎯 重点任务带教建议

### Bug 11（顶栏组织不一致）—— 调试思维训练

这是清单里**最有教学价值的调试题**。建议带教按这个节奏：

```
Step 1（独立）：复现 bug，写下"我观察到的现象"
Step 2（独立）：尝试 30 分钟定位（大概率定位不到）
Step 3（带教介入）：一起用浏览器 Network 面板看请求
        → 发现 X-Current-Org-Id header 没发
Step 4（带教引导）：从 axios 拦截器一步步往上溯源
        → axios 读 localStorage → localStorage 是空的 → Pinia state 不是空的
        → 找到根因：store 没同步到 localStorage
Step 5（独立）：写修复方案 + 测试
Step 6（带教总结）：讨论"为什么这种 bug 难定位"
```

这一套走完，**的调试能力会有质的飞跃**。

### Bug 14（路径穿越）—— 安全意识训练

务必让**亲手用 Postman 复现漏洞**：

```
1. 用普通 PDF 命名 evil.pdf，上传成功 → 文件出现在 docs_dir/general/evil.pdf
2. 用 Postman 改 Content-Disposition 的 filename="../../../evil.pdf"
3. 重新上传 → 发现文件出现在了项目根目录（甚至更上层）
4. 此时让她意识到："我刚才把文件写到了不该写的地方"
5. 引导她思考：如果攻击者写一个 .py 文件到某个会被 Python 自动加载的位置呢？
6. 修复 + 验证攻击不再生效
```

这个过程的震撼远大于讲十遍"要校验用户输入"。

### 任务 13（密码修改/重置）—— 综合能力训练

这是清单里**唯一的"完整功能开发"**，包含：

- 后端：业务函数 + API 路由 + 权限校验 + 审计日志
- 前端：用户菜单入口 + 表单弹窗 + 错误提示
- 安全：旧密码校验 + Token 失效策略 + 权限矩阵

建议工作流程：

```
Day 1：方案设计文档（写一页 README 描述要做什么、怎么做、API 长什么样）
       → 带教 review 方案，确认无误再开始
Day 2：后端实现（业务函数 + API），用 Postman 测通
Day 3：前端实现，与后端联调，跑通完整流程
```

不要让她一上来就动手写代码——**先写方案再写代码**是这个任务最大的教学价值。

---

## 🎯 任务执行规范

### 每个 Bug 的工作流程

```
1. 阅读现状代码 → 写一段话描述"我理解的问题是什么"（带教 review）
2. 写复现步骤 → 实际操作复现 bug，截图证明
3. 设计修复方案 → 至少给出 2 个候选方案，分析利弊
4. 写代码（遵守 CLAUDE.md 规范）
5. 自测：复现步骤里的现象是否消失？
6. 写一段"修复说明"：改了什么、为什么这么改、有没有副作用
7. 提交代码 + 修复说明给带教 review
```

### Git 提交规范

每个 bug 一个独立的 commit，message 格式：
```
fix(模块): 简短描述

修复 [Bug编号]
- 问题：[一句话描述]
- 修复：[做了什么]
- 影响范围：[改了哪些文件]
```

例如：
```
fix(login): 修复登录页输入框图标不显示

修复 Bug 1
- 问题：prefix-icon 传字符串导致 Element Plus 2.x 无法渲染图标
- 修复：改为从 @element-plus/icons-vue 导入组件并用 :prefix-icon 绑定
- 影响范围：Code/ai-assistant/src/views/Login.vue
```

---

## 🔍 给带教的检查清单

每次 review 时按这个清单检查：

- [ ] Bug 是否真的被修复了（重现复现步骤验证）
- [ ] 有没有引入新的副作用（其他功能是否还正常）
- [ ] 代码风格是否匹配现有代码（参考 [CLAUDE.md](../CLAUDE.md)）
- [ ] 是否过度修改（"顺便优化"了不相关的代码）
- [ ] 注释是否得当（只解释 WHY，不解释 WHAT）
- [ ] 有没有遗漏的边界场景（空值、并发、权限）

---

## 💡 给的额外建议

### 必读

1. **修 bug 之前先理解整个调用链**，不要只看错误那一行就动手
2. **复现是修 bug 的第一步**，复现不了说明你没真正理解问题
3. **优先修 bug，不要顺便重构**——重构是另一个任务，不要混在一起
4. **每个修复都要有"我为什么改这里"的清晰理由**

### 卡住时怎么办

1. 看 git log，搜索类似 bug 修过没（`git log --all --grep="关键词"`）
2. 看类似功能的实现（如改 admin 路由，对照另一个能跑的路由）
3. 用 print 大法定位问题（注意修完要删掉）
4. 不要超过 1 小时还卡住，主动找带教

### 不要做的事

- ❌ 一次改多个 bug（提交时分不清谁是谁的功劳）
- ❌ 改了一行代码就提交（用整体的 commit message）
- ❌ 修了 bug 不写测试说明（"我改了，应该好了"是不够的）
- ❌ 看了一眼觉得"我猜应该是这里"就改（必须复现 + 验证）

---

## 🏆 最终交付

每完成一个 bug，提交：

1. **代码改动**（git commit）
2. **修复说明文档**（一段话，写在 commit message 或单独的 README）
3. **复现步骤 + 验证截图**
4. **如有副作用或权衡，写在说明里**

完成全部 13 个 bug 后，写一份**总结报告**：
- 学到了什么
- 哪些 bug 最难调
- 项目还有哪些类似的潜在 bug

---

## 📞 紧急联系

如果碰到以下情况，**立即停下来找带教**：

- 🚨 改动可能涉及数据库迁移（动 db.py 之前必须 review）
- 🚨 改动可能涉及认证逻辑（动 auth.py 之前必须 review）
- 🚨 不确定改动会不会影响其他功能
- 🚨 改完后某个原本能用的功能不能用了

**记住：在生产代码里写错一行字母可能影响成千上万的用户。慢一点没关系，错了不行。**
