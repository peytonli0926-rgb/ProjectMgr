"""
awr-auto-analyzer 全局配置

所有临时文件、输出目录、模型地址等集中管理。
"""

import os
from pathlib import Path

# ── 项目根目录 ──
ROOT = Path(__file__).resolve().parent.parent

# ── 输出目录（可通过环境变量 AWR_OUTPUT_DIR 覆盖） ──
OUTPUT_DIR = Path(os.environ.get("AWR_OUTPUT_DIR", str(ROOT / "output")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 数据目录 ──
DATA_DIR = Path(os.environ.get("AWR_DATA_DIR", str(ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 图表目录 ──
CHART_DIR = OUTPUT_DIR / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# ── DeepSeek / Ollama 模型 ──
DEFAULT_DEEPSEEK_URL = os.environ.get("LOCAL_DEEPSEEK_URL", "http://127.0.0.1:11434/api/chat")
DEFAULT_DEEPSEEK_MODEL = os.environ.get("LOCAL_DEEPSEEK_MODEL", "deepseek-r1")

# 在线 DeepSeek / OpenAI 兼容模型
DEFAULT_ONLINE_URL = os.environ.get("ONLINE_DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
DEFAULT_ONLINE_MODEL = os.environ.get("ONLINE_DEEPSEEK_MODEL", "deepseek-chat")

# ── Word 报告样式（金融行业专业配色方案） ──
FONT_CN = "Microsoft YaHei"
FONT_MONO = "Consolas"

# 主色调：深海蓝 + 金色强调
COLOR_PRIMARY = "1B3A5C"       # 深海蓝 — 封面/主标题/页眉
COLOR_ACCENT = "C8A96E"        # 香槟金 — 强调/分割线/表头装饰
COLOR_ACCENT_LIGHT = "E8DCC8"  # 浅金色 — 特殊块背景

# 标题层级
COLOR_TITLE = "1B3A5C"         # H1 — 深海蓝
COLOR_H2 = "2C5F8A"            # H2 — 中蓝
COLOR_H3 = "4A7BA7"            # H3 — 浅蓝

# 正文与背景
COLOR_BODY = "2C3E50"          # 正文 — 深灰蓝
COLOR_MUTED = "7F8C8D"         # 辅助文字 — 中灰
COLOR_BG_LIGHT = "F5F7FA"     # 浅灰蓝背景（表格斑马纹/页面背景）
COLOR_BG_DARK = "1B3A5C"      # 深色背景（表头）

# 表格
COLOR_TABLE_HEAD = "1B3A5C"    # 表头底色 — 深海蓝
COLOR_BORDER = "D5DDE5"        # 边框 — 浅灰蓝
COLOR_TABLE_ALT = "F0F3F7"     # 斑马纹隔行色

# 特殊块配色
COLOR_CONCLUSION_BG = "EBF0F7"  # 结论块背景
COLOR_CONCLUSION_ACCENT = "1B3A5C"
COLOR_RISK_BG = "FDEDED"       # 风险块背景
COLOR_RISK_ACCENT = "C0392B"
COLOR_EVIDENCE_BG = "F2F4F4"   # 证据块背景
COLOR_EVIDENCE_ACCENT = "7F8C8D"
COLOR_ADVICE_BG = "E8F0E8"     # 建议块背景
COLOR_ADVICE_ACCENT = "27AE60"

# 风险等级色标
COLOR_RISK_HIGH = "E74C3C"
COLOR_RISK_MEDIUM = "E67E22"
COLOR_RISK_LOW = "27AE60"
COLOR_RISK_NONE = "95A5A6"

# ── AWR 报告章节（中文） ──
SECTION_TITLES = [
    "总体结论",
    "风险等级判断",
    "数据库负载画像",
    "Top Wait Events 分析",
    "Top SQL 分析",
    "主机资源分析",
    "内存与参数建议",
    "问题点清单",
    "整改建议",
    "后续取证清单",
    "领导汇报摘要",
    "专家交付结论",
]
CHINESE_NUMBERS = "一二三四五六七八九十"

# ── 输出文件名 ──
AWR_SUMMARY_JSON = OUTPUT_DIR / "awr_summary.json"
AWR_SUMMARY_MD = OUTPUT_DIR / "awr_summary.md"
AWR_RULE_FINDINGS_JSON = OUTPUT_DIR / "awr_rule_findings.json"
AWR_RULE_FINDINGS_MD = OUTPUT_DIR / "awr_rule_findings.md"
AWR_ANALYSIS_MD = OUTPUT_DIR / "awr_analysis_report.md"
AWR_ANALYSIS_DOCX = OUTPUT_DIR / "awr_analysis_report.docx"
