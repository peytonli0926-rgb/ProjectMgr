"""全局配置：路径、常量、方向定义。"""

from pathlib import Path

# ── 运行时目录 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = PROJECT_ROOT / ".tfa_temp"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ── 八大分析方向（排序固定，用于报告） ──
ANALYSIS_CATEGORIES = [
    "数据库错误与稳定性",
    "RAC/Clusterware",
    "ASM/存储",
    "OS 资源",
    "I/O 性能",
    "连接/监听",
    "SQL/性能争用",
    "ADG/备份",
]

# ── 风险等级 ──
RISK_CRITICAL = "critical"
RISK_HIGH = "high"
RISK_MEDIUM = "medium"
RISK_LOW = "low"
RISK_INFO = "info"

RISK_LABELS = {
    RISK_CRITICAL: "严重",
    RISK_HIGH: "高",
    RISK_MEDIUM: "中",
    RISK_LOW: "低",
    RISK_INFO: "参考",
}

# ── TFA zip 包内常见文件 glob 模式（用于分类扫描） ──
FILE_PATTERNS = {
    "alert_log":        ["**/alert*.log", "**/alert*.xml"],
    "listener_log":     ["**/listener*.log"],
    "asm_alert":        ["**/asm/alert*/alert*.log"],
    "crs_log":          ["**/crs*/log/**/*.log", "**/crs*/log/**/*.trc"],
    "os_info":          ["**/os*/**/*.out", "**/os*/**/*.log"],
    "rman_log":         ["**/rman*/**/*.log"],
    "awr_report":       ["**/awr*.html", "**/awr*.txt", "**/*.lst"],
    "sql_trace":        ["**/*.trc", "**/*.trm"],
    "adg_log":          ["**/*adg*.log", "**/dr*.log", "**/*dataguard*"],
}
