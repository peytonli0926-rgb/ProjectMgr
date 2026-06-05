"""ADG/备份 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class DataGapRule(BaseRule):
    rule_id = "ADG-001"
    title = "Data Guard 日志缺口 (Gap)"
    category = "ADG/备份"
    severity = "high"
    description = "备库存在日志缺口，无法实时同步"
    recommendation = "检查网络连通性、归档日志可用性，手动 gap resolution"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"gap|fetching gap|archive gap|log gap|GAP", line):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="Data Guard 日志缺口",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="备库与主库之间存在日志缺口，数据保护能力下降。"
                ))
        return result


class DGTransportDelayRule(BaseRule):
    rule_id = "ADG-002"
    title = "DG 同步延迟过高"
    category = "ADG/备份"
    severity = "medium"
    description = "Data Guard 日志 apply 延迟超过阈值"
    recommendation = "检查网络带宽、备库 I/O 能力，考虑启用实时 apply"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            m = re.search(r"(?:lag|delay|transport lag|apply lag)\D{0,10}(\d+)\s*(?:min|分钟|秒)?", line, re.IGNORECASE)
            if m:
                try:
                    val = int(m.group(1))
                    level = "medium" if val < 30 else "high"
                    result.matched = True
                    result.evidence.append(Evidence(
                        category=self.category,
                        rule_id=self.rule_id,
                        title=f"DG 同步延迟 {val} 分钟",
                        severity=level,
                        log_file=file_path,
                        log_snippet=line.strip(),
                        line_number=i,
                        recommendation=self.recommendation,
                        detail=f"Data Guard 同步延迟 {val} 分钟，建议控制在 5 分钟内。"
                    ))
                except ValueError:
                    pass
        return result


class RmanErrorRule(BaseRule):
    rule_id = "ADG-003"
    title = "RMAN 备份错误"
    category = "ADG/备份"
    severity = "high"
    description = "RMAN 备份失败或报错"
    recommendation = "检查 RMAN 脚本、备份目录、磁盘空间"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"RMAN-\d{4,5}|ORA-\d{5}", line) and \
               re.search(r"error|fail|abort", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="RMAN 备份错误",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail=f"RMAN 备份遇到错误: {line.strip()[:80]}"
                ))
        return result
