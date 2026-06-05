"""规则基类与 Evidence 数据模型。"""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Evidence:
    category: str
    rule_id: str
    title: str
    severity: str
    log_file: str
    log_snippet: str
    line_number: int = 0
    recommendation: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleResult:
    matched: bool = False
    evidence: list[Evidence] = field(default_factory=list)


class BaseRule:
    rule_id: str = ""
    title: str = ""
    category: str = ""
    severity: str = "info"
    description: str = ""
    recommendation: str = ""

    def match(self, file_path: str, content: str) -> RuleResult:
        raise NotImplementedError
