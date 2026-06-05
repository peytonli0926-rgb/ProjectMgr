"""I/O 性能 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class HighDiskLatencyRule(BaseRule):
    rule_id = "IO-001"
    title = "磁盘延迟过高"
    category = "I/O 性能"
    severity = "high"
    description = "磁盘平均 I/O 服务时间超过阈值"
    recommendation = "检查存储负载、AWR 中 Top Event 是否为 I/O 相关，考虑存储迁移或 SQL 优化"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"(?:await|svctm|r_await|w_await|avg-exe|average wait|avg wait)", line, re.IGNORECASE):
                nums = re.findall(r"(\d+[.,]?\d*)", line)
                for num_str in nums:
                    try:
                        val = float(num_str.replace(",", "."))
                        if val > 50:
                            result.matched = True
                            result.evidence.append(Evidence(
                                category=self.category,
                                rule_id=self.rule_id,
                                title=f"磁盘延迟 {val} ms（异常）" if val > 100 else f"磁盘延迟 {val} ms（偏高）",
                                severity=self.severity if val > 100 else "medium",
                                log_file=file_path,
                                log_snippet=line.strip(),
                                line_number=i,
                                recommendation=self.recommendation,
                                detail=f"检测到磁盘 I/O 延迟 {val} ms，建议阈值 < 20ms。"
                            ))
                            break
                    except ValueError:
                        continue
        return result


class IOThroughputRule(BaseRule):
    rule_id = "IO-002"
    title = "I/O 吞吐量异常"
    category = "I/O 性能"
    severity = "medium"
    description = "磁盘读写速率异常（过高或过低）"
    recommendation = "检查是否存在全表扫描、异常 SQL、或存储瓶颈"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(r"([\d.]+)\s*(?:MB/s|GB/s|kB/s|KB/s)", line, re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    result.matched = True
                    result.evidence.append(Evidence(
                        category=self.category,
                        rule_id=self.rule_id,
                        title=f"I/O 速率 {val} {m.group(2)}",
                        severity=self.severity,
                        log_file=file_path,
                        log_snippet=line.strip(),
                        line_number=i,
                        recommendation=self.recommendation,
                        detail=f"检测到 I/O 吞吐量为 {val} {m.group(2)}。"
                    ))
                except ValueError:
                    pass
        return result
