# 项目: KnowledgeBaseRetrieval

## 语言偏好

- 所有思考过程和回复使用**中文**
- 代码（变量名、函数名等）保持英文
- 注释可使用中文

## 项目结构

```
Code/
  backend/          — Python FastAPI 后端
    main.py         — 入口，路由定义
    venv/           — Python 虚拟环境
    requirements.txt
  ai-assistant/     — Vue 3 + Vite 前端
    src/
    package.json
Doc/                — 项目文档
```

## 技术栈

- **后端**: FastAPI + Uvicorn + ChromaDB + OpenAI/DeepSeek
- **前端**: Vue 3 + Element Plus + Pinia + Vite

## 常用命令

- 后端启动: `cd Code/backend; .\venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- 前端启动: `cd Code/ai-assistant; npm run dev`
