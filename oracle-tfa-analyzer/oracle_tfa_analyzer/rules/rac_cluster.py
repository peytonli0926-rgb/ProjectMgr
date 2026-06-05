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
                    category=self.category, rule_id=self.rule_id, title="CRS 资源 OFFLINE",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="集群资源离线影响服务可用性。"
                ))
        return result


class FencingRebootRule(BaseRule):
    rule_id = "RAC-002"
    title = "节点隔离/重启"
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
                        category=self.category, rule_id=self.rule_id, title="节点隔离/通信异常",
                        severity=self.severity, log_file=file_path,
                        log_snippet=line.strip(), line_number=i,
                        recommendation=self.recommendation, detail=f"集群通信异常: {line.strip()[:100]}"
                    ))
        return result


class BrainSplitRule(BaseRule):
    rule_id = "RAC-003"
    title = "脑裂检测"
    category = "RAC/Clusterware"
    severity = "critical"
    description = "集群可能出现脑裂"
    recommendation = "检查私网心跳、CSS reconfig、voting disk"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"split.brain|brain.split|reconfig|reconfiguration", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category, rule_id=self.rule_id, title="集群重配置/疑似脑裂",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="集群发生重配置事件，可能伴随脑裂风险。"
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
                    category=self.category, rule_id=self.rule_id, title="OCR/Voting Disk 异常",
                    severity=self.severity, log_file=file_path,
                    log_snippet=line.strip(), line_number=i,
                    recommendation=self.recommendation, detail="OCR/voting disk 异常影响集群稳定性。"
                ))
        return result


class AsmCrsCommFailureRule(BaseRule):
    """ASM-CRS 通信故障链规则。

    捕获以下模式（常见于 ASM alert log）：
      1. failed to online diskgroup resource ora.XXX.dg (unable to communicate with CRSD/OHASD)
      2. giving up on client id [node1:db:hostname] which has not reconnected
      3. CSS requested to fence client node1:db:hostname
    """
    rule_id = "RAC-005"
    title = "ASM-CRS 通信故障"
    category = "RAC/Clusterware"
    severity = "critical"
    description = "ASM 无法与 CRSD/OHASD 通信，导致磁盘组无法 online，最终触发 CSS 隔离客户端"
    recommendation = (
        "1. 检查 CRS 堆栈状态: crsctl stat res -t\n"
        "2. 查看 CRS alert log: $GRID_HOME/log/<hostname>/alert*.log\n"
        "3. 检查 ASM 和 CRS 之间的网络心跳\n"
        "4. 如频繁出现，考虑重启 CRS 堆栈: crsctl stop crs -f && crsctl start crs"
    )

    # 三个阶段的匹配模式
    _PATTERN_ONLINE_FAIL = re.compile(
        r"failed to online diskgroup resource ora\.\w+\.dg\s*"
        r"\(unable to communicate with CRSD/OHASD\)",
        re.IGNORECASE,
    )
    _PATTERN_GIVEUP_CLIENT = re.compile(
        r"giving up on client id\s+\[.*?\]\s+which has not reconnected",
        re.IGNORECASE,
    )
    _PATTERN_CSS_FENCE = re.compile(
        r"CSS requested to fence client\s+\[.*?\]",
        re.IGNORECASE,
    )

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 阶段 1: 磁盘组 online 失败（因无法与 CRSD 通信）
            m1 = self._PATTERN_ONLINE_FAIL.search(stripped)
            if m1:
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="磁盘组 online 失败 — ASM 无法与 CRSD 通信",
                    severity="critical",
                    log_file=file_path,
                    log_snippet=stripped,
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="ASM 实例无法与 CRSD/OHASD 通信，磁盘组无法 online。这是 ASM-CRS 通信断裂的典型症状。"
                ))

            # 阶段 2: ASM 放弃等待客户端重连
            m2 = self._PATTERN_GIVEUP_CLIENT.search(stripped)
            if m2:
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="ASM 放弃客户端 — 客户端长时间未重连",
                    severity="high",
                    log_file=file_path,
                    log_snippet=stripped,
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="客户端长期未与 ASM 重连，ASM 将释放其资源。"
                ))

            # 阶段 3: CSS 隔离客户端
            m3 = self._PATTERN_CSS_FENCE.search(stripped)
            if m3:
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="CSS 隔离客户端",
                    severity="critical",
                    log_file=file_path,
                    log_snippet=stripped,
                    line_number=i,
                    recommendation=(
                        "检查被隔离节点的 CSS 心跳、私网延时、存储链路。\n"
                        "查看 CSS 日志: $GRID_HOME/log/<hostname>/cssd/ocssd.log"
                    ),
                    detail="CSS 请求隔离集群客户端节点，可能导致 RAC 节点被驱逐。"
                ))

        return result
