"""ASM/存储 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class AsmDiskOfflineRule(BaseRule):
    rule_id = "ASM-001"
    title = "ASM 磁盘 OFFLINE"
    category = "ASM/存储"
    severity = "high"
    description = "ASM 磁盘组中的磁盘处于 OFFLINE 状态"
    recommendation = "检查磁盘路径和存储链路，尝试 online disk"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"OFFLINE", line, re.IGNORECASE) and re.search(r"(disk|ASM)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category, rule_id=self.rule_id, title="ASM 磁盘 OFFLINE",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="ASM 磁盘离线可能导致磁盘组 redundancy 降级。"
                ))
        return result


class AsmDiskgroupMountRule(BaseRule):
    rule_id = "ASM-002"
    title = "ASM 磁盘组 MOUNT 异常"
    category = "ASM/存储"
    severity = "critical"
    description = "ASM 磁盘组无法正常挂载"
    recommendation = "检查磁盘路径、存储连通性和磁盘头状态"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"diskgroup| disk ", line, re.IGNORECASE) and \
               re.search(r"(?:not mounted|cannot mount|error mounting|fail)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category, rule_id=self.rule_id, title="ASM 磁盘组挂载失败",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="磁盘组无法挂载将导致数据库无法访问数据文件。"
                ))
        return result


class StorageIOErrorRule(BaseRule):
    rule_id = "ASM-003"
    title = "存储 I/O 错误"
    category = "ASM/存储"
    severity = "high"
    description = "存储系统 I/O 错误"
    recommendation = "检查存储链路、HBA、SAN 交换机状态"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"I/O error|IO error|disk error|path error|SCSI error", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category, rule_id=self.rule_id, title="存储 I/O 错误",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="存储 I/O 错误可能导致性能下降或数据损坏。"
                ))
        return result
