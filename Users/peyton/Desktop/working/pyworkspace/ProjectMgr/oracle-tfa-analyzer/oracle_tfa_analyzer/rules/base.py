"""规则基类与 Evidence 数据模型。"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Evidence:
    """单条证据的标准化结构。"""
    category: str            # 分析方向，如 "数据库错误与稳定性"
    rule_id: str             # 规则编号，如 "DB-001"
    title: str               # 证据标题
    severity: str            # 风险等级: critical/high/medium/low/info
    log_file: str            # 来源日志文件（相对路径）
    log_snippet: str         # 日志中的关键片段（≥1 行）
    line_number: int = 0     # 日志行号（可选）
    recommendation: str = "" # 整改建议
    detail: str = ""         # 技术解释

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleResult:
    """单条规则的匹配结果。"""
    matched: bool = False
    evidence: list[Evidence] = field(default_factory=list)


class BaseRule:
    """所有规则需继承此类。"""
    rule_id: str = ""
    title: str = ""
    category: str = ""
    severity: str = "info"
    description: str = ""
    recommendation: str = ""

    def match(self, file_path: str, content: str) -> RuleResult:
        """检查文件内容是否命中规则。由子类实现。"""
        raise NotImplementedError
