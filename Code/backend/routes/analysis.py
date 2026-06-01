"""
文件分析路由 — 上传文件进行数据校验或合规检查。

分析类型:
  - data: 数据校验 — 将上传的 Excel/CSV 与知识库规范进行比对
  - compliance: 合规检查 — 将上传的文档与知识库中的合规要求进行比对

工作流程:
  1. 用户上传文件 → 保存到临时目录
  2. 创建 analysis_tasks 记录（status='processing'）
  3. 调用 file_analyzer 执行分析 → 结果写入 result_json
  4. 更新任务状态为 'completed' 或 'failed'
  5. 清理临时文件
  6. 前端通过 /analyze/result/{task_id} 轮询获取结果

注意: 分析任务在当前请求中同步完成（非后台任务），大文件可能导致请求超时。
"""

import json
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Query

from auth import get_current_user
from dependencies import get_effective_org_context

router = APIRouter()


@router.post("/analyze/upload")
async def upload_analysis_file(
    http_request: Request,
    file: UploadFile = File(...),
    analysis_type: str = Query(...),
    departments: str = Query(default="general"),
    user_question: str = Query(default=""),
    user: dict = Depends(get_current_user)
):
    """
    上传文件进行分析。

    参数:
      - analysis_type: "data"（数据校验）或 "compliance"（合规检查）
      - departments: 逗号分隔的部门列表，如 "general,hr,sale"，指定参考哪些知识库
      - user_question: 可选的用户自定义分析要求

    返回:
      - task_id: 分析任务 ID，前端用此 ID 查询结果

    文件格式限制:
      - data 分析: 仅支持 .xlsx, .xls, .csv
      - compliance 分析: 仅支持 .pdf, .docx, .doc, .txt, .md
    """
    from file_analyzer import analyze_data_file, analyze_document_compliance
    from db import get_db
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, http_request)

    dept_list = [d.strip() for d in departments.split(",") if d.strip()]

    # 根据分析类型限制可上传的文件格式
    ext = Path(file.filename).suffix.lower()
    if analysis_type == "data":
        allowed = {".xlsx", ".xls", ".csv"}
    else:  # compliance
        allowed = {".pdf", ".docx", ".doc", ".txt", ".md"}

    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"文件类型不支持。{analysis_type}分析支持: {', '.join(allowed)}")

    # 保存上传文件到用户专属临时目录
    temp_dir = Path(config.ANALYSIS_TEMP_DIR) / str(user["user_id"])
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename

    content = await file.read()
    max_size = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail=f"文件超过{config.MAX_UPLOAD_SIZE_MB}MB限制")

    with open(temp_path, "wb") as f:
        f.write(content)

    # 创建分析任务记录（初始状态: processing）
    db = get_db()
    file_type = "data" if analysis_type == "data" else "compliance"
    cur = db.execute(
        """INSERT INTO analysis_tasks (user_id, filename, file_type, analysis_type, department, status, created_at)
           VALUES (?, ?, ?, ?, ?, 'processing', datetime('now','localtime'))""",
        (user["user_id"], file.filename, file_type, analysis_type, departments)
    )
    db.commit()
    task_id = cur.lastrowid

    try:
        # 执行分析（同步阻塞，大文件可能耗时较长）
        if analysis_type == "data":
            result = await analyze_data_file(str(temp_path), user_question, dept_list, org_code)
        else:
            result = await analyze_document_compliance(str(temp_path), org_code, dept_list, user_question)

        # 分析成功 → 更新状态和结果
        db.execute(
            "UPDATE analysis_tasks SET status = 'completed', result_json = ? WHERE id = ?",
            (json.dumps(result, ensure_ascii=False), task_id)
        )
        db.commit()
    except Exception as e:
        # 分析失败 → 记录错误信息，不阻塞响应
        error_msg = str(e)
        db.execute(
            "UPDATE analysis_tasks SET status = 'failed', error_message = ? WHERE id = ?",
            (error_msg, task_id)
        )
        db.commit()
        raise HTTPException(status_code=500, detail=f"分析失败: {error_msg}")
    finally:
        # 无论成功失败，都清理临时文件（避免磁盘积累）
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

    log_action(user["user_id"], f"analyze_{analysis_type}", "analysis",
               f"文件={file.filename}, 类型={analysis_type}")

    return {
        "task_id": task_id,
        "status": "completed",
        "filename": file.filename,
        "analysis_type": analysis_type
    }


@router.get("/analyze/result/{task_id}")
async def get_analysis_result(
    task_id: int,
    user: dict = Depends(get_current_user)
):
    """
    获取文件分析结果。

    权限校验:
      - 任务所有者可查看
      - 管理员（admin/super_admin）可查看所有任务

    返回的 result 字段是分析结果 JSON，结构取决于分析类型:
      - data 分析: 包含校验通过/失败的记录列表
      - compliance 分析: 包含合规/不合规的检查项列表
    """
    from db import get_db
    db = get_db()
    row = db.execute(
        "SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="分析任务不存在")

    if row["user_id"] != user["user_id"] and user["role"] not in ('super_admin', 'admin'):
        raise HTTPException(status_code=403, detail="无权访问此任务")

    result = {
        "task_id": row["id"],
        "filename": row["filename"],
        "file_type": row["file_type"],
        "analysis_type": row["analysis_type"],
        "status": row["status"],
        "error_message": row["error_message"],
        "created_at": row["created_at"]
    }

    if row["result_json"]:
        try:
            result["result"] = json.loads(row["result_json"])
        except json.JSONDecodeError:
            result["result"] = {}

    return result


@router.get("/analyze/history")
async def get_analysis_history(
    user: dict = Depends(get_current_user)
):
    """
    获取当前用户的分析历史记录（最近 20 条）。

    返回简要信息（不含完整分析结果），用于历史列表展示。
    要获取完整结果需调用 /analyze/result/{task_id}。
    """
    from db import get_db
    db = get_db()
    rows = db.execute(
        """SELECT id, filename, file_type, analysis_type, status, created_at
           FROM analysis_tasks WHERE user_id = ?
           ORDER BY id DESC LIMIT 20""",
        (user["user_id"],)
    ).fetchall()
    return {"tasks": [dict(r) for r in rows]}
