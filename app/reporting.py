"""
app.reporting — ProjectMgr 兼容层

委派给 unified-report-generator 独立模块。
保留原公开 API 签名以确保 server.py 及其他调用方无需修改。
"""

import sys as _sys
from pathlib import Path as _Path

# ── 将 unified-report-generator 加入搜索路径 ──
_REPORT_PKG = _Path(__file__).resolve().parent.parent / "unified-report-generator"
if _REPORT_PKG.exists():
    _sys.path.insert(0, str(_REPORT_PKG))

# ── 同步输出目录为 app.config 中的 TMP_REPORTS ──
from .config import TMP_REPORTS as _APP_TMP_REPORTS
from unified_report_generator.config import set_reports_dir as _set_reports_dir
_set_reports_dir(str(_APP_TMP_REPORTS))

# ── 全部从 standalone 包中重新导出 ──
from unified_report_generator import (
    REPORT_TYPES,
    WORK_SHEETS,
    DOCUMENT_EXTENSIONS,
    parse_date,
    parse_iso_date,
    load_records,
    stringify,
    markdown_cell,
    normalize_doc_name,
    build_document_index,
    find_delivery_document,
    extract_document_text,
    summarize_document_chunks,
    collect_delivery_document_summaries,
    top_counts,
    filter_weekly_records,
    generate_report,
    generate_report_with_ai,
    generate_weekly_report,
    generate_monthly_report,
    generate_quarterly_report,
    generate_annual_report,
)
from unified_report_generator.config import KEY_CONTENT_WORDS

__all__ = [
    "REPORT_TYPES",
    "WORK_SHEETS",
    "DOCUMENT_EXTENSIONS",
    "KEY_CONTENT_WORDS",
    "parse_date",
    "parse_iso_date",
    "load_records",
    "stringify",
    "markdown_cell",
    "normalize_doc_name",
    "build_document_index",
    "find_delivery_document",
    "extract_document_text",
    "summarize_document_chunks",
    "collect_delivery_document_summaries",
    "top_counts",
    "filter_weekly_records",
    "generate_report",
    "generate_report_with_ai",
    "generate_weekly_report",
    "generate_monthly_report",
    "generate_quarterly_report",
    "generate_annual_report",
]
