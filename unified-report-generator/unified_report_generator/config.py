"""
统一报告生成 - 配置

提供默认的报告类型定义、工作表和文档扩展名配置。
输出目录可通过 set_reports_dir() 动态调整。
"""

from pathlib import Path
import os

# 默认临时报告输出目录
TMP_REPORTS: Path = Path(
    os.environ.get("UNIFIED_REPORT_TMP_DIR", "/tmp/unified_reports")
)


def set_reports_dir(path: str | Path) -> Path:
    """动态设置报告输出目录，返回设置后的目录 Path。"""
    global TMP_REPORTS
    TMP_REPORTS = Path(path).expanduser().resolve()
    TMP_REPORTS.mkdir(parents=True, exist_ok=True)
    return TMP_REPORTS


# ── 台账工作表名称 ──
WORK_SHEETS = ("一线支持", "二线支持")

# ── 可搜索的交付文档扩展名 ──
DOCUMENT_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".txt", ".md", ".log"}

# ── 报告类型定义 ──
REPORT_TYPES = {
    "weekly": {
        "title": "周报",
        "file_prefix": "weekly_report",
        "focus_title": "本周重点事项",
        "plan_title": "下周计划",
        "plan_items": [
            "根据本周延续事项和风险事项持续跟进。",
            "对未闭环问题补充责任人、计划完成时间和处理进展。",
            "对重点系统服务事项进行复盘和材料归档。",
        ],
    },
    "monthly": {
        "title": "月报",
        "file_prefix": "monthly_report",
        "focus_title": "本月重点事项",
        "plan_title": "下月计划",
        "plan_items": [
            "围绕本月高频问题和重点系统制定改进计划。",
            "对延续事项形成闭环跟踪清单。",
            "整理交付文档和服务指标，沉淀月度服务材料。",
        ],
    },
    "quarterly": {
        "title": "季度报",
        "file_prefix": "quarterly_report",
        "focus_title": "本季度重点事项",
        "plan_title": "下季度计划",
        "plan_items": [
            "结合季度趋势识别重点风险和改进方向。",
            "对关键系统、重点事件、迁移和优化事项进行复盘。",
            "形成下季度服务策略和重点保障计划。",
        ],
    },
    "annual": {
        "title": "年度报告",
        "file_prefix": "annual_report",
        "focus_title": "年度重点事项",
        "plan_title": "下一年度计划",
        "plan_items": [
            "总结全年服务成果、重点风险和改进成效。",
            "沉淀关键系统支持经验和交付文档资产。",
            "制定下一年度服务规划、风险治理和能力提升计划。",
        ],
    },
}

# ── 文档摘要提取时关注的重点关键词 ──
KEY_CONTENT_WORDS = (
    "问题", "原因", "根因", "处理", "解决", "结果", "结论", "风险", "影响", "建议",
    "优化", "变更", "迁移", "巡检", "故障", "异常", "ORA-", "SQL", "数据库",
)
