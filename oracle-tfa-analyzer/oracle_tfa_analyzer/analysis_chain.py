"""分析链生成模块。

从关键日志入口（entry files）出发，构建完整的故障分析链路。
每条链展示：入口文件 → 发现的问题 → 关联的根快照 → 相关证据 → 根因结论。

支持如下入口文件类型：
  - alert_*.log          (数据库警告日志)
  - crsd.log / cssd.log  (集群日志)
  - listener_*.log       (监听日志)
  - asm_alert.log        (ASM 警告日志)
  - DMESG / OS 快照      (OS 级别入口)
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── 入口文件分类器 ──
ENTRY_CLASSIFIER: dict[str, str] = {
    # 数据库入口
    "alert_log": "🚨 数据库警告日志",
    "asm_alert": "💾 ASM 警告日志",
    # 集群入口
    "crs_log":   "🔗 CRS 集群日志",
    # 监听入口
    "listener_log": "📡 监听器日志",
    # 性能/OS 快照入口
    "os_perf":  "🖥️ OS 性能快照",
    "os_kernel": "🖥️ OS 内核日志",
    "os_process": "🖥️ OS 进程快照",
    "os_memory": "🖥️ OS 内存快照",
    "os_network": "🌐 OS 网络快照",
    "os_system": "🖥️ OS 系统状态",
    "os_mount": "💾 OS 存储/挂载",
    "os_hardware": "🖥️ OS 硬件信息",
    # ASM/ADG 入口
    "asm_config": "💾 ASM 配置",
    "adg_status": "🔄 ADG 状态",
    # RAC 入口
    "cluster_config": "🔗 集群配置",
    "cluster_state":  "🔗 集群状态",
    "crs_health":     "🔗 CRS 健康检查",
    "crs_resource":   "🔗 CRS 资源",
    "ocr_info":       "🔗 OCR 信息",
    "voting_disk":    "🔗 Voting Disk",
}

# ── 入口 → 根快照关联映射 ──
# 当入口文件发现问题时，建议查看哪些根快照来交叉验证
ENTRY_RELATED_SNAPSHOT_CATEGORIES: dict[str, list[str]] = {
    "alert_log":        ["os_perf", "os_kernel", "os_process", "os_memory", "os_system", "os_network", "os_mount"],
    "asm_alert":        ["asm_config", "os_mount", "os_perf", "os_kernel"],
    "crs_log":          ["ocr_info", "voting_disk", "crs_health", "crs_resource", "cluster_state", "cluster_config", "os_network"],
    "listener_log":     ["os_network", "os_process"],
    "os_perf":          ["os_process", "os_memory", "os_kernel", "os_mount", "os_network"],
    "os_kernel":        ["os_system", "os_hardware", "os_perf", "os_process"],
    "os_process":       ["os_perf", "os_memory", "os_kernel"],
    "os_memory":        ["os_process", "os_perf"],
    "os_network":       ["os_system", "os_process"],
    "os_system":        ["os_perf", "os_kernel", "os_process", "os_memory", "os_mount"],
    "os_mount":         ["os_perf", "os_kernel", "os_system"],
    "os_hardware":      ["os_kernel", "os_perf", "os_system"],
    "asm_config":       ["os_mount", "os_perf", "voting_disk"],
    "adg_status":       ["os_network", "os_perf", "os_mount"],
    "cluster_config":   ["crs_health", "crs_resource", "ocr_info", "voting_disk", "os_network"],
    "cluster_state":    ["crs_health", "ocr_info", "voting_disk", "os_perf", "os_network"],
    "crs_health":       ["cluster_state", "ocr_info", "voting_disk", "os_network"],
    "crs_resource":     ["cluster_state", "crs_health"],
    "ocr_info":         ["voting_disk", "cluster_state", "os_mount"],
    "voting_disk":      ["ocr_info", "cluster_state", "os_mount", "os_perf"],
}

# ── 入口 → 规则 ID 关联 ──
# 标记哪些规则通常从哪些入口文件发现
ENTRY_RULE_CATEGORIES: dict[str, list[str]] = {
    "alert_log":        ["DB-", "ORA-", "INST-"],
    "asm_alert":        ["ASM-", "ORA-", "DB-"],
    "crs_log":          ["RAC-"],
    "listener_log":     ["LISTENER-", "LSN-"],
    "os_perf":          ["OS-", "IO-"],
    "os_kernel":        ["OS-"],
    "os_process":       ["OS-"],
    "os_memory":        ["OS-"],
    "os_network":       ["OS-", "LISTENER-"],
    "os_system":        ["OS-"],
    "os_mount":         ["ASM-", "OS-"],
    "os_hardware":      ["OS-"],
    "asm_config":       ["ASM-"],
    "adg_status":       ["ADG-"],
    "cluster_config":   ["RAC-"],
    "cluster_state":    ["RAC-"],
    "crs_health":       ["RAC-"],
    "crs_resource":     ["RAC-"],
    "ocr_info":         ["RAC-"],
    "voting_disk":      ["RAC-"],
}




# ── 规则级分析方法论 ──
# 针对每个规则 ID，定义具体的文件检查步骤和关联分析方法。
# 架构师/用户可以按此模板添加新规则的分析方法论。
# 每条方法论包含：
#   - primary_entry_types: 该规则通常从哪些入口文件发现
#   - examination_chain: 具体的文件检查步骤（有序列表）
#   - cross_references: 需要交叉验证的文件/规则
#   - root_cause_indicators: 根因判定依据
# 后续可添加更多规则的方法论
RULE_ANALYSIS_METHODOLOGY: dict[str, dict] = {

    # ═══════════════════════════════════════════════
    # 数据库错误与稳定性 (DB-001 ~ DB-005)
    # ═══════════════════════════════════════════════

    "DB-001": {
        "title": "ORA-00600 内部错误",
        "category": "数据库错误与稳定性",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "alert_log_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-00600 错误及其错误参数（arg [a],[b],[c],[d]）",
                "analysis_action": "记录 ORA-00600 的完整错误行及参数，确定错误类型（如 kcbzib/ktfbhcheck 等）",
            },
            {
                "step": "trace_file_analysis",
                "files_to_check": ["<SID>_ora_<PID>.trc", "<SID>_ora_<PID>.trm"],
                "what_to_look_for": "Call Stack Trace — 查看哪些函数调用导致 ORA-00600",
                "analysis_action": "分析 call stack 顶部函数，判断是逻辑损坏还是 bug",
            },
            {
                "step": "incident_file_check",
                "files_to_check": ["<SID>_inc_<ID>_<PID>.trc", "incident/incdir_<ID>/"],
                "what_to_look_for": "Incident 文件中 ORA-00600 的完整上下文和错误堆栈",
                "analysis_action": "检查 incident 文件中的 Call Stack 和 Error Reference 编号",
            },
            {
                "step": "db_alert_timeline",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-00600 前后各 5 分钟的日志，查找关联错误（如 ORA-07445、ORA-00604）",
                "analysis_action": "绘制时间线，判断 ORA-00600 是否由其他故障引发",
            },
            {
                "step": "os_snapshot_crosscheck",
                "files_to_check": ["os_perf/top*.txt", "os_perf/sar*.txt", "os_kernel/dmesg*.txt"],
                "what_to_look_for": "ORA-00600 发生时刻的 CPU 使用率、内存压力、内核错误",
                "analysis_action": "排除 OS 级硬件故障（内存错误/CPU 问题）导致的内部错误",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-002", "DB-003", "DB-005", "OS-003"],
            "validation_files": ["alert_<SID>.log", "os_kernel/dmesg*.txt", "os_perf/sar*.txt"],
            "correlation": "如果同时有 OS-003（Kernel Panic），则根因是 OS 层；否则优先怀疑 Oracle bug",
        },
        "root_cause_indicators": [
            "Call Stack 包含已知 bug 函数（如 ktfbhcheck → 块损坏）",
            "伴随 ORA-07445 → 进程异常终止",
            "伴随 OS-003/Kernel Panic → OS 内核级故障",
            "无其他关联错误 → 疑似 Oracle 软件 bug",
        ],
    },

    "DB-002": {
        "title": "ORA-07445 进程异常终止",
        "category": "数据库错误与稳定性",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "alert_log_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-07445 错误行，记录异常信号编号（SIGSEGV/SIGBUS/SIGILL）",
                "analysis_action": "识别信号类型：SIGSEGV(段错误)、SIGBUS(总线错误)、SIGILL(非法指令)",
            },
            {
                "step": "trace_file_analysis",
                "files_to_check": ["<SID>_ora_<PID>.trc", "<SID>_ora_<PID>.trm"],
                "what_to_look_for": "Call Stack Trace — 确定进程终止时的执行路径",
                "analysis_action": "分析 call stack，找出触发异常的最后一个 Oracle 函数",
            },
            {
                "step": "os_crash_check",
                "files_to_check": ["os_kernel/dmesg*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "同一时刻 OS 层是否有 OOM Killer、Kernel Panic、内存错误",
                "analysis_action": "确认是 OS 信号导致进程终止还是进程自身 bug",
            },
            {
                "step": "process_state_check",
                "files_to_check": ["os_process/ps*.txt"],
                "what_to_look_for": "ORA-07445 之后该进程是否已被 PMON 清理",
                "analysis_action": "确认进程终止是否触发了 PMON cleanup 或 instance recovery",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-001", "DB-003", "OS-001", "OS-002", "OS-003"],
            "validation_files": ["alert_<SID>.log", "os_kernel/dmesg*.txt"],
            "correlation": "SIGSEGV → 通常为 bug；SIGKILL → 可能 OOM；SIGBUS → 存储问题",
        },
        "root_cause_indicators": [
            "SIGSEGV/SIGILL → 疑似 Oracle bug",
            "SIGKILL → OOM Killer（检查 OS-002）",
            "SIGBUS → 存储/文件系统问题（检查 ASM-003）",
            "Call Stack 显示在特定功能模块中崩溃",
        ],
    },

    "DB-003": {
        "title": "ORA-00604 — 递归 SQL 错误",
        "category": "数据库错误与稳定性",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "alert_log_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-00604 及其关联的 ORA 错误（ORA-00600、ORA-07445 等）",
                "analysis_action": "ORA-00604 通常为伴随错误，需找到递归 SQL 执行时触发的主错误",
            },
            {
                "step": "recursive_sql_trace",
                "files_to_check": ["<SID>_ora_<PID>.trc"],
                "what_to_look_for": "递归 SQL 的完整执行路径和触发错误的实际 SQL",
                "analysis_action": "确定是哪个 DDL/DML 触发了递归 SQL 执行",
            },
            {
                "step": "object_validation",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-00604 前后是否有 invalid object、compilation error",
                "analysis_action": "检查是否有存储过程/函数/触发器的编译错误",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-001", "DB-002", "DB-005"],
            "validation_files": ["alert_<SID>.log"],
            "correlation": "ORA-00604 是第 2 层错误，需要找到底层主错误（通常是 DB-001/DB-002）",
        },
        "root_cause_indicators": [
            "伴随 DB-001 (ORA-00600) → 底层 bug 导致的递归 SQL 失败",
            "伴随 invalid object → 对象状态异常",
            "单独出现 → 应用触发的递归 SQL 失败",
        ],
    },

    "DB-004": {
        "title": "实例崩溃/重启记录",
        "category": "数据库错误与稳定性",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "alert_log_shutdown_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "'Shutting down instance' 或 'terminating instance' 记录",
                "analysis_action": "记录实例关闭/崩溃的确切时间戳，判断是正常 shutdown 还是 abnormal termination",
            },
            {
                "step": "pre_crash_alert_review",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "实例关闭前 2 小时内的所有 ORA- 错误和警告",
                "analysis_action": "定位导致实例崩溃的前导错误（ORA-00600、ORA-07445、ORA-00604 等）",
            },
            {
                "step": "instance_startup_check",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "之后的 'Starting ORACLE instance' / 'startup mounted' / 'startup open'",
                "analysis_action": "确认实例是否自动重启（crash → recovery → startup），记录 recovery 持续时间",
            },
            {
                "step": "recovery_phase_analysis",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "SMON recovery、redo apply、undo recovery 的记录",
                "analysis_action": "如果 recovery 时间过长，表示有大量未提交事务或 redo 生成量大",
            },
            {
                "step": "os_resource_at_crash",
                "files_to_check": ["os_perf/sar*.txt", "os_kernel/dmesg*.txt", "os_memory/free*.txt"],
                "what_to_look_for": "实例崩溃时刻的 OS 资源状态：CPU、内存、Swap、OOM、Kernel Panic",
                "analysis_action": "排除 OS 资源耗尽（OOM Killer/Swap 满）导致实例被 OS 杀死",
            },
            {
                "step": "cluster_crosscheck",
                "files_to_check": ["crsd.log", "cssd.log", "alert_<SID>.log"],
                "what_to_look_for": "RAC 环境中是否有其他节点 eviction/fencing 的记录",
                "analysis_action": "判断是否是集群层面导致节点被驱逐，进而引起实例关闭",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-001", "DB-002", "DB-003", "DB-005", "OS-003", "RAC-001", "RAC-002"],
            "validation_files": ["alert_<SID>.log", "crsd.log", "cssd.log", "os_perf/sar*.txt", "os_kernel/dmesg*.txt"],
            "correlation": "实例崩溃通常由前导错误引起，需找到原始触发原因（bug/OS 信号/OOM/存储）",
        },
        "root_cause_indicators": [
            "前导 ORA-00600 → bug 导致崩溃",
            "前导 ORA-07445 → 进程终止 → instance crash",
            "OOM Killer / 内存耗尽 → OS 杀死数据库进程",
            "Kernel Panic → OS 内核故障",
            "集群 eviction → RAC 节点被驱逐",
            "无前导错误 → 硬件故障或电源问题",
        ],
    },

    "DB-005": {
        "title": "常见数据库错误 (ORA-)",
        "category": "数据库错误与稳定性",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "alert_log_ora_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "ORA-<5位错误号>，排除 00600/07445/00604",
                "analysis_action": "按错误号分组统计频率，高频出现的错误需要优先排查",
            },
            {
                "step": "error_context_analysis",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "每个 ORA 错误前后 10 行日志，确认是否有关联错误",
                "analysis_action": "判断 ORA 错误是孤立错误还是关联故障链的一部分",
            },
            {
                "step": "frequency_pattern_analysis",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "同一 ORA 错误是否在短时间内频繁出现",
                "analysis_action": "高频重复出现表示持续性故障（如 ORA-1653 表空间满、ORA-1691 磁盘空间满）",
            },
            {
                "step": "resource_crosscheck",
                "files_to_check": ["os_perf/sar*.txt", "os_memory/free*.txt", "os_mount/df*.txt"],
                "what_to_look_for": "ORA-1653/Space 错误 → 检查 df 和表空间使用；ORA-1691 错误 → 磁盘空间",
                "analysis_action": "针对存储类 ORA 错误，交叉验证 OS 存储状态",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-001", "DB-003", "OS-002", "IO-001"],
            "validation_files": ["os_mount/df*.txt", "alert_<SID>.log"],
            "correlation": "ORA-1653(表空间满)、ORA-1691(磁盘空间满) → 存储管理问题; ORA-错误频繁 → 可能存在应用问题",
        },
        "root_cause_indicators": [
            "ORA-1653 / ORA-1691 → 空间不足",
            "ORA-00600 伴随 → bug",
            "高频 ORA 错误 → 应用或配置问题",
        ],
    },

    # ═══════════════════════════════════════════════
    # RAC/Clusterware (RAC-001 ~ RAC-005)
    # ═══════════════════════════════════════════════

    "RAC-001": {
        "title": "CRS 资源 OFFLINE",
        "category": "RAC/Clusterware",
        "primary_entry_types": ["crs_log", "cluster_state"],
        "examination_chain": [
            {
                "step": "crs_log_offline_scan",
                "files_to_check": ["crsd.log"],
                "what_to_look_for": "'OFFLINE' 与 'ora.' 或 'resource' 同时出现的行",
                "analysis_action": "记录哪些资源（VIP/ONS/Database/Listener/LSNR_ASM）处于 OFFLINE",
            },
            {
                "step": "crs_resource_check",
                "files_to_check": ["crs_resource/*.txt", "crs_health/*.txt"],
                "what_to_look_for": "有哪些资源在哪个节点上 OFFLINE，以及是否在自动重启",
                "analysis_action": "判断 OFFLINE 的原因：节点本身异常 / 依赖资源缺失 / 手动停止",
            },
            {
                "step": "dependency_chain_analysis",
                "files_to_check": ["crsd.log", "crs_resource/*.txt"],
                "what_to_look_for": "资源依赖关系链：例如 ora.XXX.db 依赖 ora.XXX.LISTENER_XXX.lsnr",
                "analysis_action": "如果某个上层依赖资源 OFFLINE，下游资源也会 OFFLINE，找到根本资源",
            },
            {
                "step": "node_health_crosscheck",
                "files_to_check": ["os_perf/top*.txt", "os_kernel/dmesg*.txt", "ocssd.log"],
                "what_to_look_for": "资源 OFFLINE 时节点本身是否存活，CSS 心跳是否正常",
                "analysis_action": "如果节点健康但资源 OFFLINE — 可能是 CRS 问题；如果节点异常 — 节点级别原因",
            },
            {
                "step": "alert_log_crosscheck",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "同一时刻数据库中是否有 ORA- 错误或 instance crash",
                "analysis_action": "数据库资源 OFFLINE 可能导致实例异常，反之亦然",
            },
        ],
        "cross_references": {
            "related_rules": ["RAC-002", "RAC-003", "RAC-004", "RAC-005"],
            "validation_files": ["crsd.log", "crs_resource/*.txt", "ocr_info/*.txt", "voting_disk/*.txt"],
            "correlation": "多个资源同时 OFFLINE → 节点问题；单个资源 OFFLINE → 该资源/依赖链问题",
        },
        "root_cause_indicators": [
            "所有资源 OFFLINE → 节点级别问题",
            "仅数据库 OFFLINE → 实例/监听器问题",
            "VIP OFFLINE → 网络问题",
            "伴随 OCR/Voting Disk 异常 → RAC-004",
        ],
    },

    "RAC-002": {
        "title": "节点隔离/重启",
        "category": "RAC/Clusterware",
        "primary_entry_types": ["crs_log", "cluster_state", "alert_log"],
        "examination_chain": [
            {
                "step": "crs_log_eviction_scan",
                "files_to_check": ["crsd.log", "cssd.log", "ocssd.log"],
                "what_to_look_for": "'evicted'、'fencing'、'node restart'、'CSSD'、'cluster communication'",
                "analysis_action": "确认节点被驱逐的确切时间、驱逐原因和被驱逐的节点名称",
            },
            {
                "step": "heartbeat_analysis",
                "files_to_check": ["crsd.log", "cssd.log"],
                "what_to_look_for": "'timeout'、'misscount'、'loss' — 心跳超时或网络延时",
                "analysis_action": "确认是私网心跳超时导致节点被驱逐，记录 misscount 和 timeout 值",
            },
            {
                "step": "network_latency_check",
                "files_to_check": ["os_network/netstat*.txt", "os_network/ifconfig*.txt"],
                "what_to_look_for": "私网网卡的丢包率、错误包数、接口状态",
                "analysis_action": "高丢包率/错误包 → 物理网络问题；接口 down → 网卡/驱动问题",
            },
            {
                "step": "storage_latency_check",
                "files_to_check": ["os_perf/sar*.txt", "os_mount/df*.txt", "voting_disk/*.txt"],
                "what_to_look_for": "Voting Disk 的 I/O 延迟和存储路径可达性",
                "analysis_action": "Voting Disk I/O 超时是导致节点被驱逐的常见原因",
            },
            {
                "step": "os_load_at_eviction",
                "files_to_check": ["os_perf/top*.txt", "os_perf/sar*.txt", "os_memory/free*.txt"],
                "what_to_look_for": "节点被驱逐时的系统负载：CPU 峰值、Swap 使用、运行队列长度",
                "analysis_action": "CPU run queue 过高/内存耗尽 → 资源耗尽导致 heartbeat 无法及时响应",
            },
            {
                "step": "alert_log_crosscheck",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "被驱逐节点上的实例是否产生了 crash / abort 记录",
                "analysis_action": "实例 crash 可能是节点被驱逐的原因或结果，需按时间顺序排列",
            },
        ],
        "cross_references": {
            "related_rules": ["RAC-001", "RAC-003", "RAC-004", "RAC-005", "OS-001", "OS-002", "IO-001"],
            "validation_files": ["crsd.log", "cssd.log", "ocssd.log", "os_network/*.txt", "voting_disk/*.txt"],
            "correlation": "私网心跳超时 + Voting Disk I/O 正常 → 网络原因；Voting Disk I/O 超时 → 存储原因；CPU 满载 → 资源原因",
        },
        "root_cause_indicators": [
            "私网心跳超时 + 丢包 → 网络原因",
            "Voting Disk I/O 延迟 > 200ms → 存储原因",
            "CPU run queue > 20 + Swap full → 资源耗尽",
            "OS-003 (Kernel Panic) → 内核级故障导致节点重启",
            "私网心跳正常 + Voting Disk 正常 → 可能是 CRS bug",
        ],
    },

    "RAC-003": {
        "title": "脑裂检测",
        "category": "RAC/Clusterware",
        "primary_entry_types": ["crs_log", "cluster_state"],
        "examination_chain": [
            {
                "step": "crs_log_reconfig_scan",
                "files_to_check": ["crsd.log", "cssd.log"],
                "what_to_look_for": "'split brain'、'reconfig'、'reconfiguration' — 集群重配置事件",
                "analysis_action": "记录每次集群重配置的时间、原因、参与的节点",
            },
            {
                "step": "voting_disk_iocheck",
                "files_to_check": ["voting_disk/*.txt"],
                "what_to_look_for": "Voting Disk 在脑裂节点间的 I/O 可达性",
                "analysis_action": "哪个节点无法访问 Voting Disk，该节点会在脑裂仲裁中被驱逐",
            },
            {
                "step": "private_network_check",
                "files_to_check": ["os_network/netstat*.txt", "os_network/ifconfig*.txt"],
                "what_to_look_for": "私网网卡状态、丢包、中断次数、错误包",
                "analysis_action": "私网故障是脑裂的最常见诱因 — 检查两个私网接口的健康状态",
            },
            {
                "step": "node_eviction_aftermath",
                "files_to_check": ["crsd.log", "ocssd.log"],
                "what_to_look_for": "脑裂后哪个节点被驱逐，以及受影响资源的恢复过程",
                "analysis_action": "确认脑裂导致的节点驱逐是否影响了数据库服务和业务",
            },
        ],
        "cross_references": {
            "related_rules": ["RAC-001", "RAC-002", "RAC-004"],
            "validation_files": ["crsd.log", "cssd.log", "voting_disk/*.txt", "os_network/*.txt"],
            "correlation": "脑裂通常由私网故障或 Voting Disk I/O 超时触发，可导致节点被驱逐",
        },
        "root_cause_indicators": [
            "私网丢包/中断 → 网络原因",
            "Voting Disk I/O 超时 → 存储原因",
            "出现 'lost contact with all nodes' → 节点完全隔离",
        ],
    },

    "RAC-004": {
        "title": "OCR/Voting Disk 异常",
        "category": "RAC/Clusterware",
        "primary_entry_types": ["crs_log", "ocr_info", "voting_disk"],
        "examination_chain": [
            {
                "step": "ocr_voting_scan",
                "files_to_check": ["ocr_info/*.txt", "voting_disk/*.txt"],
                "what_to_look_for": "'OCR error'、'corrupt'、'not accessible'、'I/O error'",
                "analysis_action": "确认哪个 OCR/Voting Disk 文件报错，记录错误类型和 I/O 状态",
            },
            {
                "step": "storage_path_check",
                "files_to_check": ["os_mount/df*.txt", "os_mount/mount*.txt"],
                "what_to_look_for": "OCR/Voting Disk 所在存储路径是否正常挂载、空间是否充足",
                "analysis_action": "路径丢失/空间满 → 存储问题；路径正常 → 文件损坏",
            },
            {
                "step": "io_perf_at_error",
                "files_to_check": ["os_perf/sar*.txt", "os_kernel/dmesg*.txt"],
                "what_to_look_for": "OCR/Voting Disk 报错时刻的磁盘 I/O 延迟和 SCSI/驱动错误",
                "analysis_action": "高 I/O 延迟可能导致 OCR/Voting Disk 读写超时",
            },
            {
                "step": "cluster_impact_assessment",
                "files_to_check": ["crsd.log", "cssd.log", "crs_health/*.txt"],
                "what_to_look_for": "OCR/Voting Disk 异常导致的集群重配置、资源 OFFLINE、节点驱逐",
                "analysis_action": "评估 OCR/Voting Disk 异常对集群可用性的实际影响",
            },
        ],
        "cross_references": {
            "related_rules": ["RAC-001", "RAC-002", "RAC-003", "ASM-003"],
            "validation_files": ["ocr_info/*.txt", "voting_disk/*.txt", "os_mount/*.txt", "crsd.log"],
            "correlation": "OCR/Voting Disk 异常 → 集群配置丢失 → 级联资源 OFFLINE",
        },
        "root_cause_indicators": [
            "I/O 错误 → 存储链路问题",
            "空间满 → 磁盘空间管理问题",
            "文件损坏 → 需要从备份恢复 OCR",
            "伴随 ASM-003 → 底层存储 I/O 故障",
        ],
    },

    "RAC-005": {
        "title": "ASM-CRS 通信故障",
        "category": "RAC/Clusterware",
        "primary_entry_types": ["asm_alert", "crs_log"],
        "examination_chain": [
            {
                "step": "asm_alert_scan",
                "files_to_check": ["asm_alert.log"],
                "what_to_look_for": "'failed to online diskgroup resource ora.XXX.dg (unable to communicate with CRSD/OHASD)'",
                "analysis_action": "记录 ASM 无法与 CRSD 通信的时间点和涉及的磁盘组",
            },
            {
                "step": "crs_alert_crosscheck",
                "files_to_check": ["crsd.log", "alert_+ASM<#>.log"],
                "what_to_look_for": "CRSD/OHASD 状态、ASM 实例注册信息、资源恢复记录",
                "analysis_action": "确认 CRS 堆栈本身是否正常运行，ohasd 是否在线",
            },
            {
                "step": "client_reconnect_monitor",
                "files_to_check": ["asm_alert.log"],
                "what_to_look_for": "'giving up on client id' / 'CSS requested to fence client' — 通信断裂后的级联影响",
                "analysis_action": "通信故障 → ASM 放弃客户端 → CSS 隔离客户端，形成完整故障链",
            },
            {
                "step": "css_health_check",
                "files_to_check": ["ocssd.log", "cssd.log"],
                "what_to_look_for": "CSS 心跳状态、节点成员关系变化、集群 reconfig 事件",
                "analysis_action": "检查 CSS 层面是否有节点通信问题，确认是 ASM→CRS 还是 CRS→CSS 断裂",
            },
            {
                "step": "os_network_and_load",
                "files_to_check": ["os_network/netstat*.txt", "os_perf/top*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "网络延时/丢包、系统负载 — 影响 IPC 通信的因素",
                "analysis_action": "高负载/网卡故障是 ASM↔CRS communication 断裂的常见物理原因",
            },
        ],
        "cross_references": {
            "related_rules": ["RAC-001", "RAC-002", "ASM-001", "ASM-002"],
            "validation_files": ["asm_alert.log", "crsd.log", "ocssd.log", "os_network/*.txt"],
            "correlation": "阶段1(online失败) → 阶段2(放弃客户端) → 阶段3(CSS隔离) 是三级递进故障链",
        },
        "root_cause_indicators": [
            "只有阶段1 online 失败 → 瞬时通信故障，可能自愈",
            "阶段1 + 阶段2 + 阶段3 → 完整断裂链，需要干预",
            "伴随 os_network 错误 → 网络问题",
            "高系统负载 → 资源竞争导致 IPC 超时",
        ],
    },

    # ═══════════════════════════════════════════════
    # ASM/存储 (ASM-001 ~ ASM-003)
    # ═══════════════════════════════════════════════

    "ASM-001": {
        "title": "ASM 磁盘 OFFLINE",
        "category": "ASM/存储",
        "primary_entry_types": ["asm_alert", "alert_log"],
        "examination_chain": [
            {
                "step": "asm_alert_offline_scan",
                "files_to_check": ["asm_alert.log", "alert_+ASM<#>.log"],
                "what_to_look_for": "'OFFLINE' 伴随 'disk' 或 'ASM' — 识别哪些磁盘被标记为 OFFLINE",
                "analysis_action": "记录 OFFLINE 磁盘的完整路径和磁盘组名称",
            },
            {
                "step": "disk_path_validation",
                "files_to_check": ["os_mount/df*.txt", "os_mount/mount*.txt"],
                "what_to_look_for": "OFFLINE 磁盘所在存储路径是否仍然可见、多路径状态",
                "analysis_action": "路径丢失 → 存储/光纤/SAN 问题；路径正常 → ASM 层面问题",
            },
            {
                "step": "io_error_check",
                "files_to_check": ["os_kernel/dmesg*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "磁盘 OFFLINE 时刻是否有 I/O 错误、SCSI error、path error",
                "analysis_action": "有 I/O 错误 → 存储链路故障；无错误 → 可能是 ASM 磁盘超时",
            },
            {
                "step": "redundancy_impact",
                "files_to_check": ["asm_alert.log"],
                "what_to_look_for": "磁盘 OFFLINE 后磁盘组是否触发 rebalance、redundancy 是否降级",
                "analysis_action": "Normal/High redundancy 可容忍 N 个磁盘 offline；External redundancy → 数据不可用",
            },
            {
                "step": "cluster_wide_check",
                "files_to_check": ["crsd.log", "alert_<SID>.log"],
                "what_to_look_for": "磁盘 OFFLINE 是否影响了集群节点上的数据库实例",
                "analysis_action": "ASM 磁盘 OFFLINE → 磁盘组不可用 → 数据库 abort",
            },
        ],
        "cross_references": {
            "related_rules": ["ASM-002", "ASM-003", "RAC-004", "RAC-005"],
            "validation_files": ["asm_alert.log", "os_mount/*.txt", "os_kernel/dmesg*.txt"],
            "correlation": "ASM-001(磁盘OFFLINE) → 可能升级为 ASM-002(磁盘组挂载失败) → 数据库不可用",
        },
        "root_cause_indicators": [
            "I/O 错误 + 路径丢失 → 存储/光纤故障",
            "无 I/O 错误 + 路径正常 → ASM 超时配置或 bug",
            "同一存储多路径同时离线 → SAN 交换机问题",
            "单个磁盘离线 → 磁盘本身故障",
        ],
    },

    "ASM-002": {
        "title": "ASM 磁盘组 MOUNT 异常",
        "category": "ASM/存储",
        "primary_entry_types": ["asm_alert", "alert_log"],
        "examination_chain": [
            {
                "step": "asm_alert_mount_scan",
                "files_to_check": ["asm_alert.log", "alert_+ASM<#>.log"],
                "what_to_look_for": "'not mounted'、'cannot mount'、'error mounting' — 哪些磁盘组挂载失败",
                "analysis_action": "记录挂载失败的磁盘组名称、时间和错误信息",
            },
            {
                "step": "disk_access_validation",
                "files_to_check": ["asm_alert.log"],
                "what_to_look_for": "磁盘组挂载失败的具体原因 — 磁盘不可用 / 磁盘头损坏 / 不一致",
                "analysis_action": "查看 fail 前最后一个磁盘状态信息",
            },
            {
                "step": "underlying_storage_check",
                "files_to_check": ["os_mount/df*.txt", "os_kernel/dmesg*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "底层磁盘设备是否可达、多路径状态、SCSI 错误",
                "analysis_action": "存储不可达 → 物理存储问题；存储可达 → 磁盘组元数据问题",
            },
            {
                "step": "database_impact",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "磁盘组挂载失败后，依赖该磁盘组的数据库实例的状态",
                "analysis_action": "数据库访问该磁盘组上的数据文件 → 实例不可用 → 业务中断",
            },
        ],
        "cross_references": {
            "related_rules": ["ASM-001", "ASM-003", "RAC-005"],
            "validation_files": ["asm_alert.log", "os_mount/*.txt", "alert_<SID>.log"],
            "correlation": "ASM-002 通常由 ASM-001(磁盘OFFLINE) 或 ASM-003(存储I/O错误) 级联导致",
        },
        "root_cause_indicators": [
            "所有磁盘组均无法挂载 → ASM 实例或底层存储全面故障",
            "单个磁盘组无法挂载 → 该磁盘组的磁盘故障或元数据损坏",
            "ASM-001 前导 → 磁盘 offline 级联",
        ],
    },

    "ASM-003": {
        "title": "存储 I/O 错误",
        "category": "ASM/存储",
        "primary_entry_types": ["asm_alert", "alert_log", "os_kernel"],
        "examination_chain": [
            {
                "step": "io_error_source_scan",
                "files_to_check": ["asm_alert.log", "os_kernel/dmesg*.txt"],
                "what_to_look_for": "'I/O error'、'disk error'、'path error'、'SCSI error'",
                "analysis_action": "记录报错磁盘设备、错误类型和首次报错时间",
            },
            {
                "step": "multipath_health_check",
                "files_to_check": ["os_mount/mount*.txt", "os_kernel/dmesg*.txt"],
                "what_to_look_for": "多路径配置是否正常，是否有路径 fail 或 degraded",
                "analysis_action": "多路径降级 → 硬件链路问题；多路径正常 → 磁盘/控制器故障",
            },
            {
                "step": "io_latency_at_error",
                "files_to_check": ["os_perf/sar*.txt", "os_perf/iostat*.txt"],
                "what_to_look_for": "I/O 报错时刻的磁盘延迟(await/svctm)和 IOPS",
                "analysis_action": "延迟飙升 + I/O 错误 → 存储控制器或磁盘故障",
            },
            {
                "step": "cascading_impact",
                "files_to_check": ["asm_alert.log", "alert_<SID>.log", "crsd.log"],
                "what_to_look_for": "I/O 错误导致的磁盘 OFFLINE、磁盘组异常、数据库错误、集群事件",
                "analysis_action": "绘制完整影响链：存储I/O错误 → ASM磁盘离线 → 磁盘组失败 → 数据库故障",
            },
        ],
        "cross_references": {
            "related_rules": ["ASM-001", "ASM-002", "RAC-004", "IO-001", "DB-004"],
            "validation_files": ["os_kernel/dmesg*.txt", "os_perf/sar*.txt", "asm_alert.log"],
            "correlation": "存储 I/O 错误通常是根因，会级联触发 ASM、数据库和集群级别的故障",
        },
        "root_cause_indicators": [
            "SCSI 错误 + 路径丢失 → 光纤/HBA/SAN 硬件故障",
            "磁盘 I/O error + 延迟高 → 磁盘故障",
            "无硬件错误 → 可能是驱动或固件 bug",
        ],
    },

    # ═══════════════════════════════════════════════
    # OS 资源 (OS-001 ~ OS-003)
    # ═══════════════════════════════════════════════

    "OS-001": {
        "title": "CPU 使用率过高",
        "category": "OS 资源",
        "primary_entry_types": ["os_perf"],
        "examination_chain": [
            {
                "step": "top_cpu_scan",
                "files_to_check": ["top*.txt", "sar*.txt", "mpstat*.txt"],
                "what_to_look_for": "CPU idle < 20% → 确认哪些 CPU 核心繁忙, user/sys/iowait 占比",
                "analysis_action": "user 高 → 应用/Oracle 进程；sys 高 → 系统调用/中断；iowait 高 → 存储瓶颈",
            },
            {
                "step": "cpu_hog_process_identification",
                "files_to_check": ["top*.txt", "ps*.txt"],
                "what_to_look_for": "CPU 占用率最高的前 10 个进程及其 owner",
                "analysis_action": "oracle 用户进程 → 数据库 SQL/会话；其他进程 → 外部应用",
            },
            {
                "step": "process_detail_analysis",
                "files_to_check": ["ps*.txt"],
                "what_to_look_for": "oracle 进程的 SPID，关联到 v$process / v$session",
                "analysis_action": "定位到具体的数据库会话和正在执行的 SQL",
            },
            {
                "step": "sql_performance_crosscheck",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "CPU 高峰时刻是否有 SQL 相关错误或 ORA- 错误",
                "analysis_action": "CPU 满载 → SQL 执行效率低 → 需要 SQL 优化",
            },
            {
                "step": "cluster_node_cpu_compare",
                "files_to_check": ["top*.txt", "sar*.txt"],
                "what_to_look_for": "RAC 各节点的 CPU 负载是否均衡",
                "analysis_action": "单个节点 CPU 高 → 会话偏斜；所有节点高 → 应用负载问题",
            },
        ],
        "cross_references": {
            "related_rules": ["SQL-001", "SQL-002", "OS-002"],
            "validation_files": ["top*.txt", "ps*.txt", "alert_<SID>.log"],
            "correlation": "CPU 满载 → 应用 SQL 问题或系统进程占资源；需要结合 SQL-001 判断",
        },
        "root_cause_indicators": [
            "oracle 进程占用 CPU > 80% → 数据库 SQL/会话问题",
            "iowait > 30% → 存储瓶颈导致 CPU 等待",
            "非 oracle 进程占用 CPU → 外部应用/监控工具/病毒",
            "所有节点 CPU 高 → 应用层负载",
        ],
    },

    "OS-002": {
        "title": "内存使用过高",
        "category": "OS 资源",
        "primary_entry_types": ["os_memory", "os_perf"],
        "examination_chain": [
            {
                "step": "memory_usage_scan",
                "files_to_check": ["free*.txt", "top*.txt", "sar*.txt", "vmstat*.txt"],
                "what_to_look_for": "物理内存使用率 > 90%、Swap 使用率、available 内存",
                "analysis_action": "计算实际可用内存 = free + buffers/cache；Swap 使用 > 0 表示内存压力",
            },
            {
                "step": "process_memory_check",
                "files_to_check": ["ps*.txt", "top*.txt"],
                "what_to_look_for": "RSS 占用最高的前 10 个进程 — 检查 oracle 进程的 VSZ/RSS",
                "analysis_action": "Oracle SGA/PGA 过大可能挤压 OS 内存 → 触发 OOM",
            },
            {
                "step": "oom_scan",
                "files_to_check": ["os_kernel/dmesg*.txt"],
                "what_to_look_for": "'OOM'、'Out of memory'、'killed process' — OOM Killer 活动记录",
                "analysis_action": "OOM Killer 杀死的如果是 oracle/crs 进程 → 严重影响数据库",
            },
            {
                "step": "swap_analysis",
                "files_to_check": ["free*.txt", "vmstat*.txt", "sar*.txt"],
                "what_to_look_for": "Swap 使用量 > 总内存 10%、si/so 持续非零",
                "analysis_action": "大量 swap 换入换出 → 内存严重不足，系统性能急剧下降",
            },
            {
                "step": "sga_pga_review",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "实例的 SGA/PGA 配置值和当前使用率",
                "analysis_action": "SGA+PGA > 物理内存 * 0.8 → 内存配置过大",
            },
        ],
        "cross_references": {
            "related_rules": ["OS-001", "OS-003", "DB-004"],
            "validation_files": ["free*.txt", "dmesg*.txt", "top*.txt", "alert_<SID>.log"],
            "correlation": "OOM Killer 杀死 oracle 进程 → DB-004 (instance crash)；内存耗尽而 OOM 未触发 → 需检查内核参数 vm.overcommit",
        },
        "root_cause_indicators": [
            "OOM killer 活跃 → 物理内存不足",
            "Swap 使用 > 50% + si/so 活跃 → 严重内存压力",
            "Oracle SGA+PGA > 85% 物理内存 → 内存配置过大",
            "内存泄漏进程（RSS 持续增长）→ bug",
        ],
    },

    "OS-003": {
        "title": "OS Kernel 异常/Panic",
        "category": "OS 资源",
        "primary_entry_types": ["os_kernel", "os_system"],
        "examination_chain": [
            {
                "step": "kernel_log_scan",
                "files_to_check": ["dmesg*.txt", "os_kernel/*.txt"],
                "what_to_look_for": "'panic'、'kernel BUG'、'hung_task'、'kernel Oops' — 内核级错误",
                "analysis_action": "记录首次 panic 时间点和内核错误的具体描述",
            },
            {
                "step": "oom_or_hang_check",
                "files_to_check": ["dmesg*.txt"],
                "what_to_look_for": "'hung_task_timeout_secs'、'blocked for more than 120 seconds' — 进程挂起/阻塞",
                "analysis_action": "IO 阻塞导致内核 hung_task 触发 → 存储/文件系统问题",
            },
            {
                "step": "kernel_oops_detail",
                "files_to_check": ["dmesg*.txt"],
                "what_to_look_for": "kernel Oops 的 Call Trace 和异常码",
                "analysis_action": "通过 Call Trace 定位是哪个内核模块或驱动导致的 panic",
            },
            {
                "step": "crash_dump_check",
                "files_to_check": ["os_hardware/*.txt", "dmesg*.txt"],
                "what_to_look_for": "Kdump/vmcore 是否存在，硬件错误记录",
                "analysis_action": "需要 OS 管理员分析 crash dump 定位根因",
            },
            {
                "step": "database_cluster_impact",
                "files_to_check": ["alert_<SID>.log", "crsd.log", "cssd.log"],
                "what_to_look_for": "Kernel Panic 后数据库实例和集群节点的状态变化",
                "analysis_action": "Kernel Panic → 节点重启 → 实例恢复(resetlogs) → 集群 reconfig → 业务影响评估",
            },
        ],
        "cross_references": {
            "related_rules": ["DB-004", "RAC-002", "OS-001", "OS-002"],
            "validation_files": ["dmesg*.txt", "alert_<SID>.log", "crsd.log"],
            "correlation": "OS-003(Kernel Panic) → 必然导致 DB-004(instance crash) 和可能的 RAC-002(node eviction)",
        },
        "root_cause_indicators": [
            "panic + Call Trace 指向特定驱动 → 驱动 bug",
            "hung_task + IO 阻塞 → 存储/文件系统问题",
            "OOM + killed process → 内存耗尽",
            "硬件错误(MCE) → 物理硬件故障",
        ],
    },

    # ═══════════════════════════════════════════════
    # I/O 性能 (IO-001 ~ IO-002)
    # ═══════════════════════════════════════════════

    "IO-001": {
        "title": "磁盘延迟过高",
        "category": "I/O 性能",
        "primary_entry_types": ["os_perf"],
        "examination_chain": [
            {
                "step": "iostat_latency_scan",
                "files_to_check": ["iostat*.txt", "sar*.txt"],
                "what_to_look_for": "await/svctm > 50ms — 哪些磁盘设备延迟高，r_await 还是 w_await",
                "analysis_action": "读延迟高 → 存储缓存命中率低；写延迟高 → 存储写缓存或日志盘问题",
            },
            {
                "step": "device_load_analysis",
                "files_to_check": ["iostat*.txt", "sar*.txt"],
                "what_to_look_for": "磁盘的 %%util、avgqu-sz、r/s、w/s 队列深度和 IOPS",
                "analysis_action": "%%util > 90%% + 高队列 → 磁盘饱和；低 IOPS + 高延迟 → 磁盘故障",
            },
            {
                "step": "top_disk_consumer",
                "files_to_check": ["top*.txt", "ps*.txt"],
                "what_to_look_for": "I/O 等待最高的进程和 oracle 进程的 D状态",
                "analysis_action": "数据库进程 D 状态 → 数据文件所在磁盘延迟高 → SQL 等待 'db file sequential read'",
            },
            {
                "step": "sql_level_impact",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "磁盘 IO 高峰时刻的 AWR Top Event 和 SQL 执行情况",
                "analysis_action": "定位到是哪些 SQL 导致大量 I/O，判断是否需要 SQL 优化",
            },
            {
                "step": "storage_link_check",
                "files_to_check": ["os_kernel/dmesg*.txt", "os_mount/mount*.txt"],
                "what_to_look_for": "存储链路是否有错误、重置、中断",
                "analysis_action": "存储链路抖动/重置 → HBA 或 SAN 交换机问题",
            },
        ],
        "cross_references": {
            "related_rules": ["IO-002", "OS-001", "SQL-001", "ASM-003"],
            "validation_files": ["iostat*.txt", "sar*.txt", "alert_<SID>.log", "dmesg*.txt"],
            "correlation": "高延迟 I/O → SQL 执行慢(SQL-001) → CPU iowait 高(OS-001) → 存储层故障可能升级",
        },
        "root_cause_indicators": [
            "单盘高延迟 → 磁盘故障",
            "多盘高延迟 → 存储控制器/SAN 问题",
            "存储链路错误 → HBA/光纤通道问题",
            "iowait 高 + 数据库等待 'db file sequential read' → SQL 扫描过多",
        ],
    },

    "IO-002": {
        "title": "I/O 吞吐量异常",
        "category": "I/O 性能",
        "primary_entry_types": ["os_perf"],
        "examination_chain": [
            {
                "step": "throughput_baseline_check",
                "files_to_check": ["iostat*.txt", "sar*.txt"],
                "what_to_look_for": "设备的 rKB/s 和 wKB/s 是否明显超出常规值",
                "analysis_action": "确认突发大量 I/O 的开始时间和涉及的磁盘设备",
            },
            {
                "step": "process_io_correlation",
                "files_to_check": ["top*.txt", "ps*.txt"],
                "what_to_look_for": "产生大量 I/O 的进程 PID 和类型",
                "analysis_action": "定位是 RMAN/expdp/备份 还是 oracle 前台进程",
            },
            {
                "step": "io_type_analysis",
                "files_to_check": ["iostat*.txt"],
                "what_to_look_for": "读/写比例和 I/O 大小分布",
                "analysis_action": "大量随机读 → 全表扫描/SQL 问题；大量顺序写 → 排序/redo log 写入/备份",
            },
        ],
        "cross_references": {
            "related_rules": ["IO-001", "OS-001", "SQL-001", "ADG-003"],
            "validation_files": ["iostat*.txt", "sar*.txt", "top*.txt"],
            "correlation": "突发 I/O 吞吐 + 高延迟 → 存储饱和；突发 I/O + 低延迟 → 正常批量作业",
        },
        "root_cause_indicators": [
            "大量读取 → 全表扫描/expdp/备份",
            "大量写入 → redo log / archive / 排序 / RMAN",
            "I/O 异常 + 高延迟 → 存储瓶颈",
        ],
    },

    # ═══════════════════════════════════════════════
    # 连接/监听 (LSN-001 ~ LSN-003)
    # ═══════════════════════════════════════════════

    "LSN-001": {
        "title": "监听器停止/异常",
        "category": "连接/监听",
        "primary_entry_types": ["listener_log"],
        "examination_chain": [
            {
                "step": "listener_log_scan",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "'error'、'fail'、'stop'、'down'、'refuse'、'closed' 与 listener/TNS 相关",
                "analysis_action": "记录 listener 异常开始时间和错误描述",
            },
            {
                "step": "listener_end_state",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "listener 是否已重启、是否在自动重启循环中",
                "analysis_action": "检查 listener 进程状态和上次启动时间",
            },
            {
                "step": "tns_config_check",
                "files_to_check": ["listener_<HOSTNAME>.log", "os_network/*.txt"],
                "what_to_look_for": "listener.ora 配置错误、网络接口不可达",
                "analysis_action": "配置变更后重启失败 → 配置问题；网络问题 → 主机连接性",
            },
            {
                "step": "database_connection_impact",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "listener 停止期间，客户端连接失败的记录（TNS-125xx/ORA-125xx）",
                "analysis_action": "评估业务影响：listener 不可用期间的新连接全部失败",
            },
        ],
        "cross_references": {
            "related_rules": ["LSN-002", "LSN-003", "RAC-001"],
            "validation_files": ["listener_<HOSTNAME>.log", "alert_<SID>.log", "os_network/*.txt"],
            "correlation": "监听器异常(tns-125xx) → 新连接失败；监听器停止 → RAC 中 VIP 漂移",
        },
        "root_cause_indicators": [
            "TNS-125xx/ORA-125xx → 监听器配置或网络问题",
            "LSNRCTL 停止记录 → 手动操作",
            "OOM 终止 → 内存不足",
            "ORA-27146 → listener 进程已 exit",
        ],
    },

    "LSN-002": {
        "title": "连接风暴/大量连接",
        "category": "连接/监听",
        "primary_entry_types": ["listener_log"],
        "examination_chain": [
            {
                "step": "connection_count_scan",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "统计总连接数 > 100，按时间分组查看连接建立频率",
                "analysis_action": "计算每秒连接数，确认是否有突发连接峰值",
            },
            {
                "step": "client_ip_analysis",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "连接来源 IP 分布 — 是否来自同一来源或服务",
                "analysis_action": "单一 IP 大量连接 → 应用连接池配置问题；多 IP → 业务突发流量",
            },
            {
                "step": "service_name_distribution",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "连接请求的 service name 分布",
                "analysis_action": "确定是哪个 service 遭遇连接风暴",
            },
            {
                "step": "os_resource_during_storm",
                "files_to_check": ["os_process/ps*.txt", "os_memory/free*.txt"],
                "what_to_look_for": "连接风暴期间 OS 的进程数和内存消耗",
                "analysis_action": "大量 oracle 进程 → 内存耗尽(OS-002) → 系统性能下降",
            },
        ],
        "cross_references": {
            "related_rules": ["LSN-001", "LSN-003", "OS-002"],
            "validation_files": ["listener_<HOSTNAME>.log", "os_process/ps*.txt", "os_memory/free*.txt"],
            "correlation": "连接风暴 → 进程数暴增 → 内存压力 → OS-002",
        },
        "root_cause_indicators": [
            "单一 IP + 同一 service → 应用连接池泄漏/配置错误",
            "多 IP + 加权连接数高 → 业务峰值",
            "伴随 OS-002 → 内存耗尽导致系统级故障",
        ],
    },

    "LSN-003": {
        "title": "ORA-12170 TNS 连接超时",
        "category": "连接/监听",
        "primary_entry_types": ["listener_log", "os_network"],
        "examination_chain": [
            {
                "step": "timeout_log_scan",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "'ORA-12170'、'TNS-12170'、'TNS-12535' — 连接超时记录",
                "analysis_action": "统计超时频率和涉及的客户端 IP",
            },
            {
                "step": "network_latency_crosscheck",
                "files_to_check": ["os_network/netstat*.txt", "os_network/ifconfig*.txt"],
                "what_to_look_for": "客户端与服务器之间的网络延迟和丢包率",
                "analysis_action": "高延迟/丢包 → WAN/网络问题；低延迟 → listener 自身负载高",
            },
            {
                "step": "listener_load_check",
                "files_to_check": ["listener_<HOSTNAME>.log", "os_process/ps*.txt"],
                "what_to_look_for": "listener 进程负载、当前连接数、是否达到 max_connections",
                "analysis_action": "连接数达到上限 → LSN-002 连接风暴；进程正常 → 网络问题",
            },
            {
                "step": "sqlnet_timeout_config",
                "files_to_check": ["listener_<HOSTNAME>.log"],
                "what_to_look_for": "sqlnet.ora 中的 CONNECT_TIMEOUT 设置",
                "analysis_action": "超时设置过短 + 正常网络延迟 → 配置问题",
            },
        ],
        "cross_references": {
            "related_rules": ["LSN-001", "LSN-002"],
            "validation_files": ["listener_<HOSTNAME>.log", "os_network/*.txt"],
            "correlation": "TNS 连接超时可能是网络问题、listener 过载或配置超时过短的综合结果",
        },
        "root_cause_indicators": [
            "网络丢包/延迟高 → 网络原因",
            "max_connections 达到 → 连接风暴(LSN-002)",
            "CONNECT_TIMEOUT 过短 → 配置原因",
            "TNS-12535 错误 → 网络或 listener 过载",
        ],
    },

    # ═══════════════════════════════════════════════
    # SQL/性能争用 (SQL-001 ~ SQL-003)
    # ═══════════════════════════════════════════════

    "SQL-001": {
        "title": "Top SQL 耗时过长",
        "category": "SQL/性能争用",
        "primary_entry_types": ["os_perf", "alert_log"],
        "examination_chain": [
            {
                "step": "sql_time_scan",
                "files_to_check": ["alert_<SID>.log", "top*.txt"],
                "what_to_look_for": "SQL 执行时间 > 60s 的记录",
                "analysis_action": "记录慢 SQL 的 elapsed time、SQL ID 和执行时间",
            },
            {
                "step": "wait_event_analysis",
                "files_to_check": ["alert_<SID>.log", "sar*.txt", "iostat*.txt"],
                "what_to_look_for": "慢 SQL 执行期间的等待事件 — 'db file sequential read'、'log file sync'",
                "analysis_action": "I/O 等待 → 检查 IO-001(磁盘延迟)；锁等待 → 检查 SQL-002(锁争用)",
            },
            {
                "step": "execution_plan_check",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "SQL 的执行计划是否变更，统计信息是否过期",
                "analysis_action": "执行计划变差 → 统计信息陈旧或绑定变量窥探",
            },
            {
                "step": "sql_parallel_degree",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "SQL 是否使用并行执行，parallel degree 设置",
                "analysis_action": "并行度过高 → 消耗大量 CPU/IO 资源",
            },
            {
                "step": "os_resource_during_sql",
                "files_to_check": ["os_perf/sar*.txt", "os_perf/top*.txt", "os_memory/free*.txt"],
                "what_to_look_for": "慢 SQL 执行时的 CPU、I/O、内存消耗",
                "analysis_action": "关联 OS-001(CPU高)/IO-001(延迟高)/OS-002(内存高) 判断是否由资源瓶颈导致",
            },
        ],
        "cross_references": {
            "related_rules": ["SQL-002", "SQL-003", "IO-001", "OS-001", "OS-002"],
            "validation_files": ["alert_<SID>.log", "os_perf/sar*.txt", "os_perf/iostat*.txt"],
            "correlation": "SQL 慢可能由磁盘延迟(IO-001)、锁争用(SQL-002)、CPU争用(OS-001)或大排序(SQL-003)导致",
        },
        "root_cause_indicators": [
            "I/O 等待为主 + IO-001 → 存储瓶颈",
            "锁等待为主 + SQL-002 → 并发争用",
            "排序+临时表空间 → SQL-003",
            "CPU 消耗高 + OS-001 → 全表扫描/大量运算",
        ],
    },

    "SQL-002": {
        "title": "等待事件 — Enqueue/锁争用",
        "category": "SQL/性能争用",
        "primary_entry_types": ["alert_log", "os_perf"],
        "examination_chain": [
            {
                "step": "enqueue_log_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "'enq:'、'enqueue'、'TX'、'TM'、'HW' — 锁等待类型",
                "analysis_action": "TX → 事务锁(行锁)；TM → DML 锁(表锁)；HW → 高水位锁",
            },
            {
                "step": "lock_type_classification",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "锁的 mode 和 held/mode 信息",
                "analysis_action": "TX mode 6 → 排他事务锁；TM mode 3 → 行级锁；TM mode 6 → 表级锁",
            },
            {
                "step": "blocking_session_check",
                "files_to_check": ["alert_<SID>.log", "os_process/ps*.txt"],
                "what_to_look_for": "blocking session 信息 — blocker 和 waiter 的 SPID/会话",
                "analysis_action": "定位长时间未提交事务的阻塞源，检查其 SQL 和执行状态",
            },
            {
                "step": "sql_and_object_correlation",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "被锁对象名称和相关的 SQL",
                "analysis_action": "确定是应用设计问题（并发高/事务长）还是 bug",
            },
            {
                "step": "os_cpu_load_crosscheck",
                "files_to_check": ["os_perf/top*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "锁争用发生时的 CPU 负载",
                "analysis_action": "高并发锁争用 → CPU context switch 升高 → 系统吞吐下降",
            },
        ],
        "cross_references": {
            "related_rules": ["SQL-001", "SQL-003", "OS-001"],
            "validation_files": ["alert_<SID>.log", "os_perf/top*.txt"],
            "correlation": "锁等待 → SQL 执行变慢(SQL-001)；DDL 锁 → 临时表空间膨胀(SQL-003)",
        },
        "root_cause_indicators": [
            "TX 锁 + 长时间未提交 → 应用事务管理问题",
            "TM 锁 + DDL → 在线 DDL 阻塞 DML",
            "多会话争用同一行 → 应用并发设计问题",
            "Deadlock 检测 → 应用需要重试机制",
        ],
    },

    "SQL-003": {
        "title": "临时表空间使用异常",
        "category": "SQL/性能争用",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "temp_space_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "'temp'/'temporary'/'sort' 伴随 'used'/'usage'/'alloc'/'full'",
                "analysis_action": "记录临时表空间使用率和时间点",
            },
            {
                "step": "sort_consumer_identification",
                "files_to_check": ["alert_<SID>.log", "os_perf/top*.txt"],
                "what_to_look_for": "哪些 SQL/会话消耗了大量临时空间",
                "analysis_action": "大排序操作 → SQL 优化（索引/排序避免）",
            },
            {
                "step": "disk_space_crosscheck",
                "files_to_check": ["os_mount/df*.txt"],
                "what_to_look_for": "临时表空间所在文件系统的磁盘空间使用率",
                "analysis_action": "磁盘空间满 → 无法扩展临时表空间 → 数据库错误",
            },
            {
                "step": "memory_sort_check",
                "files_to_check": ["os_memory/free*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "PGA 大小和可用内存 — 是否因内存不足将排序写盘",
                "analysis_action": "PGA_AGGREGATE_TARGET 过小 → 大量 sort_area 写盘",
            },
        ],
        "cross_references": {
            "related_rules": ["SQL-001", "OS-002", "DB-005"],
            "validation_files": ["alert_<SID>.log", "os_mount/df*.txt", "os_memory/free*.txt"],
            "correlation": "临时空间满 → 大排序 hash join → 磁盘空间不足 → SQL 失败",
        },
        "root_cause_indicators": [
            "PGA 过小导致排序写盘 → 配置问题",
            "同一条 SQL 多次大排序 → SQL 需要调优",
            "磁盘空间满 → 存储管理问题",
        ],
    },

    # ═══════════════════════════════════════════════
    # ADG/备份 (ADG-001 ~ ADG-003)
    # ═══════════════════════════════════════════════

    "ADG-001": {
        "title": "Data Guard 日志缺口 (Gap)",
        "category": "ADG/备份",
        "primary_entry_types": ["adg_status"],
        "examination_chain": [
            {
                "step": "gap_detection",
                "files_to_check": ["adg_status/*.txt", "alert_<SID>.log"],
                "what_to_look_for": "'gap'、'fetching gap'、'archive gap'、'log gap'",
                "analysis_action": "记录缺口开始时间、缺口序列号和涉及的 thread",
            },
            {
                "step": "network_connectivity_check",
                "files_to_check": ["os_network/netstat*.txt"],
                "what_to_look_for": "主备库之间的网络连通性、延迟、丢包",
                "analysis_action": "网络中断 → 归档日志无法传输 → log gap",
            },
            {
                "step": "archived_log_availability",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "主库的归档日志是否已删除或损坏",
                "analysis_action": "归档被删除 → 备库无法获取 → 永久 gap，需要重建备库",
            },
            {
                "step": "archive_destination_check",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "主库的 LOG_ARCHIVE_DEST 配置和归档目的地状态",
                "analysis_action": "目的地错误/不可写 → 归档失败 → gap",
            },
            {
                "step": "standby_recovery_status",
                "files_to_check": ["adg_status/*.txt", "alert_<SID>.log"],
                "what_to_look_for": "备库的 MRP 进程状态是否正常",
                "analysis_action": "MRP 进程停止 → apply 停止 → gap 不断增大",
            },
        ],
        "cross_references": {
            "related_rules": ["ADG-002", "ADG-003", "LSN-003"],
            "validation_files": ["adg_status/*.txt", "alert_<SID>.log", "os_network/*.txt"],
            "correlation": "网络中断 → ADG-001(gap) → 同步延迟(ADG-002)；归档删除 → 永久 gap 需重建",
        },
        "root_cause_indicators": [
            "网络中断 + gap → 网络恢复后自动恢复",
            "归档被删除 → 永久 gap",
            "MRP 停止 → 备库管理问题",
            "归档目的地异常 → 配置问题",
        ],
    },

    "ADG-002": {
        "title": "DG 同步延迟过高",
        "category": "ADG/备份",
        "primary_entry_types": ["adg_status"],
        "examination_chain": [
            {
                "step": "lag_measurement",
                "files_to_check": ["adg_status/*.txt", "alert_<SID>.log"],
                "what_to_look_for": "'lag'、'delay'、'transport lag' 后面的数值（分钟）",
                "analysis_action": "确认 transport lag 和 apply lag 分别多少",
            },
            {
                "step": "transport_vs_apply_analysis",
                "files_to_check": ["adg_status/*.txt"],
                "what_to_look_for": "transport lag 高 → 网络/传输问题；apply lag 高 → 备库 I/O 能力不足",
                "analysis_action": "transport lag << apply lag → 备库能力瓶颈；transport lag ≈ apply lag → 网络瓶颈",
            },
            {
                "step": "standby_io_perf_check",
                "files_to_check": ["os_perf/iostat*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "备库磁盘 I/O 延迟 — apply 需要大量写 I/O",
                "analysis_action": "备库 I/O 延迟高 → 存储瓶颈导致 apply 慢",
            },
            {
                "step": "network_bandwidth_check",
                "files_to_check": ["os_network/netstat*.txt"],
                "what_to_look_for": "主备间的网络带宽利用率和延迟",
                "analysis_action": "网络带宽不足 → 传输慢 → transport lag",
            },
            {
                "step": "real_apply_config",
                "files_to_check": ["adg_status/*.txt"],
                "what_to_look_for": "是否使用了实时 apply（REAL TIME APPLY）",
                "analysis_action": "未启用实时 apply → apply 需要等归档切换 → 额外延迟",
            },
        ],
        "cross_references": {
            "related_rules": ["ADG-001", "LSN-003", "IO-001", "IO-002"],
            "validation_files": ["adg_status/*.txt", "os_perf/iostat*.txt", "os_network/*.txt"],
            "correlation": "ADG-002(延迟) 未处理 → 可能升级为 ADG-001(日志缺口)",
        },
        "root_cause_indicators": [
            "transport lag 高 + 带宽满 → 网络带宽不足",
            "apply lag 高 + 备库 I/O 延迟 → 备库存储瓶颈",
            "apply lag 高 + I/O 正常 → CPU 资源不足",
            "未启用实时 apply → 配置优化",
        ],
    },

    "ADG-003": {
        "title": "RMAN 备份错误",
        "category": "ADG/备份",
        "primary_entry_types": ["alert_log"],
        "examination_chain": [
            {
                "step": "rman_error_scan",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "'RMAN-<4-5 位>' 或 'ORA-' 伴随 'error'/'fail'/'abort'",
                "analysis_action": "记录 RMAN 错误代码和失败的操作类型（backup/restore/validate）",
            },
            {
                "step": "backup_destination_check",
                "files_to_check": ["os_mount/df*.txt", "os_mount/mount*.txt"],
                "what_to_look_for": "备份目标路径是否可写、空间是否充足、是否正常挂载",
                "analysis_action": "空间满/路径不可写 → 备份失败",
            },
            {
                "step": "io_perf_during_backup",
                "files_to_check": ["os_perf/iostat*.txt", "os_perf/sar*.txt"],
                "what_to_look_for": "备份进行时的磁盘 I/O 负载 — 备份可能加重存储负担",
                "analysis_action": "备份消耗大量 I/O → 影响业务 SQL 性能(SQL-001)",
            },
            {
                "step": "corruption_check",
                "files_to_check": ["alert_<SID>.log"],
                "what_to_look_for": "RMAN 是否检测到数据文件损坏（block corruption）",
                "analysis_action": "块损坏 → 需要从好的备份还原",
            },
        ],
        "cross_references": {
            "related_rules": ["ADG-001", "IO-002", "DB-005"],
            "validation_files": ["alert_<SID>.log", "os_mount/df*.txt", "os_perf/iostat*.txt"],
            "correlation": "RMAN 失败 → 无可用备份 → 数据损坏无法恢复；RMAN I/O 重 → 影响性能",
        },
        "root_cause_indicators": [
            "空间满 → 磁盘管理问题",
            "块损坏 → 存储或硬件问题",
            "RMAN-06059 → 备份片冲突",
            "权限错误 → 文件系统权限问题",
        ],
    },
}

def classify_entry_file(file_path: str) -> tuple[str | None, str | None]:
    """判断文件路径是否属于已知入口类型。

    Returns:
        (category, label): 如 ('alert_log', '🚨 数据库警告日志')
        (None, None): 如果不是入口文件
    """
    lower = file_path.lower()
    for category, label in ENTRY_CLASSIFIER.items():
        # 匹配路径中的关键词
        cat_key = category.lower().replace("_", "")
        if cat_key in lower:
            return category, label

    # 更精确的启发式匹配
    if "alert" in lower and ".log" in lower:
        return "alert_log", "🚨 数据库警告日志"
    if "crsd.log" in lower or "cssd.log" in lower:
        return "crs_log", "🔗 CRS 集群日志"
    if "listener" in lower and ".log" in lower:
        return "listener_log", "📡 监听器日志"
    if "asm" in lower and "alert" in lower:
        return "asm_alert", "💾 ASM 警告日志"
    if "dmesg" in lower:
        return "os_kernel", "🖥️ OS 内核日志"

    return None, None


def build_analysis_chains(
    evidence_data: dict,
    snapshot_manifest: list[dict] | None = None,
) -> list[dict]:
    """从证据数据构建分析链。

    每条分析链以「入口文件」为起点，按以下结构构建：
    1. entry_file: 入口文件路径（触发首次分析的文件）
    2. entry_type: 入口类型（alert_log / crs_log / ...）
    3. entry_label: 入口类型中文标签
    4. evidence_found: 在该入口文件中发现的证据列表
    5. related_snapshots_checked: 关联的根快照文件列表（供交叉验证）
    6. related_evidence: 跨文件关联证据（其他文件中的相关证据）
    7. fault_cluster: 所属故障簇信息
    8. root_cause: 根因结论
    9. severity: 该链的最大严重级别
    10. time_range: 时间范围
    11. analysis_flow: 分析流程描述（自然语言）

    Args:
        evidence_data: evidence.json 中的完整数据结构
        snapshot_manifest: snapshot_manifest.json 列表（可选）

    Returns:
        分析链列表，按严重级别排序
    """
    evidence_list = evidence_data.get("evidence", [])
    if not evidence_list:
        return []

    # 1. 按入口文件分组证据
    entry_groups: dict[str, dict] = {}
    for ev in evidence_list:
        source_file = ev.get("source_file", "")
        if not source_file:
            source_file = ev.get("log_file", "")
        if not source_file:
            continue

        # 从 source_file 提取实际文件名
        # 格式可能是：pa00db12/alert_orcl2.log 或 /pa00db12/alert_orcl2.log
        file_path = source_file.split("/")[-1] if "/" in source_file else source_file

        entry_cat, entry_label = classify_entry_file(file_path)
        if entry_cat is None:
            # 如果不是标准入口文件，尝试检查是否匹配已知快照后缀
            snapshot_entry = classify_snapshot_entry(source_file, evidence_list)
            if snapshot_entry:
                entry_cat, entry_label = snapshot_entry
            else:
                # 不作为入口，归为"其他关联文件"
                continue

        if entry_cat not in entry_groups:
            entry_groups[entry_cat] = {
                "entry_category": entry_cat,
                "entry_label": entry_label,
                "entry_files": set(),
                "evidence": [],
                "file_evidence_map": {},
            }

        group = entry_groups[entry_cat]
        group["entry_files"].add(file_path)
        group["evidence"].append(ev)
        group["file_evidence_map"].setdefault(file_path, []).append(ev)

    if not entry_groups:
        return []

    # 2. 为每个入口构建分析链
    chains = []
    for entry_cat, group in entry_groups.items():
        chain = build_single_chain(
            entry_cat=entry_cat,
            entry_label=group["entry_label"],
            entry_files=sorted(group["entry_files"]),
            evidence=group["evidence"],
            file_evidence_map=group["file_evidence_map"],
            all_evidence=evidence_list,
            snapshot_manifest=snapshot_manifest,
        )
        if chain:
            chains.append(chain)

    # 3. 按严重级别排序
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    chains.sort(key=lambda c: sev_order.get(c["severity"], 99))

    return chains


def classify_snapshot_entry(file_path: str, all_evidence: list[dict]) -> tuple[str, str] | None:
    """尝试将文件路径分类为快照入口类型。"""
    lower = file_path.lower()
    # 检查 evidence 中最常出现的文件名模式
    snapshot_map: dict[str, tuple[str, str]] = {
        "dmesg":    ("os_kernel", "🖥️ OS 内核日志"),
        "ps":       ("os_process", "🖥️ OS 进程快照"),
        "top":      ("os_perf", "🖥️ OS 性能快照"),
        "vmstat":   ("os_perf", "🖥️ OS 性能快照"),
        "iostat":   ("os_perf", "🖥️ OS 性能快照"),
        "sar":      ("os_perf", "🖥️ OS 性能快照"),
        "mpstat":   ("os_perf", "🖥️ OS 性能快照"),
        "free":     ("os_memory", "🖥️ OS 内存快照"),
        "netstat":  ("os_network", "🌐 OS 网络快照"),
        "ifconfig": ("os_network", "🌐 OS 网络快照"),
        "df":       ("os_mount", "💾 OS 存储/挂载"),
        "mount":    ("os_mount", "💾 OS 存储/挂载"),
        "fstab":    ("os_mount", "💾 OS 存储/挂载"),
    }
    for keyword, (cat, label) in snapshot_map.items():
        if keyword in lower:
            return cat, label
    return None


def build_single_chain(
    entry_cat: str,
    entry_label: str,
    entry_files: list[str],
    evidence: list[dict],
    file_evidence_map: dict[str, list[dict]],
    all_evidence: list[dict],
    snapshot_manifest: list[dict] | None = None,
) -> dict | None:
    """构建单条分析链。"""
    if not evidence:
        return None

    # 计算严重级别
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sev_scores = [sev_order.get(ev.get("severity", "info"), 99) for ev in evidence]
    max_sev_score = min(sev_scores) if sev_scores else 99
    severity = "info"
    for k, v in sev_order.items():
        if v == max_sev_score:
            severity = k
            break

    # 时间范围
    timestamps = []
    for ev in evidence:
        ts = ev.get("discovered_at")
        if ts:
            timestamps.append(ts)
    time_range = {
        "start": min(timestamps) if timestamps else None,
        "end": max(timestamps) if timestamps else None,
    }

    # 收集入口文件中发现的规则 ID
    rule_ids_found = sorted(set(ev.get("rule_id", "") for ev in evidence))
    rule_ids_found_str = ", ".join(rule_ids_found) if rule_ids_found else "无规则匹配"

    # 关联的根快照类别
    related_snapshot_cats = ENTRY_RELATED_SNAPSHOT_CATEGORIES.get(entry_cat, [])

    # 在快照清单中找对应文件
    related_snapshots = []
    if snapshot_manifest:
        for snap in snapshot_manifest:
            snap_cat = snap.get("category", "")
            if snap_cat in related_snapshot_cats:
                related_snapshots.append({
                    "file": snap.get("file", ""),
                    "filename": snap.get("filename", ""),
                    "category": snap_cat,
                    "top_category": snap.get("top_category", ""),
                    "timestamp": snap.get("timestamp", ""),
                })

    # 跨文件关联证据（从其他非入口文件）
    entry_cat_rules = ENTRY_RULE_CATEGORIES.get(entry_cat, [])
    related_evidence = []
    for ev in all_evidence:
        if ev.get("source_file", "") in str(entry_files):
            continue
        # 检查规则 ID 是否匹配该入口的规则分类
        rule_id = ev.get("rule_id", "")
        if any(rule_id.startswith(prefix) for prefix in entry_cat_rules):
            related_evidence.append({
                "rule_id": rule_id,
                "severity": ev.get("severity", "info"),
                "description": (ev.get("description", "") or "")[:100],
                "source_file": ev.get("source_file", ""),
                "discovered_at": ev.get("discovered_at"),
            })
        # 时间窗口关联（相同 discovered_at）
        elif ev.get("discovered_at") and time_range["start"]:
            try:
                ev_ts = ev["discovered_at"]
                if time_range["start"] <= ev_ts <= (time_range["end"] or time_range["start"]):
                    related_evidence.append({
                        "rule_id": rule_id,
                        "severity": ev.get("severity", "info"),
                        "description": (ev.get("description", "") or "")[:100],
                        "source_file": ev.get("source_file", ""),
                        "discovered_at": ev.get("discovered_at"),
                    })
            except Exception:
                pass

    # 去重
    seen = set()
    unique_related = []
    for ev in related_evidence:
        key = (ev["rule_id"], ev["source_file"], ev["discovered_at"])
        if key not in seen:
            seen.add(key)
            unique_related.append(ev)
    related_evidence = unique_related[:20]  # 最多展示 20 条

    # 汇总涉及的规则（去重）
    rules_involved = sorted(set(
        (ev.get("rule_id", ""), ev.get("title", ""), ev.get("severity", "info"))
        for ev in evidence
        if ev.get("rule_id")
    ))

    # ── 构建事件时间线（chronological timeline） ──
    chain_timeline = build_chain_timeline(evidence, all_evidence, time_range)

    # ── 推演根因（root cause deduction） ──
    root_cause = deduce_root_cause(
        entry_cat=entry_cat,
        evidence=evidence,
        rules_involved=rules_involved,
        severity=severity,
        related_evidence=related_evidence,
        chain_timeline=chain_timeline,
    )

    # 生成结构化的文件审计步骤链
    analysis_steps = build_analysis_steps(
        entry_cat=entry_cat,
        entry_files=entry_files,
        entry_label=entry_label,
        evidence=evidence,
        rules_involved=rules_involved,
        severity=severity,
        related_snapshot_cats=related_snapshot_cats,
        related_snapshots=related_snapshots,
        related_evidence=related_evidence,
        root_cause=root_cause,
        chain_timeline=chain_timeline,
    )
    # 保留原有的 analysis_flow 字符串（兼容旧代码）
    analysis_flow = " → ".join(f"[{s['action_label']}] {s['detail'][:80]}" for s in analysis_steps)

    # 文件详情（含完整日志片段）
    file_details = []
    for fpath in entry_files:
        ev_in_file = file_evidence_map.get(fpath, [])
        file_details.append({
            "file": fpath,
            "evidence_count": len(ev_in_file),
            "evidence_items": [
                {
                    "rule_id": ev.get("rule_id", ""),
                    "title": ev.get("title", ""),
                    "severity": ev.get("severity", "info"),
                    "description": (ev.get("description", "") or "")[:200],
                    "discovered_at": ev.get("discovered_at"),
                    "log_snippet": (ev.get("log_snippet", "") or "")[:500],
                    "log_lines": (ev.get("log_snippet", "") or "").split("\n")[:10],
                    "line_number": ev.get("line_number", 0),
                }
                for ev in ev_in_file
            ],
        })

    chain = {
        "entry_category": entry_cat,
        "entry_label": entry_label,
        "entry_files": entry_files,
        "severity": severity,
        "time_range": time_range,
        "evidence_count": len(evidence),
        "rules_found": rule_ids_found,
        "rules_involved": [
            {"rule_id": r[0], "title": r[1], "severity": r[2]} for r in rules_involved
        ],
        "file_details": file_details,
        "related_snapshot_categories": related_snapshot_cats,
        "related_snapshots": related_snapshots,
        "related_evidence": related_evidence,
        "analysis_flow": analysis_flow,
        "analysis_steps": analysis_steps,
        "chain_timeline": chain_timeline,
        "root_cause": root_cause,
    }

    return chain


def generate_analysis_flow(
    entry_cat: str,
    entry_files: list[str],
    entry_label: str,
    rules_involved: list[tuple],
    severity: str,
    rule_count: int,
    evidence_count: int,
    related_snapshot_count: int,
    related_evidence_count: int,
    related_snapshot_cats: list[str],
    root_cause: dict | None = None,
) -> str:
    """生成自然语言分析流程描述。"""
    files_str = "、".join(entry_files[:3])
    if len(entry_files) > 3:
        files_str += f" 等 {len(entry_files)} 个文件"

    rules_str = "、".join(f"{r[0]}({r[1]})" for r in rules_involved[:5])
    if len(rules_involved) > 5:
        rules_str += f" 等 {len(rules_involved)} 条规则"

    snapshot_cats_labels = []
    cat_label_map = {
        "os_perf": "OS 性能快照", "os_kernel": "内核日志", "os_process": "进程快照",
        "os_memory": "内存快照", "os_network": "网络快照", "os_system": "系统状态",
        "os_mount": "存储/挂载", "os_hardware": "硬件信息", "asm_config": "ASM 配置",
        "ocr_info": "OCR 信息", "voting_disk": "Voting Disk", "crs_health": "CRS 健康检查",
        "crs_resource": "CRS 资源", "cluster_state": "集群状态", "cluster_config": "集群配置",
        "adg_status": "ADG 状态",
    }
    for cat in related_snapshot_cats[:4]:
        snapshot_cats_labels.append(cat_label_map.get(cat, cat))
    snapshot_str = "、".join(snapshot_cats_labels)
    if len(related_snapshot_cats) > 4:
        snapshot_str += f" 等 {len(related_snapshot_cats)} 个类别"

    flow_parts = [
        f"[入口] {entry_label} → 分析文件: {files_str}",
    ]
    if rules_involved:
        flow_parts.append(f"[发现] 命中 {rule_count} 条规则: {rules_str}")
    if related_snapshot_cats:
        flow_parts.append(f"[交叉验证] 建议查看 {snapshot_str} ({related_snapshot_count} 个关联快照)")
    if related_evidence_count > 0:
        flow_parts.append(f"[关联分析] 在 {related_evidence_count} 条跨文件证据中验证根因")
    if root_cause:
        flow_parts.append(f"[根因推断] {root_cause.get('summary', '')}")
    flow_parts.append(f"[结论] 严重级别: {severity}，共 {evidence_count} 条证据")

    return " → ".join(flow_parts)


def build_analysis_steps(
    entry_cat: str,
    entry_files: list[str],
    entry_label: str,
    evidence: list[dict],
    rules_involved: list[tuple],
    severity: str,
    related_snapshot_cats: list[str],
    related_snapshots: list[dict],
    related_evidence: list[dict],
    root_cause: dict | None = None,
    chain_timeline: list[dict] | None = None,
) -> list[dict]:
    """生成结构化的文件审计步骤链。

    每一步展示：操作类型 → 查看的文件 → 发现的内容 → 分析动作。
    形成清晰的"先查看了哪个文件，发现了什么，然后做了什么"链条。
    """
    steps = []
    cat_label_map = {
        "os_perf": "OS 性能快照", "os_kernel": "内核日志", "os_process": "进程快照",
        "os_memory": "内存快照", "os_network": "网络快照", "os_system": "系统状态",
        "os_mount": "存储/挂载", "os_hardware": "硬件信息", "asm_config": "ASM 配置",
        "ocr_info": "OCR 信息", "voting_disk": "Voting Disk", "crs_health": "CRS 健康检查",
        "crs_resource": "CRS 资源", "cluster_state": "集群状态", "cluster_config": "集群配置",
        "adg_status": "ADG 状态",
    }

    # 找到所有入口证据的最早时间，用于 step1 time_ref
    entry_earliest = None
    for ev in evidence:
        ts = ev.get("discovered_at")
        if ts and (entry_earliest is None or ts < entry_earliest):
            entry_earliest = ts

    # Step 1: 入口文件分析
    files_str = "、".join(entry_files[:3])
    if len(entry_files) > 3:
        files_str += f" 等 {len(entry_files)} 个文件"
    steps.append({
        "step": 1,
        "action": "entry_scan",
        "action_icon": "🔍",
        "action_label": "入口扫描",
        "target_files": entry_files[:5],
        "detail": f"从 {entry_label} 入口开始分析，扫描文件: {files_str}",
        "time_ref": entry_earliest,
    })

    # Step 2: 规则命中分析 (对应每个规则发现)
    if rules_involved:
        for i, (rid, rtitle, rsev) in enumerate(rules_involved[:5]):
            # 找到这条规则对应的证据文件
            matching_ev = [e for e in evidence if e.get("rule_id") == rid]
            source_files = sorted(set(e.get("source_file", "") for e in matching_ev))
            steps.append({
                "step": 2 + i,
                "action": "rule_hit",
                "action_icon": "🎯",
                "action_label": "规则命中",
                "target_files": source_files[:3],
                "rule_id": rid,
                "rule_title": rtitle,
                "severity": rsev,
                "detail": f"在 {'、'.join(source_files[:2])} 中命中规则 {rid}: {rtitle} ({rsev})",
                "ev_count": len(matching_ev),
                "time_ref": matching_ev[0].get("discovered_at") if matching_ev else None,
            })
    step_offset = 2 + len(rules_involved[:5])

    # Step 3: 按规则方法论进行交叉验证
    # 查找每条命中规则的专有分析步骤
    methodology_items = build_methodology_evidence_steps(evidence, rules_involved)
    if methodology_items:
        for mi in methodology_items:
            steps.append({
                "step": step_offset,
                "action": "cross_validate",
                "action_icon": "🔗",
                "action_label": f"{mi['rule_id']} 验证",
                "target_files": mi['target_files'][:5],
                "rule_id": mi['rule_id'],
                "step_label": mi['step_label'],
                "what_to_look_for": mi['what_to_look_for'],
                "analysis_action": mi['analysis_action'],
                "detail": mi['detail'],
                "file_count": mi['file_count'],
                "time_ref": mi.get('time_ref'),
            })
            step_offset += 1
    elif related_snapshot_cats:
        # 降级：如果命中规则无方法论，使用通用关联快照
        cat_labels = [cat_label_map.get(c, c) for c in related_snapshot_cats[:5]]
        snap_files = sorted(set(s.get("file", "") for s in related_snapshots[:5]))
        steps.append({
            "step": step_offset,
            "action": "cross_validate",
            "action_icon": "🔗",
            "action_label": "交叉验证",
            "target_files": snap_files[:5],
            "snapshot_categories": related_snapshot_cats[:5],
            "snapshot_count": len(related_snapshots),
            "detail": f"参考通用的关联快照类别：{'、'.join(cat_labels)} 等 {len(related_snapshot_cats)} 个类别（共 {len(related_snapshots)} 个关联快照）",
            "time_ref": None,
        })
        step_offset += 1

    # Step 4: 跨文件关联分析（含方法论关联规则验证）
    if related_evidence:
        cross_files = sorted(set(e.get("source_file", "") for e in related_evidence[:5]))
        cross_rules = sorted(set(e.get("rule_id", "") for e in related_evidence[:5]))
        # 查找方法论中的 cross_references 信息
        cross_ref_detail = ""
        for rid, _, _ in rules_involved:
            methodology = RULE_ANALYSIS_METHODOLOGY.get(rid)
            if methodology and methodology.get("cross_references"):
                cr = methodology["cross_references"]
                cross_ref_detail = cr.get("correlation", "")
                break
        detail = f"在 {len(related_evidence)} 条跨文件证据中关联分析（来源: {'、'.join(cross_files[:3])}，规则: {'、'.join(cross_rules[:3])}）"
        if cross_ref_detail:
            detail += f" | {cross_ref_detail}"
        steps.append({
            "step": step_offset,
            "action": "correlation",
            "action_icon": "🔄",
            "action_label": "关联分析",
            "target_files": cross_files[:5],
            "evidence_count": len(related_evidence),
            "known_rules": list(set(cross_rules) & set(RULE_ANALYSIS_METHODOLOGY.keys())),
            "correlation_guide": cross_ref_detail,
            "detail": detail,
            "time_ref": related_evidence[0].get("discovered_at") if related_evidence else None,
        })
        step_offset += 1

    # Step 5: 根因推断
    if root_cause:
        steps.append({
            "step": step_offset,
            "action": "root_cause",
            "action_icon": "🧠",
            "action_label": "根因推断",
            "target_files": [],
            "detail": f"{root_cause.get('summary', '')}",
            "rc_type": root_cause.get("type", ""),
            "rc_confidence": root_cause.get("confidence", "low"),
            "time_ref": chain_timeline[0].get("time") if chain_timeline and len(chain_timeline) > 0 else None,
        })
        step_offset += 1

    # Step 6: 结论
    last_ts = chain_timeline[-1].get("time") if chain_timeline and len(chain_timeline) > 0 else None
    steps.append({
        "step": step_offset,
        "action": "conclusion",
        "action_icon": "📊",
        "action_label": "分析结论",
        "target_files": [],
        "severity": severity,
        "detail": f"问题严重级别: {severity}，共发现 {len(evidence)} 条证据，涉及 {len(rules_involved)} 条规则",
        "time_ref": last_ts,
    })

    return steps



def build_methodology_evidence_steps(
    evidence: list[dict],
    rules_involved: list[tuple],
) -> list[dict]:
    """根据 RULE_ANALYSIS_METHODOLOGY 生成具体的交叉验证步骤。

    对于每条命中的规则，查找其专有的 examination_chain 步骤，
    生成针对性的文件检查步骤，替代通用的"建议查看 OS 性能快照..."描述。
    """
    items = []
    seen_rules = set()

    for rid, rtitle, rsev in rules_involved:
        if rid in seen_rules:
            continue
        seen_rules.add(rid)

        methodology = RULE_ANALYSIS_METHODOLOGY.get(rid)
        if not methodology:
            continue

        exam_chain = methodology.get("examination_chain", [])
        for step_def in exam_chain[:3]:  # 每个规则最多展示 3 个具体步骤
            files_str = "、".join(step_def["files_to_check"][:3])
            if len(step_def["files_to_check"]) > 3:
                files_str += f" 等 {len(step_def['files_to_check'])} 类文件"

            # 找到这条规则在 evidence 中的时间参考
            matching_ev = [e for e in evidence if e.get("rule_id") == rid]
            time_ref = matching_ev[0].get("discovered_at") if matching_ev else None

            items.append({
                "rule_id": rid,
                "rule_title": methodology.get("title", rtitle),
                "step_id": step_def["step"],
                "step_label": step_def.get("step", "分析"),
                "files_to_check": step_def["files_to_check"][:5],
                "target_files": step_def["files_to_check"][:5],
                "what_to_look_for": step_def.get("what_to_look_for", ""),
                "analysis_action": step_def.get("analysis_action", ""),
                "file_count": len(step_def["files_to_check"]),
                "detail": f"[{rid}] {methodology.get('title', rtitle)} → 检查 {files_str}，关注: {step_def.get('what_to_look_for', '')[:60]}",
                "time_ref": time_ref,
            })

        # 添加 root_cause_indicators 作为验证参考
        indicators = methodology.get("root_cause_indicators", [])
        if indicators:
            items.append({
                "rule_id": rid,
                "rule_title": methodology.get("title", rtitle),
                "step_id": "rc_verify",
                "step_label": "根因验证",
                "files_to_check": methodology.get("cross_references", {}).get("validation_files", []),
                "target_files": methodology.get("cross_references", {}).get("validation_files", [])[:5],
                "what_to_look_for": "验证根因指标: " + "; ".join(indicators[:3]),
                "analysis_action": "根据根因指标综合判断",
                "file_count": len(methodology.get("cross_references", {}).get("validation_files", [])),
                "detail": f"[{rid}] 根因判定指标: {' | '.join(indicators[:3])}",
                "time_ref": None,
            })

    return items



def build_chain_timeline(
    evidence: list[dict],
    all_evidence: list[dict],
    time_range: dict,
) -> list[dict]:
    """构建链内事件时间线 — 按 discovered_at 排序展示关键事件序列。

    将所有相关证据（入口文件证据 + 时间窗口内跨文件证据）按时间排列，
    形成完整的事件时间线，帮助分析故障发生的前后顺序。
    """
    events = []

    # 收集入口文件证据
    for ev in evidence:
        ts = ev.get("discovered_at")
        if ts:
            events.append({
                "time": ts,
                "type": "entry",
                "rule_id": ev.get("rule_id", ""),
                "severity": ev.get("severity", "info"),
                "description": (ev.get("description", "") or "")[:150],
                "source_file": ev.get("source_file", ""),
                "log_snippet": (ev.get("log_snippet", "") or "")[:200],
            })

    # 收集时间窗口内的跨文件证据
    start_ts = time_range.get("start")
    end_ts = time_range.get("end")
    if start_ts:
        for ev in all_evidence:
            ts = ev.get("discovered_at")
            if not ts:
                continue
            try:
                if start_ts <= ts <= (end_ts or start_ts):
                    rule_id = ev.get("rule_id", "")
                    src = ev.get("source_file", "")
                    key = (rule_id, src, ts)
                    # 避免重复添加已在入口证据中的条目
                    if any(
                        e["rule_id"] == rule_id
                        and e["source_file"] == src
                        and e["time"] == ts
                        for e in events
                    ):
                        continue
                    events.append({
                        "time": ts,
                        "type": "related",
                        "rule_id": rule_id,
                        "severity": ev.get("severity", "info"),
                        "description": (ev.get("description", "") or "")[:150],
                        "source_file": src,
                        "log_snippet": (ev.get("log_snippet", "") or "")[:200],
                    })
            except Exception:
                pass

    # 按时间排序
    events.sort(key=lambda e: e["time"])

    # 生成时间线步骤描述
    for i, evt in enumerate(events):
        evt["step"] = i + 1

    return events


def deduce_root_cause(
    entry_cat: str,
    evidence: list[dict],
    rules_involved: list[tuple],
    severity: str,
    related_evidence: list[dict],
    chain_timeline: list[dict],
) -> dict:
    """基于入口类型、规则命中、时间线序列和关联证据，推演最可能的根因。

    使用基于规则的启发式方法推断根因，而非简单的描述拼接。
    根据证据链的时间序列和相关规则分类推导因果关系。
    """
    # 收集所有规则 ID
    all_rule_ids = [r[0] for r in rules_involved]
    all_rule_descriptions = [r[1] for r in rules_involved if r[1]]

    # 检查时间线中是否存在 "早期→晚期" 模式（先兆事件 → 主故障）
    timeline_sequence = ""
    if len(chain_timeline) >= 2:
        timeline_sequence = " → ".join(
            f"{e['rule_id']}({e['description'][:30]})" for e in chain_timeline[:5]
        )

    # 根据入口类型和命中规则推断根因
    root_cause_type = "unknown"
    root_cause_summary = "无法自动推断根因，需要人工分析。"
    root_cause_detail = ""
    confidence: str = "low"

    # 数据库入口根因推断
    if entry_cat == "alert_log":
        if any("DB-" in r for r in all_rule_ids):
            # DB-004 实例启动一般是正常事件，但也可能是 crash-recovery 的后续
            if any("DB-004" in r for r in all_rule_ids) and any("DB-003" in r or "DB-005" in r or "ORA-" in r for r in all_rule_ids):
                root_cause_type = "instance_crash"
                root_cause_summary = "数据库实例异常关闭后自动重启（crash → recovery → startup）"
                root_cause_detail = "检测到实例启动（DB-004）伴随 ORA- 或 DB-003/DB-005 错误，属于 crash-recovery 模式"
                confidence = "high"
            elif any("DB-001" in r for r in all_rule_ids):
                root_cause_type = "ora_error"
                root_cause_summary = "数据库内部错误（ORA-00600 / ORA-07445）"
                confidence = "high"
            elif any("DB-003" in r for r in all_rule_ids):
                root_cause_type = "instance_abort"
                root_cause_summary = "实例异常终止（ORA-07445 / PMON 终止）"
                confidence = "high"
            elif any("DB-004" in r for r in all_rule_ids):
                # 单独的实例启动，无关联错误 — 可能是正常操作或恢复后重启
                if related_evidence:
                    root_cause_type = "post_recovery_startup"
                    root_cause_summary = "故障恢复后实例自动重启"
                    confidence = "medium"
                else:
                    root_cause_type = "normal_startup"
                    root_cause_summary = "数据库实例正常启动过程（可能是计划内操作）"
                    confidence = "low"
            else:
                root_cause_summary = f"数据库警告日志中检测到相关规则：{', '.join(all_rule_ids[:3])}"
                confidence = "medium"

    # CRS / RAC 根因推断
    elif entry_cat == "crs_log":
        if any("RAC-001" in r for r in all_rule_ids):
            root_cause_type = "crs_offline"
            root_cause_summary = "CRS 集群服务异常离线"
            confidence = "high"
        elif any("RAC-002" in r for r in all_rule_ids):
            root_cause_type = "node_eviction"
            root_cause_summary = "节点被集群驱逐（Node Eviction）"
            confidence = "high"
        elif any("RAC-003" in r for r in all_rule_ids):
            root_cause_type = "split_brain"
            root_cause_summary = "集群脑裂（Split Brain）风险"
            confidence = "high"
        else:
            root_cause_summary = f"集群日志中检测到异常：{', '.join(all_rule_ids[:3])}"
            confidence = "medium"

    # ASM 根因推断
    elif entry_cat == "asm_alert":
        if any("ASM-001" in r for r in all_rule_ids):
            root_cause_type = "asm_disk_offline"
            root_cause_summary = "ASM 磁盘 OFFLINE，磁盘组冗余降低"
            confidence = "high"
        elif any("ASM-002" in r for r in all_rule_ids):
            root_cause_type = "asm_dg_fail"
            root_cause_summary = "ASM 磁盘组挂载失败"
            confidence = "high"
        else:
            root_cause_type = "asm_anomaly"
            root_cause_summary = f"ASM 警告日志中发现异常：{', '.join(all_rule_ids[:3])}"
            confidence = "medium"

    # OS 性能/内核根因推断
    elif entry_cat in ("os_perf", "os_kernel"):
        if any("OS-001" in r for r in all_rule_ids):
            root_cause_type = "cpu_overload"
            root_cause_summary = "CPU 过载导致系统性能瓶颈"
            confidence = "high"
        elif any("OS-002" in r for r in all_rule_ids):
            root_cause_type = "memory_pressure"
            root_cause_summary = "内存/Swap 使用率过高导致性能下降"
            confidence = "high"
        elif any("OS-003" in r for r in all_rule_ids):
            root_cause_type = "kernel_panic"
            root_cause_summary = "OS 内核级故障（Kernel Panic / OOM）"
            confidence = "high"
        else:
            root_cause_type = "os_anomaly"
            root_cause_summary = f"OS 层面发现性能或异常事件：{', '.join(all_rule_ids[:3])}"
            confidence = "medium"

    # ADG 根因推断
    elif entry_cat == "adg_status":
        if any("ADG-001" in r for r in all_rule_ids):
            root_cause_type = "dg_gap"
            root_cause_summary = "Data Guard 日志缺口（Gap）导致同步中断"
            confidence = "high"
        elif any("ADG-002" in r for r in all_rule_ids):
            root_cause_type = "dg_lag"
            root_cause_summary = "ADG 同步延迟过高"
            confidence = "high"
        else:
            root_cause_summary = f"ADG 状态异常：{', '.join(all_rule_ids[:3])}"
            confidence = "medium"

    # 监听器根因推断
    elif entry_cat == "listener_log":
        if any("LSN-001" in r for r in all_rule_ids):
            root_cause_type = "listener_down"
            root_cause_summary = "监听器服务停止，客户端连接中断"
            confidence = "high"
        elif any("LSN-002" in r for r in all_rule_ids):
            root_cause_type = "connect_storm"
            root_cause_summary = "监听器连接风暴，超过最大连接数"
            confidence = "high"
        else:
            root_cause_summary = f"监听器日志中发现连接异常：{', '.join(all_rule_ids[:3])}"
            confidence = "medium"

    # 通用推断 — 基于时间线的事件序列
    if root_cause_type == "unknown" and len(chain_timeline) >= 3:
        first_event = chain_timeline[0]
        last_event = chain_timeline[-1]
        if first_event.get("severity") in ("info", "low") and last_event.get("severity") in ("critical", "high"):
            root_cause_type = "cascading_failure"
            root_cause_summary = "级联故障：初始轻微异常逐步演变为严重故障"
            root_cause_detail = (
                f"首事件: {first_event['rule_id']}({first_event['description'][:40]}) "
                f"→ 末事件: {last_event['rule_id']}({last_event['description'][:40]})"
            )
            confidence = "medium"

    # 关联证据推导 — 如果跨文件证据中有 OS 资源类，可能是资源耗尽导致
    rel_os_evidence = [e for e in related_evidence if e.get("rule_id", "").startswith("OS-")]
    rel_db_evidence = [e for e in related_evidence if e.get("rule_id", "").startswith("DB-")]
    if root_cause_type == "unknown" and rel_os_evidence and rel_db_evidence:
        root_cause_type = "resource_starvation"
        root_cause_summary = "OS 资源耗尽导致数据库异常"
        root_cause_detail = f"发现 {len(rel_os_evidence)} 条 OS 级别证据和 {len(rel_db_evidence)} 条数据库级别证据，资源 → 数据库的传导链路"
        confidence = "high"

    return {
        "type": root_cause_type,
        "summary": root_cause_summary,
        "detail": root_cause_detail,
        "confidence": confidence,
        "key_rules": all_rule_ids[:5],
        "timeline_sequence": timeline_sequence,
        "severity": severity,
    }
