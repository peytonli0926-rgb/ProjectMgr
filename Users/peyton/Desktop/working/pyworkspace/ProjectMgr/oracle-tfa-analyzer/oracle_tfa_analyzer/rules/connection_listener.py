"""连接/监听 — 规则。"""

import re
from .base import BaseRule, RuleResult, Evidence


class ListenerDownRule(BaseRule):
    rule_id = "LSN-001"
    title = "监听器停止/异常"
    category = "连接/监听"
    severity = "high"
    description = "Listener 停止运行或出现致命错误"
    recommendation = "检查 listener.log，重启监听器并确认网络配置"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"listener|TNS|LSNR", line, re.IGNORECASE) and \
               re.search(r"(?:error|fail|stop|down|refuse|closed)", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="监听器异常",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="监听器异常会导致数据库无法接受新连接。"
                ))
        return result


class ConnectionStormRule(BaseRule):
    rule_id = "LSN-002"
    title = "连接风暴/大量连接"
    category = "连接/监听"
    severity = "medium"
    description = "短时间内大量连接涌入"
    recommendation = "检查应用连接池配置，确认是否合理设置 max_connections"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        conns = 0
        for line in content.splitlines():
            if re.search(r"connect|established|accept", line, re.IGNORECASE):
                conns += 1
        if conns > 100:
            result.matched = True
            result.evidence.append(Evidence(
                category=self.category,
                rule_id=self.rule_id,
                title=f"文件中共 {conns} 个连接记录",
                severity=self.severity,
                log_file=file_path,
                log_snippet=f"总连接记录数: {conns}",
                recommendation=self.recommendation,
                detail=f"在 listener 日志中发现 {conns} 条连接记录，可能存在连接风暴。"
            ))
        return result


class TNS12170Rule(BaseRule):
    rule_id = "LSN-003"
    title = "ORA-12170 TNS 连接超时"
    category = "连接/监听"
    severity = "high"
    description = "TNS 连接超时错误"
    recommendation = "检查网络连通性、防火墙、sqlnet.ora 中的连接超时参数"

    def match(self, file_path: str, content: str) -> RuleResult:
        result = RuleResult()
        for i, line in enumerate(content.splitlines(), 1):
            if re.search(r"ORA-12170|TNS-12170|TNS-12535", line, re.IGNORECASE):
                result.matched = True
                result.evidence.append(Evidence(
                    category=self.category,
                    rule_id=self.rule_id,
                    title="TNS 连接超时",
                    severity=self.severity,
                    log_file=file_path,
                    log_snippet=line.strip(),
                    line_number=i,
                    recommendation=self.recommendation,
                    detail="TNS 连接超时通常由网络延迟、防火墙或 listener 负载过高引起。"
                ))
        return result
