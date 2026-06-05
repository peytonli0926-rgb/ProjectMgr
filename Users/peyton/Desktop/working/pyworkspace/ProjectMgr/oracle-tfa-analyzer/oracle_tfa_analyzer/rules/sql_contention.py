"""SQL/性能争用 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class TopSqlByElapsedRule(BaseRule):
    rule_id = "SQL-001"
    title = "Top SQL 耗时过长"
    category = "SQL/性能争用"
    severity = "high"
    description = "Top SQL 的 Elapsed Time 超过阈值"
    recommendation = "分析执行计划，检查索引、统计信息、并行度等"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"Elapsed|elapsed|CPU|executions", line, re.IGNORECASE):
                nums = re.findall(r"([\d,]+[.,]?\d*)\s*(?:sec|min|ms|s)", line, re.IGNORECASE)
                for num_str, unit in re.findall(r"([\d,]+[.,]?\d*)\s*(sec|min|ms|s)", line, re.IGNORECASE):
                    try:
                        val = float(num_str.replace(",", ""))
                        if unit.lower() == "min":
                            val *= 60
                        elif unit.lower() == "ms":
                            val /= 1000
                        if val > 60:
                            result.matched = True
                            result.evidence.append(Evidence(
                                category=self.category,
                                rule_id=self.rule_id,
                                title=f"SQL 耗时 {num_str} {unit}",
                                severity=self.severity,
                                log_file=file_path,
                                log_snippet=line.strip(),
                                line_number=i,
                                recommendation=self.recommendation,
                                detail=f"SQL 执行时间 {val:.1f}s，超过 60s 阈值。"
                            ))
                            break
                    except ValueError:
                        continue
        return result


class WaitEventEnqueueRule(BaseRule):
    rule_id = "SQL-002"
    title = "等待事件 — Enqueue/锁争用"
    category = "SQL/性能争用"
    severity = "high"
    description = "检测到 enqueue 类型等待事件"
    recommendation = "检查锁定对象、长时间未提交事务、应用设计中的锁冲突"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"enq:|enqueue|TX|TM|HW|UL|buffer busy|row lock", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="Enqueue/锁等待事件",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail=f"检测到锁争用等待事件: {line.strip()[:80]}"
                ))
        return result


class TempUsageRule(BaseRule):
    rule_id = "SQL-003"
    title = "临时表空间使用异常"
    category = "SQL/性能争用"
    severity = "medium"
    description = "临时表空间使用量过大"
    recommendation = "检查排序操作、Hash Join、临时段使用情况"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"temp|temporary|sort", line, re.IGNORECASE) and \
               re.search(r"(?:used|usage|alloc|extend|full)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="临时表空间使用异常",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail=f"临时表空间使用情况异常: {line.strip()[:80]}"
                ))
        return result
