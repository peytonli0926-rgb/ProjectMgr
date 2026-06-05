"""RAC/Clusterware — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class CrsOfflineRule(BaseRule):
    rule_id = "RAC-001"
    title = "CRS 资源 OFFLINE"
    category = "RAC/Clusterware"
    severity = "high"
    description = "CRS 管理的资源处于 OFFLINE 状态"
    recommendation = "使用 crsctl stat res -t 检查资源状态，尝试 crsctl start res"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"OFFLINE", line, re.IGNORECASE) and re.search(r"(?:ora\.|resource)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="CRS 资源 OFFLINE",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="集群资源处于离线状态，影响服务可用性。"
                ))
        return result


class FencingRebootRule(BaseRule):
    rule_id = "RAC-002"
    title = "节点隔离/重启 (Fencing/Reboot)"
    category = "RAC/Clusterware"
    severity = "critical"
    description = "集群节点被 fencing 或重启"
    recommendation = "检查 CSS 心跳超时、网络延迟和存储路径"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        keywords = ["fencing", "evicted", "reboot", "node restart", "CSSD", "cluster communication"]
        for i, line in enumerate(content.splitlines(), 1):
            if any(re.search(kw, line, re.IGNORECASE) for kw in keywords):
                if re.search(r"(?:error|fail|dead|loss|abort|timeout)", line, re.IGNORECASE):
                    result.matched = True
                    result.evidence.append(Evidence(
                        category=self.category,
                        rule_id=self.rule_id,
                        title="节点隔离/通信异常",
                        severity=self.severity,
                        log_file=file_path,
                        log_snippet=line.strip(),
                        line_number=i,
                        recommendation=self.recommendation,
                        detail=f"检测到集群通信异常关键词: {line.strip()[:100]}"
                    ))
        return result


class BrainSplitRule(BaseRule):
    rule_id = "RAC-003"
    title = "脑裂检测 (Split Brain)"
    category = "RAC/Clusterware"
    severity = "critical"
    description = "集群可能出现脑裂"
    recommendation = "检查私网心跳网络、CSS reconfig 日志、 voting disk 状态"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"split.brain|brain.split|reconfig|reconfiguration", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="集群重配置/疑似脑裂",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="集群发生重配置事件，可能伴随脑裂风险。"
                ))
        return result


class OCRCorruptRule(BaseRule):
    rule_id = "RAC-004"
    title = "OCR/Voting Disk 异常"
    category = "RAC/Clusterware"
    severity = "high"
    description = "OCR 或 voting disk 访问错误"
    recommendation = "检查 OCR 和 voting disk 所在存储，使用 ocrcheck 验证完整性"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"OCR|voting|Voting Disk", line, re.IGNORECASE) and \
               re.search(r"(?:error|fail|corrupt|not accessible|I/O)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="OCR/Voting Disk 异常",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="OCR 或 voting disk 异常影响集群稳定性。"
                ))
        return result
