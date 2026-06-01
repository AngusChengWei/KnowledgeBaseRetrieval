"""
文件分析模块 — 支持数据文件校验和文档合规性检查。

两种分析类型:
  1. 数据文件分析 (analyze_data_file):
     - 输入: Excel/CSV 文件
     - 输出: 列统计（均值/方差/缺失率）、异常值检测（3σ）、重复行、AI 分析报告
     - 可选关联知识库: 用文件摘要向量检索相关业务规范，增强 AI 报告

  2. 文档合规检查 (analyze_document_compliance):
     - 输入: PDF/DOCX/TXT 等文档
     - 输出: 逐条合规分析（符合项/不符合项/风险评估/改进建议）
     - 核心: 将文档内容与知识库中的制度规范进行向量检索 + LLM 比对

技术流程:
  文档上传 → 解析文本 → 向量化 → 跨部门知识库检索 → LLM 分析 → 结构化报告
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import pandas as pd

import config


# ============ 数据文件分析 ============

async def analyze_data_file(
    file_path: str,
    user_question: str = "",
    departments: list = None,
    org_code: str = "default"
) -> dict:
    """
    分析数据文件（Excel/CSV），返回结构化的分析结果。

    参数:
        file_path: 文件路径
        user_question: 用户自定义分析重点
        departments: 可选知识库部门列表，用于在 AI 报告中补充业务上下文
        org_code: 组织编码

    返回:
        {
            "summary": 概览信息,
            "columns": 列分析详情,
            "missing_values": 缺失值分析,
            "duplicates": 重复行,
            "outliers": 异常值,
            "ai_report": AI 分析报告
        }
    """
    ext = Path(file_path).suffix.lower()

    # 读取文件
    if ext == ".csv":
        # 尝试多种编码
        try:
            df = pd.read_csv(file_path, encoding="utf-8")
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding="gbk")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="gb18030")
    else:
        df = pd.read_excel(file_path, engine="openpyxl")

    if df.empty:
        return {
            "status": "error",
            "message": "文件为空或无法读取"
        }

    result = {}

    # 1. 概览
    result["summary"] = {
        "filename": Path(file_path).name,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "dtypes": {col: str(df[col].dtype) for col in df.columns},
        "memory_usage": f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB"
    }

    # 2. 列分析
    col_analysis = []
    for col in df.columns:
        info = {"name": col, "dtype": str(df[col].dtype)}
        non_null = df[col].notna().sum()
        info["non_null_count"] = int(non_null)
        info["null_count"] = int(len(df) - non_null)
        info["null_ratio"] = round((len(df) - non_null) / len(df) * 100, 2)

        # 数值列统计
        if pd.api.types.is_numeric_dtype(df[col]):
            info["min"] = _safe_round(df[col].min())
            info["max"] = _safe_round(df[col].max())
            info["mean"] = _safe_round(df[col].mean())
            info["std"] = _safe_round(df[col].std())
            info["unique_count"] = int(df[col].nunique())

            # 识别可能的异常值（3倍标准差以外）
            mean = df[col].mean()
            std = df[col].std()
            if pd.notna(std) and std > 0:
                outliers = df[(df[col] - mean).abs() > 3 * std][col]
                info["outlier_count"] = len(outliers)
                if len(outliers) > 0:
                    info["outlier_examples"] = [float(x) for x in outliers.head(5)]
                else:
                    info["outlier_examples"] = []
            else:
                info["outlier_count"] = 0
                info["outlier_examples"] = []

        # 文本列统计
        elif pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            non_null_values = df[col].dropna()
            info["unique_count"] = int(non_null_values.nunique())
            info["empty_string_count"] = int((non_null_values == "").sum())
            info["min_length"] = int(non_null_values.astype(str).str.len().min()) if len(non_null_values) > 0 else 0
            info["max_length"] = int(non_null_values.astype(str).str.len().max()) if len(non_null_values) > 0 else 0
            # 常见值分布（Top 5）
            top_values = non_null_values.value_counts().head(5)
            info["top_values"] = [
                {"value": str(k), "count": int(v)}
                for k, v in zip(top_values.index, top_values.values)
            ]

        col_analysis.append(info)

    result["columns"] = col_analysis

    # 3. 缺失值总览
    null_cols = [c for c in col_analysis if c["null_count"] > 0]
    result["missing_values"] = {
        "has_missing": len(null_cols) > 0,
        "total_missing_cells": sum(c["null_count"] for c in null_cols),
        "missing_ratio": round(
            sum(c["null_count"] for c in null_cols) / (len(df) * len(df.columns)) * 100, 2
        ),
        "columns_with_missing": [{
            "name": c["name"],
            "null_count": c["null_count"],
            "null_ratio": c["null_ratio"]
        } for c in null_cols]
    }

    # 4. 重复行
    duplicate_count = df.duplicated().sum()
    result["duplicates"] = {
        "has_duplicates": duplicate_count > 0,
        "duplicate_rows": int(duplicate_count),
        "duplicate_ratio": round(duplicate_count / len(df) * 100, 2)
    }

    # 5. 异常值汇总
    outlier_cols = [c for c in col_analysis if c.get("outlier_count", 0) > 0]
    result["outliers"] = {
        "has_outliers": len(outlier_cols) > 0,
        "columns_with_outliers": [{
            "name": c["name"],
            "outlier_count": c["outlier_count"],
            "outlier_examples": c.get("outlier_examples", [])
        } for c in outlier_cols]
    }

    # 6. 生成 AI 分析报告（含知识库上下文）
    result["ai_report"] = await _generate_data_analysis_report(df, result, user_question, departments, org_code)

    result["status"] = "completed"
    return result


async def _generate_data_analysis_report(df: pd.DataFrame, analysis: dict, user_question: str,
                                         departments: list = None, org_code: str = "default") -> str:
    """调用 LLM 生成数据文件分析报告（可选关联知识库作为业务上下文）"""
    from llm import _call_deepseek_api

    # 如果指定了知识库，检索相关上下文
    kb_context = ""
    if departments:
        try:
            from vector_store import search_similar_multi
            from embedding import get_embedding
            # 用文件摘要做知识库检索
            summary_text = f"数据文件分析: {analysis['summary']['filename']}, 列: {', '.join(analysis['summary']['column_names'])}"
            emb = await get_embedding(summary_text)
            results = search_similar_multi(emb, top_k_per_dept=2, departments=departments, org_code=org_code)
            if results:
                kb_texts = [f"[来源:{r['metadata'].get('filename','未知')}] {r['text'][:200]}" for r in results[:5]]
                kb_context = "\n\n=== 知识库相关参考 ===\n" + "\n---\n".join(kb_texts)
        except Exception as e:
            print(f"[数据分析] 知识库检索失败: {e}")

    # 构建分析概要描述
    summary = analysis["summary"]
    col_descriptions = []
    for c in analysis["columns"]:
        desc = f"- {c['name']} ({c['dtype']}): {c['non_null_count']}/{summary['rows']} 非空"
        if "min" in c:
            desc += f", 范围 [{c['min']}, {c['max']}], 均值={c['mean']}"
        if "outlier_count" in c and c["outlier_count"] > 0:
            desc += f", 异常值 {c['outlier_count']} 个"
        if c["null_count"] > 0:
            desc += f", 缺失值 {c['null_count']} 个 ({c['null_ratio']}%)"
        col_descriptions.append(desc)

    missing_desc = ""
    if analysis["missing_values"]["has_missing"]:
        missing_desc = f"\n缺失值: 共 {analysis['missing_values']['total_missing_cells']} 个单元格 ({analysis['missing_values']['missing_ratio']}%)"

    duplicates_desc = ""
    if analysis["duplicates"]["has_duplicates"]:
        duplicates_desc = f"\n重复行: {analysis['duplicates']['duplicate_rows']} 行 ({analysis['duplicates']['duplicate_ratio']}%)"

    user_req = f"\n用户特别关注: {user_question}" if user_question else ""

    messages = [
        {
            "role": "system",
            "content": """你是一个数据分析专家。根据提供的数据文件分析结果，生成一份自然语言的数据分析报告。"""
            + ("\n\n参考以下知识库信息分析数据是否符合业务规范，并在报告中注明引用的知识库来源。" if kb_context else "")
        },
        {
            "role": "user",
            "content": f"""请分析以下数据文件信息，生成一份自然语言的数据分析报告。

文件概览:
- 文件名: {summary['filename']}
- 行数: {summary['rows']}, 列数: {summary['columns']}

列详情:
{chr(10).join(col_descriptions)}
{missing_desc}
{duplicates_desc}{user_req}
{kb_context}

请生成详细的数据分析报告。"""
        }
    ]

    try:
        report = _call_deepseek_api(messages)
        return report.strip()
    except Exception as e:
        print(f"[文件分析] AI 报告生成失败: {e}")
        return "AI 分析报告暂时无法生成，请查看上方数据分析统计。" if user_question else "AI 分析报告暂时无法生成，请查看上方数据分析统计。"


# ============ 文档合规性检查 ============

async def analyze_document_compliance(
    file_path: str,
    org_code: str = "default",
    departments: list = None,
    user_notes: str = ""
) -> dict:
    """
    分析上传文档与公司知识库中制度/规范的合规性（支持多知识库）。

    参数:
        file_path: 上传文档路径
        org_code: 组织编码
        departments: 部门列表，指定要检索的知识库
        user_notes: 用户补充说明

    返回:
        {
            "status": "completed"/"error",
            "document_summary": 文档概览,
            "compliance_items": 合规项目列表,
            "overall_assessment": 总体评估,
            "suggestions": 改进建议
        }
    """
    from document_loader import _parse_file
    from vector_store import search_similar_multi
    from embedding import get_embedding
    from llm import _call_deepseek_api

    doc_path = Path(file_path)
    if not doc_path.exists():
        return {"status": "error", "message": "文件不存在"}

    # 1. 提取文档内容
    try:
        doc_text = _parse_file(doc_path)
    except Exception as e:
        return {"status": "error", "message": f"文档解析失败: {str(e)}"}

    if not doc_text.strip():
        return {"status": "error", "message": "文档内容为空"}

    # 截取合理长度（避免 token 超限）
    max_content_length = 8000
    if len(doc_text) > max_content_length:
        doc_text = doc_text[:max_content_length] + "\n\n[文档较长，已截取前8000字符进行分析]"

    # 2. 从知识库检索相关制度（支持多知识库）
    if not departments:
        departments = ["general"]

    related_policies = []
    try:
        question_embedding = await get_embedding(doc_text[:2000])
        results = search_similar_multi(
            question_embedding,
            top_k_per_dept=3,
            departments=departments,
            org_code=org_code
        )
        # 过滤低相似度结果
        from config import SIMILARITY_THRESHOLD
        related_policies = [
            r for r in results
            if r["similarity"] >= max(SIMILARITY_THRESHOLD, 0.5)
        ]
    except Exception as e:
        print(f"[合规检查] 知识库检索失败: {e}")

    # 3. 如果没有检索到相关制度，尝试用文档关键词再搜一次
    if not related_policies:
        try:
            # 提取文档中可能的关键词
            keywords = doc_text[:500]
            kw_embedding = await get_embedding(keywords)
            results = search_similar_multi(
                kw_embedding,
                top_k_per_dept=3,
                departments=departments,
                org_code=org_code
            )
            related_policies = [
                r for r in results
                if r["similarity"] >= max(SIMILARITY_THRESHOLD, 0.5)
            ]
        except Exception as e:
            print(f"[合规检查] 二次检索失败: {e}")

    # 4. 组装 prompt 调用 LLM 进行分析
    policy_context = ""
    if related_policies:
        policy_context = "\n\n---\n\n".join([
            f"[来源: {r['metadata'].get('filename', '未知')}] (相似度: {r['similarity']:.2f})\n{r['text']}"
            for r in related_policies
        ])
    else:
        policy_context = "知识库中未找到直接相关的制度或规范。请仅基于一般合规常识进行分析，并注明知识库中缺少相关制度。"

    user_notes_section = f"\n用户补充说明: {user_notes}" if user_notes else ""

    messages = [
        {
            "role": "system",
            "content": """你是一个合规分析专家。你的任务是根据企业知识库中的制度/规范，对用户上传的文档进行合规性检查。

请从以下维度进行分析：
1. 符合项：列出文档中符合相关制度的条款
2. 不符合项：列出文档中与制度不一致的条款（并引用制度原文）
3. 风险评估：对每个不符合项评估风险等级（高/中/低）
4. 总体评估：给出整体合规评分（优/良/中/差）
5. 改进建议：针对不符合项给出具体的修改建议

注意：
- 如果知识库中缺乏相关制度，请明确注明
- 只能基于提供的知识库内容进行判断
- 保持客观，避免过度解读"""
        },
        {
            "role": "user",
            "content": f"""请对以下上传文档进行合规性检查。

=== 上传文档内容 ===
{doc_text}
{user_notes_section}

=== 知识库中的相关制度/规范 ===
{policy_context}

请提供详细的合规检查报告。"""
        }
    ]

    try:
        compliance_report = _call_deepseek_api(messages)
    except Exception as e:
        return {"status": "error", "message": f"AI 分析失败: {str(e)}"}

    # 5. 构建结果
    result = {
        "status": "completed",
        "document_summary": {
            "filename": doc_path.name,
            "file_size": doc_path.stat().st_size,
            "content_length": len(doc_text),
            "has_knowledge_base_reference": len(related_policies) > 0,
            "knowledge_base_sources": list(set(
                r["metadata"].get("filename", "未知") for r in related_policies
            ))
        },
        "compliance_report": compliance_report.strip(),
        "related_policies": [
            {
                "filename": r["metadata"].get("filename", "未知"),
                "similarity": round(r["similarity"], 4),
                "excerpt": r["text"][:200]
            }
            for r in related_policies
        ]
    }

    return result


# ============ 辅助函数 ============

def _safe_round(value, decimals=2):
    """安全四舍五入，处理 NaN/None"""
    if pd.isna(value) or value is None:
        return None
    return round(float(value), decimals)
