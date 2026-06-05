"""核心分析引擎：遍历文件 — 应用规则 — 生成 evidence。"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any
from .config import ANALYSIS_CATEGORIES, OUTPUT_DIR
from .extractor import discover_files
from .rules.registry import get_all_rules

logger = logging.getLogger(__name__)


def analyze(extract_dir: Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    """核心分析：
    1. 发现文件
    2. 对每个文件应用所有规则
    3. 汇总 evidence.json
    """
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    discovered = discover_files(extract_dir)
    logger.info("发现文件类别: %s", {k: len(v) for k, v in discovered.items()})

    all_rules = get_all_rules()
    all_evidence: list[dict] = []
    files_analyzed = 0

    # 遍历发现的文件并应用规则
    for cat, files in discovered.items():
        for fpath in files:
            rel_path = str(fpath.relative_to(extract_dir))
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = fpath.read_text(encoding="latin-1", errors="replace")
            files_analyzed += 1

            for rule in all_rules:
                try:
                    result = rule.match(rel_path, content)
                    if result.matched:
                        for ev in result.evidence:
                            all_evidence.append(ev.to_dict())
                except Exception as e:
                    logger.warning("规则 %s 分析 %s 时出错: %s", rule.rule_id, rel_path, e)

    # 归类统计
    by_category: dict[str, list[dict]] = {}
    for ev in all_evidence:
        by_category.setdefault(ev["category"], []).append(ev)

    risk_counts = {"high": 0, "medium": 0, "low": 0, "critical": 0, "info": 0}
    for ev in all_evidence:
        sev = ev.get("severity", "info")
        risk_counts[sev] = risk_counts.get(sev, 0) + 1

    evidence_data = {
        "metadata": {
            "analyzed_at": datetime.now().isoformat(timespec="seconds"),
            "files_analyzed": files_analyzed,
            "total_evidence": len(all_evidence),
            "rules_applied": len(all_rules),
        },
        "risk_summary": risk_counts,
        "by_category": by_category,
        "evidence": all_evidence,
    }

    # 写入 evidence.json
    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("evidence.json 已写入 %s（共 %d 条证据）", evidence_path, len(all_evidence))

    return evidence_data
