"""Word 报告生成入口。"""

import logging
from pathlib import Path
from typing import Any
from .executive_report import generate_executive_report
from .technical_report import generate_technical_report

logger = logging.getLogger(__name__)


def generate_reports(evidence_data: dict[str, Any], source_zip_name: str, output_dir: str | Path) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = source_zip_name.replace(".zip", "")
    exec_path = out_dir / f"领导汇报版_{base}.docx"
    tech_path = out_dir / f"技术专家版_{base}.docx"

    generate_executive_report(evidence_data, source_zip_name, exec_path)
    generate_technical_report(evidence_data, source_zip_name, tech_path)

    return {
        "executive": str(exec_path),
        "technical": str(tech_path),
        "evidence_path": str(out_dir / "evidence.json"),
    }
