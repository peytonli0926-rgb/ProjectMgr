"""规则注册中心。收集所有规则并分类注册。"""

from .base import BaseRule
from .db_stability import ORA600Rule, ORA7445Rule, ORA6002Rule, InstanceCrashRule, GenericDBErrorRule
from .rac_cluster import CrsOfflineRule, FencingRebootRule, BrainSplitRule, OCRCorruptRule
from .asm_storage import AsmDiskOfflineRule, AsmDiskgroupMountRule, StorageIOErrorRule
from .os_resource import HighCpuUsageRule, HighMemRule, KernelPanicRule
from .io_perf import HighDiskLatencyRule, IOThroughputRule
from .connection_listener import ListenerDownRule, ConnectionStormRule, TNS12170Rule
from .sql_contention import TopSqlByElapsedRule, WaitEventEnqueueRule, TempUsageRule
from .adg_backup import DataGapRule, DGTransportDelayRule, RmanErrorRule


def get_all_rules() -> list[BaseRule]:
    """返回所有注册的规则实例列表。"""
    return [
        # 数据库错误与稳定性
        ORA600Rule(),
        ORA7445Rule(),
        ORA6002Rule(),
        InstanceCrashRule(),
        GenericDBErrorRule(),
        # RAC/Clusterware
        CrsOfflineRule(),
        FencingRebootRule(),
        BrainSplitRule(),
        OCRCorruptRule(),
        # ASM/存储
        AsmDiskOfflineRule(),
        AsmDiskgroupMountRule(),
        StorageIOErrorRule(),
        # OS 资源
        HighCpuUsageRule(),
        HighMemRule(),
        KernelPanicRule(),
        # I/O 性能
        HighDiskLatencyRule(),
        IOThroughputRule(),
        # 连接/监听
        ListenerDownRule(),
        ConnectionStormRule(),
        TNS12170Rule(),
        # SQL/性能争用
        TopSqlByElapsedRule(),
        WaitEventEnqueueRule(),
        TempUsageRule(),
        # ADG/备份
        DataGapRule(),
        DGTransportDelayRule(),
        RmanErrorRule(),
    ]


def get_rules_by_category() -> dict[str, list[BaseRule]]:
    """按分析方向分类规则。"""
    rules = get_all_rules()
    by_cat: dict[str, list[BaseRule]] = {}
    for rule in rules:
        by_cat.setdefault(rule.category, []).append(rule)
    return by_cat
