"""数据库错误与稳定性 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class ORA600Rule(BaseRule):
    rule_id = "DB-001"
    title = "ORA-00600 内部错误"
    category = "数据库错误与稳定性"
    severity = "critical"
    description = "Oracle 内部错误，通常表示 bug 或损坏"
    recommendation = "收集相关 trace 文件，联系 Oracle 支持或应用补丁"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"ORA-00600", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="ORA-00600 是 Oracle 内部错误，可能由逻辑损坏、bug 或硬件问题引发。"
                ))
        return result


class ORA7445Rule(BaseRule):
    rule_id = "DB-002"
    title = "ORA-07445 进程异常终止"
    category = "数据库错误与稳定性"
    severity = "high"
    description = "操作系统异常信号导致进程终止"
    recommendation = "检查 trace 文件，分析信号类型，确认是否为 OS 或 bug 引起"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"ORA-07445", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="ORA-07445 表示收到了操作系统异常信号（如 SIGSEGV），通常需要分析 call stack。"
                ))
        return result


class ORA6002Rule(BaseRule):
    rule_id = "DB-003"
    title = "ORA-00604 — 递归 SQL 错误"
    category = "数据库错误与稳定性"
    severity = "high"
    description = "递归 SQL 执行失败"
    recommendation = "检查递归 SQL 上下文，验证相关对象状态"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"ORA-00604", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="ORA-00604 在递归 SQL 执行时出现，常伴随其他错误。"
                ))
        return result


class InstanceCrashRule(BaseRule):
    rule_id = "DB-004"
    title = "实例崩溃/重启记录"
    category = "数据库错误与稳定性"
    severity = "critical"
    description = "数据库实例异常终止或重启"
    recommendation = "检查实例关闭原因，查看 alert log 中前面的错误堆栈"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"Shutting down instance|terminating instance|instance terminated|abnormal termination", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="实例非正常关闭是严重事件，需重点排查前序错误。"
                ))
            if re.search(r"Starting ORACLE instance|startup mounted|startup open", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=f"实例启动记录: {line.strip()[:80]}",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation="确认启动是否为计划内操作",
                    detail="实例启动记录，需核实是否为正常重启。"
                ))
        return result


class GenericDBErrorRule(BaseRule):
    rule_id = "DB-005"
    title = "常见数据库错误 (ORA-)"
    category = "数据库错误与稳定性"
    severity = "medium"
    description = "检测 alert log 中常见的 ORA- 错误"
    recommendation = "根据具体 ORA 错误号排查"

    # 排除已由其他规则捕获的错误
    _excluded = {"00600", "07445", "00604"}

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(r"ORA-(\d{5})", line)
            if m and m.group(1) not in self._excluded:
                result.matched = True
                err_code = m.group(1)
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title=f"ORA-{err_code} 错误",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail=f"检测到 ORA-{err_code}，请根据具体错误号进一步排查。"
                ))
        return result
