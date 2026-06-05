"""完整分析管道。"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from .config import OUTPUT_DIR, TEMP_DIR
from .extractor import (
    extract_tfa_zip,
    cleanup_temp,
    discover_files,
    discover_root_snapshots,
    _detect_hostname,
    get_snapshot_category_mapping,
)
from .engine import analyze
from .reporting.word_report import generate_reports
from .timeline import generate_timeline
from .analysis_chain import build_analysis_chains

logger = logging.getLogger(__name__)


def run_pipeline(
    zip_path: str | Path,
    output_dir: str | Path | None = None,
    keep_temp: bool = False,
    progress_callback: Callable[[str, str, int, int], None] | None = None,
    time_filter_days: int | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    first_match_only: bool = False,
) -> dict[str, Any]:
    """
    运行完整分析管道。

    Args:
        zip_path: TFA zip 包路径
        output_dir: 输出目录（默认 output/）
        keep_temp: 是否保留临时解压目录（默认 False 清理）
        progress_callback: 进度回调
        time_filter_days: 时间过滤天数，仅分析最近 N 天的日志行
        time_start: 自定义起始日期 yyyy-mm-dd（优先级高于 time_filter_days）
        time_end: 自定义截止日期 yyyy-mm-dd
        first_match_only: 如果为 True，找到第一条证据后立即停止分析

    progress_callback(phase, message, current, total)
        phase: 阶段标识，如 "extract", "analyze", "report", "done"
        message: 人类可读的描述文本
        current: 当前进度
        total: 总量
    """
    def cb(phase: str, msg: str, cur: int, tot: int):
        if progress_callback:
            progress_callback(phase, msg, cur, tot)

    zip_path = Path(zip_path).expanduser().resolve()
    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    zip_name = zip_path.name

    cb("extract", "正在解压 TFA zip 包...", 0, 100)
    extract_dir = extract_tfa_zip(zip_path)

    try:
        cb("extract", "解压完成，准备分析", 50, 100)

        if time_start and time_end:
            cb("analyze", f"规则分析中（{time_start} → {time_end}）...", 0, 100)
        elif time_filter_days:
            cb("analyze", f"规则分析中（仅最近 {time_filter_days} 天）...", 0, 100)
        else:
            cb("analyze", "规则分析中...", 0, 100)

        evidence_data = analyze(
            extract_dir, out_dir,
            progress_callback=lambda msg, cur, tot: cb("analyze", msg, cur, tot),
            time_filter_days=time_filter_days,
            time_start=time_start,
            time_end=time_end,
            first_match_only=first_match_only,
        )

        cb("report", "正在生成 Word 报告...", 0, 100)
        report_paths = generate_reports(evidence_data, zip_name, out_dir)

        cb("report", "Word 报告生成完毕", 100, 100)

        # ── 保存 snapshot_manifest.json（供时间线分析使用） ──
        cb("report", "正在生成 snapshot manifest...", 0, 100)
        snapshot_manifest_path = out_dir / "snapshot_manifest.json"
        try:
            hostname = _detect_hostname(extract_dir)
            snapshots = discover_root_snapshots(extract_dir / hostname if hostname else extract_dir, hostname or "")
            manifest: list[dict] = []
            for cat, files in snapshots.items():
                if cat.startswith("_"):
                    continue
                for fpath in files:
                    fname = fpath.name
                    ts = None
                    # 尝试从文件名提取时间戳
                    try:
                        st_mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc)
                        ts = st_mtime.isoformat(timespec="seconds")
                    except Exception:
                        pass
                    manifest.append({
                        "file": str(fpath.relative_to(extract_dir)) if extract_dir else fpath.name,
                        "filename": fname,
                        "category": cat,
                        "top_category": get_snapshot_category_mapping(cat),
                        "timestamp": ts,
                    })
            snapshot_manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("snapshot_manifest.json 已写入 %s（共 %d 条）", snapshot_manifest_path, len(manifest))
        except Exception as exc:
            logger.warning("生成 snapshot_manifest.json 失败: %s", exc)
            manifest = []
            snapshot_manifest_path.write_text("[]", encoding="utf-8")

        # ── 生成故障时间线 ──
        cb("report", "正在生成故障时间线...", 0, 100)
        timeline_path = out_dir / "fault_timeline.json"
        try:
            timeline_data = generate_timeline(evidence_data, manifest)
            timeline_path.write_text(
                json.dumps(timeline_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "fault_timeline.json 已写入 %s（共 %d 个故障簇）",
                timeline_path,
                len(timeline_data.get("fault_clusters", [])),
            )
        except Exception as exc:
            logger.warning("生成故障时间线失败: %s", exc)
            timeline_path.write_text(
                json.dumps({"fault_clusters": [], "timeline_events": [], "metadata": {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            timeline_data = {"fault_clusters": [], "timeline_events": [], "metadata": {}}

        # ── 生成分析链（入口驱动） ──
        cb("report", "正在生成分析链...", 0, 100)
        analysis_chains_path = out_dir / "analysis_chains.json"
        try:
            chains = build_analysis_chains(evidence_data, manifest)
            analysis_chains_path.write_text(
                json.dumps(chains, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                "analysis_chains.json 已写入 %s（共 %d 条分析链）",
                analysis_chains_path,
                len(chains),
            )
        except Exception as exc:
            logger.warning("生成分析链失败: %s", exc)
            analysis_chains_path.write_text("[]", encoding="utf-8")
            chains = []

        risk_summary = evidence_data.get("risk_summary", {})
        timeline_meta = timeline_data.get("metadata", {})
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
            "timeline_path": str(timeline_path),
            "snapshot_manifest_path": str(snapshot_manifest_path),
            "timeline_clusters": timeline_meta.get("clusters_found", 0),
            "timeline_data": timeline_data,
            "analysis_chains": chains,
        }

        cb("done", "分析完成！", 100, 100)
        return result
    finally:
        if not keep_temp:
            cleanup_temp(extract_dir)

