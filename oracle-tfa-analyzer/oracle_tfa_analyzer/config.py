"""全局配置：路径、常量、方向定义、TFA 文件分类。"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_parent_config() -> dict:
    """读取父项目 config.yaml，实现统一的临时目录配置。"""
    try:
        import yaml
        cfg_path = PROJECT_ROOT.parent / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg if isinstance(cfg, dict) else {}
    except Exception:
        pass
    return {}


_cfg = _load_parent_config()
_tmp_root = Path(
    _cfg.get("tmp_dir") or os.environ.get("PROJECTMGR_TMP_DIR", "/Users/peyton/tmp")
).expanduser().resolve()

# 所有临时/输出目录统一放在 TMP 根目录下
TEMP_DIR = _tmp_root / "tfa_temp"
OUTPUT_DIR = _tmp_root / "output"

# 确保目录存在
if _cfg.get("auto_create", True):
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

# ============================================================
# FILE_PATTERNS: glob 通配符，匹配标准 CI 路径下的日志文件
# ============================================================
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
    "agent_log":        ["**/agent/**/*.log", "**/emagent/**/*.log", "**/agent/**/*.trc"],
    "gpnp_log":         ["**/gpnp/**/*.log"],
    "chm_metadata":     ["**/CHMDATA/**/*.json", "**/CHMDATA/**/*.xml"],
    "cvu_data":         ["**/CVU/**/*"],
    "calog":            ["**/CALOG/**"],
    "tfa_config":       ["**/config.properties"],
}

# ============================================================
# ROOT_SNAPSHOT_CLASSIFIER: 分类 TFA 根目录下的 {hostname}_{SUFFIX} 快照文件
# Key   = 文件后缀（全大写，实际匹配大小写不敏感）
# Value = 类别名（供 discover_root_snapshots 输出分组）
# ============================================================
ROOT_SNAPSHOT_CLASSIFIER: dict[str, str] = {
    # --- OCR / OLR / CRS ---
    "OCRBACKUP":                "ocr_info",
    "OCRDUMP":                  "ocr_info",
    "OLRDUMP":                  "ocr_info",
    "GETCSS":                   "cluster_state",
    "QUERYVOTE":                "voting_disk",
    "CHECKCRS":                 "crs_health",
    "STATRESCRS":               "crs_resource",
    "STATRESCRSFULL":           "crs_resource",
    "STATRESDEPENDENCY":        "crs_resource",
    "STATRESOHAS":              "crs_resource",
    "STATRESFULLOHAS":          "crs_resource",
    "STATRESOHASDEPENDENCY":    "crs_resource",
    "CRSCTL_CONFIG_CRS":        "crs_config",
    "CRSCTL_QUERY_CRS_ACTIVEVERSION": "crs_config",
    "OHASDRUN":                 "crs_config",

    # --- 集群状态 ---
    "CLUSTERCONFIG":            "cluster_config",
    "CHA_STATUS":               "cluster_state",
    "CRSPATCHCKPT_STATUS":      "patch_status",
    "NODEAPPS":                 "cluster_config",
    "OLSNODES":                 "cluster_config",
    "CONFIGGNS":                "cluster_config",
    "CONFIGSCAN":               "cluster_config",
    "GPNPTOOL":                 "cluster_config",
    "GPNP_PEER_PROFILE_XML":    "cluster_config",
    "GPNS_PEER_PROFILE_XML":    "cluster_config",
    "SRCFG_JSON":               "cluster_config",
    "SRCFG_LOG":                "cluster_config",
    "CALOG":                    "cluster_state",
    "CRS_COLLECTION_ERR":       "cluster_state",
    "CRS_COLLECTION_LOG":       "cluster_state",

    # --- ASM 配置 ---
    "CONFIGASM":                "asm_config",
    "DEV_ASM_CONTENTS":         "asm_config",
    "OIFCFG":                   "network_config",
    "STATASMRESOURCEGROUP":     "asm_config",
    "ASM_COLLECTION_ERR":       "asm_config",
    "ASM_COLLECTION_LOG":       "asm_config",
    "ASM_COLLECTION_OUT":       "asm_config",

    # --- ACFS ---
    "ORACLEAFD_CONF":           "acfs_config",
    "AFDTOOL_KSTATE":           "acfs_config",
    "AFD_COLLECTION_LOG":       "acfs_config",
    "ACFSDUMPSTATS":            "acfs_status",
    "ACFSROOT_VERSION_CHECK":   "acfs_status",
    "ACFSUTILLOG":              "acfs_status",
    "ACFSUTILPLOGCONFIG":       "acfs_status",
    "ACFS_DRIVER_STATE_INFO":   "acfs_status",
    "ACFS_COLLECTION_ERR":      "acfs_status",
    "ACFS_COLLECTION_LOG":      "acfs_status",
    "ACFS_REPORT":              "acfs_status",

    # --- GI / 补丁版本 ---
    "SOFTWAREVERSION":          "gi_version",
    "ACTIVEVERSION":            "gi_version",
    "OPATCH_CRS":               "patch_info",
    "OPATCH_DBHOMES":           "patch_info",
    "OPATCH_LSINVENTORY":       "patch_info",

    # --- ADG ---
    "DATAGUARD__REPORT":        "adg_status",
    "DATAGUARD_COLLECTION_ERR": "adg_status",
    "DATAGUARD_COLLECTION_LOG": "adg_status",

    # --- OS 进程 / 内存 ---
    "PS":                       "os_process",
    "PIDS":                     "os_process",
    "TOP_50_MEMORY":            "os_memory",
    "SWAPINFO":                 "os_memory",

    # --- OS 网络 ---
    "NETSTAT":                  "os_network",
    "NSLOOKUP":                 "os_network",
    "PING_INFO":                "os_network",
    "IFCONFIG":                 "os_network",
    "IFCONFIG_A":               "os_network",
    "DHCP":                     "os_network",
    "HOSTS":                    "os_network",
    "RESOLV":                   "os_network",
    "ROUTE":                    "os_network",
    "ARP":                      "os_network",
    "DNSSERVERS":               "os_network",

    # --- OS 硬件 ---
    "IPMI":                     "os_hardware",
    "PRTDIAG":                  "os_hardware",
    "PRTCONF":                  "os_hardware",
    "DMIDECODE":                "os_hardware",
    "LSHW":                     "os_hardware",
    "LSPCI":                    "os_hardware",
    "DEVICES":                  "os_hardware",

    # --- OS 内核 ---
    "DMESG":                    "os_kernel",
    "LSMOD":                    "os_kernel",

    # --- OS 系统状态 ---
    "RUNLEVEL":                 "os_system",
    "INITTAB":                  "os_system",
    "UPSTATUS":                 "os_system",
    "UPTIME":                   "os_system",
    "LAST":                     "os_system",
    "WHO":                      "os_system",
    "PROCDIRINFO":              "os_system",
    "VARTMPORACLE":             "os_system",
    "OS_COLLECTION_ERR":        "os_system",
    "OS_COLLECTION_LOG":        "os_system",
    "OS_REPORT":                "os_system",

    # --- OS 配置 ---
    "NSSWITCH_CONF":            "os_config",
    "ULIMIT":                   "os_config",
    "ENV":                      "os_config",
    "CRONTAB":                  "os_config",
    "SERVICES":                 "os_config",
    "SERVICE":                  "os_config",
    "SYSTEM":                   "os_config",
    "SYSCTL":                   "os_config",
    "SYSCTL_A":                 "os_config",
    "LIMITS":                   "os_config",

    # --- OS 软件包 / 补丁 ---
    "RPMQA":                    "os_packages",
    "RPM_QA":                   "os_packages",
    "ospackages":               "os_packages",
    "ospatches":                "os_packages",
    "OPATCHA":                  "os_packages",

    # --- OS 挂载 / 存储 ---
    "MTAB":                     "os_mount",
    "FSTAB":                    "os_mount",
    "EXPORTS":                  "os_mount",
    "DF":                       "os_mount",
    "MOUNT":                    "os_mount",
    "LVMTAB":                   "os_mount",
    "PVS":                      "os_mount",
    "VGS":                      "os_mount",
    "LVS":                      "os_mount",

    # --- OS 性能 ---
    "VMSTAT":                   "os_perf",
    "IOSTAT":                   "os_perf",
    "MPSTAT":                   "os_perf",
    "SAR":                      "os_perf",
    "SAR_CPU":                  "os_perf",
    "SAR_IO":                   "os_perf",
    "SAR_MEMORY":               "os_perf",
    "SAR_LOAD":                 "os_perf",
    "SAR_NETWORK":              "os_perf",
    "SAR_SWAP":                 "os_perf",
    "TOP":                      "os_perf",
    "FREE":                     "os_perf",

    # --- OS 目录列表 ---
    "LS":                       "os_ls",
    "LS_L":                     "os_ls",
    "LS_LTR":                   "os_ls",
    "FIND":                     "os_ls",

    # --- TFA 自身 ---
    "SUMMARY":                  "tfa_summary",
    "TFA_CONFIG":               "tfa_summary",
    "TFA_STATUS":               "tfa_summary",
    "TFA_HISTORY":              "tfa_summary",
    "CLOUDMETADATA_LOG":        "tfa_summary",
    "COLLECTION_ERR":           "tfa_summary",
    "COLLECTION_LOG":           "tfa_summary",
    "PRINT_COLLECTIONS_JSON":   "tfa_summary",
    "QOSCTLCOLLECT_LOG":        "tfa_summary",
    "SOSREPORTCOLLECT_LOG":     "tfa_summary",
    "SYSLENS_REPORT_LOG":       "tfa_summary",

    # --- 带扩展名的变体（处理 _SUFFIX.ext 格式） ---
    "SRCFG.JSON":               "cluster_config",
    "SRCFG.LOG":                "cluster_config",
    "GPNP_PEER_PROFILE.XML":    "cluster_config",
    "PRINT_COLLECTIONS.JSON":   "tfa_summary",
    "DATAGUARD_COLLECTION.ERR": "adg_status",
    "DATAGUARD_COLLECTION.LOG": "adg_status",
    "DATAGUARD__REPORT":        "adg_status",
    "ACFS_COLLECTION.ERR":      "acfs_status",
    "ACFS_COLLECTION.LOG":      "acfs_status",
    "AFD_COLLECTION.LOG":       "acfs_config",
    "ASM_COLLECTION.ERR":       "asm_config",
    "ASM_COLLECTION.LOG":       "asm_config",
    "ASM_COLLECTION.OUT":       "asm_config",
    "CLOUDMETADATA.LOG":        "tfa_summary",
    "COLLECTION.ERR":           "tfa_summary",
    "COLLECTION.LOG":           "tfa_summary",
    "CRS_COLLECTION.ERR":       "cluster_state",
    "CRS_COLLECTION.LOG":       "cluster_state",
    "OS_COLLECTION.ERR":        "os_system",
    "OS_COLLECTION.LOG":        "os_system",
    "QOSCTLCOLLECT.LOG":        "tfa_summary",
    "SOSREPORTCOLLECT.LOG":     "tfa_summary",
    "SYSLENS_REPORT.LOG":       "tfa_summary",

    # --- pa00db12 特有 ---
    "AFD_REPORT":               "acfs_config",
    "CLOUDMETADATA.OUT":        "tfa_summary",
    "OCRLOC":                   "ocr_info",
    "OLRLOC":                   "ocr_info",
    "ORATAB":                   "os_config",
    "OS-RELEASE":               "os_config",
    "REDHAT-RELEASE":           "os_config",
}

# ============================================================
# CATEGORY_MAP: 将 ROOT_SNAPSHOT_CLASSIFIER 的细粒度类别
#               映射回 ANALYSIS_CATEGORIES 所属的大类
# ============================================================
CATEGORY_MAP: dict[str, str] = {
    "cluster_config":       "RAC/Clusterware",
    "cluster_state":        "RAC/Clusterware",
    "ocr_info":             "RAC/Clusterware",
    "voting_disk":          "RAC/Clusterware",
    "crs_health":           "RAC/Clusterware",
    "crs_resource":         "RAC/Clusterware",
    "crs_config":           "RAC/Clusterware",
    "patch_status":         "RAC/Clusterware",
    "gi_version":           "RAC/Clusterware",
    "patch_info":           "RAC/Clusterware",
    "asm_config":           "ASM/存储",
    "network_config":       "RAC/Clusterware",
    "acfs_config":          "ASM/存储",
    "acfs_status":          "ASM/存储",
    "adg_status":           "ADG/备份",
    "os_process":           "OS 资源",
    "os_memory":            "OS 资源",
    "os_network":           "OS 资源",
    "os_hardware":          "OS 资源",
    "os_kernel":            "OS 资源",
    "os_system":            "OS 资源",
    "os_config":            "OS 资源",
    "os_packages":          "OS 资源",
    "os_mount":             "OS 资源",
    "os_perf":              "OS 资源",
    "os_ls":                "OS 资源",
    "tfa_summary":          "参考",
}
