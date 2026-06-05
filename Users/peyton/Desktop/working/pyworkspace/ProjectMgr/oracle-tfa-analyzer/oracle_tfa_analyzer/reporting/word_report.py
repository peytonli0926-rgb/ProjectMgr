"""Word 报告生成入口。同时生成领导汇报版和技术专家版。"""

import json
import logging
from pathlib import Path
from typing import Any
from .executive_report import generate_executive_report
from .technical_report import generate_technical_report

logger = logging.getLogger(__name__)


def generate_reports(
    evidence_data: dict[str, Any],
    source_zip_name: str,
    output_dir: str | Path,
) -> dict[str, str]:
    """同时生成领导汇报版和技术专家版 Word 报告。

    Returns:
        dict: {"executive": "路径", "technical": "路径"}
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exec_path = out_dir / f"领导汇报版_{source_zip_name.replace('.zip', '')}.docx"
    tech_path = out_dir / f"技术专家版_{source_zip_name.replace('.zip', '')}.docx"

    exec_result = generate_executive_report(evidence_data, source_zip_name, exec_path)
    tech_result = generate_technical_report(evidence_data, source_zip_name, tech_path)

    return {
        "executive": str(exec_result),
        "technical": str(tech_result),
        "evidence_path": str(out_dir / "evidence.json"),
    }
