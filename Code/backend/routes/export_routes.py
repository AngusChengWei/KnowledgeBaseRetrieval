"""
PDF 导出 / ZIP 下载路由。

导出功能:
  - /pdf/report: 将 AI 问答结果（问题+回答+引用来源）导出为 PDF 报告
  - /export/download-zip: 将知识库文档打包为 ZIP 下载

PDF 生成依赖:
  - pdf_generator.py 使用 Playwright 无头浏览器渲染 HTML → PDF
  - 支持中文字体（通过 fonts/ 目录下的字体文件）
"""

import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse

from models import ReportPdfRequest, ExportDocsPdfRequest
from auth import get_current_user, require_admin, get_user_accessible_departments
from dependencies import get_effective_org_context, validate_department, get_docs_dir

router = APIRouter()


@router.post("/pdf/report")
async def export_report_pdf(
    request: ReportPdfRequest,
    user: dict = Depends(get_current_user)
):
    """
    将 AI 问答结果导出为 PDF 报告。

    输入:
      - question: 用户原始问题
      - answer: AI 生成的回答
      - sources: 引用的知识库来源列表
      - session_id: 关联的会话 ID（可选）

    输出:
      - PDF 文件流（application/pdf），文件名包含时间戳

    使用 StreamingResponse 直接返回 PDF 字节流，浏览器自动触发下载。
    """
    from pdf_generator import generate_report_pdf
    from audit import log_action

    sources_data = [{"filename": s.filename, "chunk": s.chunk} for s in request.sources]
    pdf_bytes = generate_report_pdf(
        question=request.question,
        answer=request.answer,
        sources=sources_data,
        title="AI 问答报告"
    )

    log_action(user["user_id"], "export_report_pdf", "pdf",
               f"导出AI问答报告: {request.question[:50]}")

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        }
    )


@router.post("/export/download-zip")
async def export_documents_zip(
    request: ExportDocsPdfRequest,
    http_request: Request,
    user: dict = Depends(require_admin)
):
    """
    将知识库文档打包为 ZIP 下载（需管理员权限）。

    支持两种模式:
      - 指定文件列表（filenames 非空）: 仅打包指定的文件
      - 导出全部（filenames 为空）: 打包部门目录下所有支持的文件

    注意: URL 导入的网页内容不支持 ZIP 导出（它们没有物理文件），仅文件类文档可导出。

    按组织隔离，不同组织的文件存储在不同目录。
    """
    import zipfile
    from io import BytesIO
    from audit import log_action
    import config

    effective_org_id, org_code = get_effective_org_context(user, http_request)
    validate_department(request.department, effective_org_id)

    accessible = get_user_accessible_departments(user)
    if request.department not in accessible:
        raise HTTPException(status_code=403, detail="无权操作该部门知识库")

    docs_dir = get_docs_dir(request.department, org_code)
    if not docs_dir.exists():
        raise HTTPException(status_code=400, detail="该知识库目录不存在")

    # 收集要导出的文件列表
    export_files = []
    if request.filenames:
        # 指定文件名模式：只打包请求中列出的文件
        selected = {f for f in request.filenames}
        for fname in selected:
            fp = docs_dir / fname
            if fp.exists() and fp.is_file():
                export_files.append(fp)
    else:
        # 导出全部模式：打包目录下所有支持的文档格式
        supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".xls"}
        for fp in docs_dir.iterdir():
            if fp.is_file() and fp.suffix.lower() in supported_extensions:
                export_files.append(fp)

    if not export_files:
        raise HTTPException(status_code=400, detail="没有可导出的文件，网页条目不支持导出为ZIP，仅支持文件类文档")

    # 在内存中构建 ZIP 文件（不落盘）
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in export_files:
            zf.write(fp, arcname=fp.name)

    buf.seek(0)
    zip_bytes = buf.getvalue()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_action(user["user_id"], "export_docs_zip", "export",
               f"部门={request.department}, 导出{len(export_files)}个文件")

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=knowledge_{request.department}_{timestamp}.zip"
        }
    )
