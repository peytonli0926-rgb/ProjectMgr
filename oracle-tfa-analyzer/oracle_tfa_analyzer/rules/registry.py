"""规则注册中心。"""

from .base import BaseRule
from .db_stability import ORA600Rule, ORA7445Rule, ORA6002Rule, InstanceCrashRule, GenericDBErrorRule
from .rac_cluster import CrsOfflineRule, FencingRebootRule, BrainSplitRule, OCRCorruptRule, AsmCrsCommFailureRule
from .asm_storage import AsmDiskOfflineRule, AsmDiskgroupMountRule, StorageIOErrorRule
from .os_resource import HighCpuUsageRule, HighMemRule, KernelPanicRule
from .io_perf import HighDiskLatencyRule, IOThroughputRule
from .connection_listener import ListenerDownRule, ConnectionStormRule, TNS12170Rule
from .sql_contention import TopSqlByElapsedRule, WaitEventEnqueueRule, TempUsageRule
from .adg_backup import DataGapRule, DGTransportDelayRule, RmanErrorRule


def get_all_rules() -> list[BaseRule]:
    return [
        ORA600Rule(), ORA7445Rule(), ORA6002Rule(), InstanceCrashRule(), GenericDBErrorRule(),
        CrsOfflineRule(), FencingRebootRule(), BrainSplitRule(), OCRCorruptRule(), AsmCrsCommFailureRule(),
        AsmDiskOfflineRule(), AsmDiskgroupMountRule(), StorageIOErrorRule(),
        HighCpuUsageRule(), HighMemRule(), KernelPanicRule(),
        HighDiskLatencyRule(), IOThroughputRule(),
        ListenerDownRule(), ConnectionStormRule(), TNS12170Rule(),
        TopSqlByElapsedRule(), WaitEventEnqueueRule(), TempUsageRule(),
        DataGapRule(), DGTransportDelayRule(), RmanErrorRule(),
    ]
