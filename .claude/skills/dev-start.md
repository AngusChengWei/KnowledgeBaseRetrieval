---
name: dev-start
description: 一键构建并启动前后端开发环境
---

## 说明

此 skill 用于一键构建并启动 KnowledgeBaseRetrieval 项目的前后端开发环境。

## 项目结构

- 后端：`Code/backend/` — Python FastAPI 应用
- 前端：`Code/ai-assistant/` — Vue 3 + Vite 应用

## 执行步骤

### 1. 检查环境

首先确认以下工具可用：
- Python（用于后端）
- Node.js 和 npm（用于前端）

### 2. 构建并启动后端

```powershell
# 进入后端目录
cd Code/backend

# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 安装依赖（如果需要）
pip install -r requirements.txt

# 启动 FastAPI 后端服务（后台运行）
Start-Process -NoNewWindow -FilePath ".\venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"
```

### 3. 构建并启动前端

```powershell
# 进入前端目录
cd Code/ai-assistant

# 安装依赖（如果 node_modules 不存在）
if (-not (Test-Path "node_modules")) { npm install }

# 启动 Vite 开发服务器
npm run dev
```

### 4. 输出访问地址

- 后端 API：http://localhost:8000
- 后端 API 文档：http://localhost:8000/docs
- 前端页面：http://localhost:5173（Vite 默认端口）
