"""OS 资源 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class HighCpuUsageRule(BaseRule):
    rule_id = "OS-001"
    title = "CPU 使用率过高"
    category = "OS 资源"
    severity = "medium"
    description = "CPU 使用率持续过高"
    recommendation = "检查 top 输出中 CPU 占用高的进程"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(r"(\d+[.,]?\d*)\s*%?\s*(?:idle|id)", line, re.IGNORECASE)
            if m:
                try:
                    idle = float(m.group(1).replace(",", "."))
                    if idle < 20:
                        result.matched = True
                        result.evidence.append(Evidence(
                            category=self.category, rule_id=self.rule_id,
                            title=f"CPU 空闲仅 {idle}%", severity=self.severity,
                            log_file=file_path, log_snippet=line.strip(), line_number=i,
                            recommendation=self.recommendation, detail=f"CPU 空闲率 {idle}%，低于 20%。"
                        ))
                except ValueError:
                    pass
        return result


class HighMemRule(BaseRule):
    rule_id = "OS-002"
    title = "内存使用过高"
    category = "OS 资源"
    severity = "medium"
    description = "物理内存或 swap 使用率异常"
    recommendation = "检查内存泄漏、SGA/PGA 配置"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"swap|memory", line, re.IGNORECASE):
                m = re.search(r"(\d+[.,]?\d*)%", line)
                if m:
                    try:
                        pct = float(m.group(1).replace(",", "."))
                        if pct > 90:
                            result.matched = True
                            result.evidence.append(Evidence(
                                category=self.category, rule_id=self.rule_id,
                                title=f"内存/Swap 使用 {pct}%", severity=self.severity,
                                log_file=file_path, log_snippet=line.strip(), line_number=i,
                                recommendation=self.recommendation, detail=f"内存使用率 {pct}%，超过 90%。"
                            ))
                    except ValueError:
                        pass
        return result


class KernelPanicRule(BaseRule):
    rule_id = "OS-003"
    title = "OS Kernel 异常/Panic"
    category = "OS 资源"
    severity = "critical"
    description = "操作系统内核 panic 或严重错误"
    recommendation = "检查 /var/log/messages, crash dump, 联系 OS 管理员"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"(?:panic|kernel oops|BUG:|kernel BUG|hung_task)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category, rule_id=self.rule_id, title="OS Kernel 异常",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="OS 内核异常影响数据库和集群稳定性。"
                ))
        return result
