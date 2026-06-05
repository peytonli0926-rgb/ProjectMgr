"""完整分析管道：解压 → 分析 → 生成报告。"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from .config import OUTPUT_DIR, TEMP_DIR
from .extractor import extract_tfa_zip, cleanup_temp
from .engine import analyze
from .reporting.word_report import generate_reports

logger = logging.getLogger(__name__)


def run_pipeline(
    zip_path: str | Path,
    output_dir: str | Path | None = None,
    keep_temp: bool = False,
) -> dict[str, Any]:
    """执行完整的 TFA 分析管道。

    Args:
        zip_path: TFA zip 包路径
        output_dir: 输出目录（默认 output/）
        keep_temp: 是否保留临时解压目录（默认 False 清理）

    Returns:
        dict: {
            "source_zip": str,
            "evidence_path": str,
            "executive_path": str,
            "technical_path": str,
            "evidence_count": int,
            "risk_high": int,
            "risk_medium": int,
            "by_category": dict,
        }
    """
    zip_path = Path(zip_path).expanduser().resolve()
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    zip_name = zip_path.name

    logger.info("=" * 60)
    logger.info("Oracle TFA Analyzer Pipeline")
    logger.info("源文件: %s", zip_path)
    logger.info("输出目录: %s", out_dir)
    logger.info("=" * 60)

    # Step 1: 解压
    logger.info("[1/4] 解压 TFA zip 包...")
    extract_dir = extract_tfa_zip(zip_path)

    try:
        # Step 2: 分析
        logger.info("[2/4] 规则分析中...")
        evidence_data = analyze(extract_dir, out_dir)

        # Step 3: 生成报告
        logger.info("[3/4] 生成 Word 报告...")
        report_paths = generate_reports(evidence_data, zip_name, out_dir)

        # Step 4: 汇总结果
        logger.info("[4/4] 汇总完成！")
        risk_summary = evidence_data.get("risk_summary", {})
        result = {
            "source_zip": str(zip_path),
            "evidence_path": report_paths.get("evidence_path", ""),
            "executive_path": report_paths.get("executive", ""),
            "technical_path": report_paths.get("technical", ""),
            "evidence_count": evidence_data.get("metadata", {}).get("total_evidence", 0),
            "risk_high": risk_summary.get("critical", 0) + risk_summary.get("high", 0),
            "risk_medium": risk_summary.get("medium", 0),
            "by_category": evidence_data.get("by_category", {}),
            "evidence": evidence_data.get("evidence", []),
        }
        return result

    finally:
        if not keep_temp:
            cleanup_temp(extract_dir)
        else:
            logger.info("保留临时目录: %s", extract_dir)
