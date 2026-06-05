"""
unified-report-generator — 统一报告生成模块

独立于 ProjectMgr 的通用报告生成引擎，支持：
- 从 Excel 台账读取记录并过滤
- 自动提取交付文档内容
- 生成 Markdown 报告
- 生成金融风格 Word (.docx) 报告
- 可选 AI 增强（LLM 润色 + 图表）
"""

from .config import (
    REPORT_TYPES,
    WORK_SHEETS,
    DOCUMENT_EXTENSIONS,
    TMP_REPORTS,
    set_reports_dir,
)
from .generator import (
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

__all__ = [
    # config
    "REPORT_TYPES",
    "WORK_SHEETS",
    "DOCUMENT_EXTENSIONS",
    "TMP_REPORTS",
    "set_reports_dir",
    # generator
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
