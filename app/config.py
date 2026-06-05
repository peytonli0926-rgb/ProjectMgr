import os
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
TARGET_SUFFIX = "_desensitized"

TEXT_EXTENSIONS = {
    ".txt", ".csv", ".json", ".xml", ".yaml", ".yml", ".log", ".md",
    ".py", ".java", ".js", ".ts", ".html", ".htm", ".sql",
}
HTML_EXTENSIONS = {".html", ".htm"}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
SKIP_EXTENSIONS = set()
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | OFFICE_EXTENSIONS
# 所有扩展名都参与扫描和脱敏，非文本/Office 文件尝试以文本方式处理
ALL_EXTENSIONS = True
EXCLUDED_PARTS = {".git", "__pycache__", ".idea", ".venv", "node_modules"}

# ── 配置文件路径 ──
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

# ── 临时文件根目录（所有上传、解压、输出文件均存放于此） ──
TMP_DIR: Path = Path(os.environ.get("PROJECTMGR_TMP_DIR", "/Users/peyton/tmp"))

def _load_config() -> dict:
    """加载 config.yaml，若文件不存在或解析失败则返回空字典。"""
    try:
        import yaml
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg if isinstance(cfg, dict) else {}
    except Exception:
        pass
    return {}

def _ensure_dir(path: Path) -> Path:
    """确保目录存在（auto_create 为 True 时），返回 Path。"""
    cfg = _load_config()
    if cfg.get("auto_create", True):
        path.mkdir(parents=True, exist_ok=True)
    return path

# 从 config.yaml 覆盖 tmp_dir
_cfg = _load_config()
if "tmp_dir" in _cfg:
    TMP_DIR = Path(_cfg["tmp_dir"]).expanduser().resolve()

# 确保 TMP_DIR 存在
TMP_DIR = _ensure_dir(TMP_DIR)

# ── 基于 TMP_DIR 的常用子目录 ──
TMP_UPLOADS     = _ensure_dir(TMP_DIR / "uploads")       # AWR/LST/TFA 上传文件
TMP_OUTPUT      = _ensure_dir(TMP_DIR / "output")         # 所有输出报告
TMP_DATA        = _ensure_dir(TMP_DIR / "data")           # 扫描 / 脱敏相关数据
TMP_DESENSITIZE = _ensure_dir(TMP_DIR / "desensitize")    # 脱敏输出目录
TMP_TFA_TEMP    = _ensure_dir(TMP_DIR / "tfa_temp")       # TFA 临时解压
TMP_TFA_UPLOAD  = _ensure_dir(TMP_DIR / "tfa_uploads")    # TFA zip 上传
TMP_REPORTS     = _ensure_dir(TMP_DIR / "reports")        # 周报 / 月报等生成报告
