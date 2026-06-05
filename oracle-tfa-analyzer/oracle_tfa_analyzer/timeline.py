"""故障时间线聚类分析模块。

从 evidence.json + snapshot_manifest.json 自动发现故障时间点、
聚类时序事件、定位根因、并匹配相关快照文件，生成前端可渲染的时间线数据。
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 故障聚类参数 ──
CLUSTER_WINDOW_MINUTES = 10  # 10 分钟内的事件归为同一故障簇
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _parse_timestamp(ts_str: str | None) -> datetime | None:
    """解析多种时间格式为 datetime 对象。"""
    if not ts_str:
        return None
    ts_str = ts_str.strip()

    patterns = [
        ("%Y-%m-%dT%H:%M:%S", re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")),
        ("%Y-%m-%d %H:%M:%S", re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")),
        ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ]
    for fmt, pattern in patterns:
        if pattern.match(ts_str):
            try:
                return datetime.strptime(ts_str[:19] if fmt != "%Y-%m-%d" else ts_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    # Oracle alert log: Mon Aug 19 14:30:00 2022
    try:
        return datetime.strptime(ts_str, "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # Oracle CSS log: 2022-08-28 14:27:39.637
    try:
        return datetime.strptime(ts_str[:26], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    logger.debug("无法解析时间戳: %s", ts_str)
    return None


def _get_evidence_time(ev: dict) -> datetime | None:
    """从证据记录中提取时间。"""
    discovered_at = ev.get("discovered_at")
    if discovered_at:
        dt = _parse_timestamp(discovered_at)
        if dt:
            return dt

    log_snippet = ev.get("log_snippet", "") or ""
    first_line = log_snippet.split("\n")[0].strip()
    if first_line:
        dt = _parse_timestamp(first_line)
        if dt:
            return dt

    return None


def _get_evidence_severity(ev: dict) -> int:
    """返回严重级别对应的排序值（越小越严重）。"""
    return SEVERITY_ORDER.get(ev.get("severity", "info"), 99)


def _get_evidence_category_group(cat: str) -> str:
    """将细粒度分类映射为方向组。"""
    cat_lower = cat.lower()
    if "数据库" in cat or "db" in cat_lower or "oracle" in cat_lower:
        return "数据库错误与稳定性"
    if "rac" in cat or "cluster" in cat_lower or "crs" in cat_lower or "css" in cat_lower:
        return "RAC / Clusterware"
    if "asm" in cat or "存储" in cat:
        return "ASM / 存储"
    if "os" in cat_lower or "系统" in cat or "操作系统" in cat:
        return "OS 资源"
    if "io" in cat_lower or "i/o" in cat_lower or "性能" in cat:
        return "I/O 性能"
    if "连接" in cat or "监听" in cat or "listener" in cat_lower:
        return "连接 / 监听"
    if "sql" in cat_lower or "adg" in cat_lower or "备份" in cat:
        return "SQL / 性能争用"
    return cat


def _build_fault_title(events: list[dict]) -> str:
    """根据簇内事件自动推断故障标题。"""
    # 找最严重的规则 ID
    critical_events = sorted(events, key=lambda e: (
        _get_evidence_severity(e),
        e.get("rule_id", ""),
    ))

    for ev in critical_events:
        rule_id = ev.get("rule_id", "")
        if rule_id.startswith("RAC-"):
            # 检查是否是 ASM-CRS 通信故障模式
            desc = (ev.get("description", "") or "").lower()
            snippet = (ev.get("log_snippet", "") or "").lower()
            if "asm" in desc or "asm" in snippet:
                return "ASM-CRS 通信故障"
            if "css" in desc or "css" in snippet:
                return "CSS 集群脑裂 / Fence"
            if "crash" in desc or "crash" in snippet:
                return "实例崩溃"
            if "diskgroup" in desc or "diskgroup" in snippet:
                return "磁盘组故障"
            if "ora-" in desc or "ora-" in snippet:
                return "ORA- 数据库错误"
            if "alert" in desc or "ora-" in snippet:
                return "Alert Log 错误"
        if rule_id.startswith("ORA-"):
            return "ORA- 数据库错误"
        if rule_id.startswith("OS-"):
            return "操作系统资源故障"
        if rule_id.startswith("LISTENER-"):
            return "监听器故障"
        if rule_id.startswith("ASM-"):
            return "ASM 存储故障"

    # 根据 severity 推断
    severities = sorted(set(ev.get("severity", "info") for ev in events), key=lambda s: SEVERITY_ORDER.get(s, 99))
    if severities and severities[0] in ("critical", "high"):
        return "关键故障"

    # 用类别推断
    cats = list(set(ev.get("category", "") for ev in events))
    if cats:
        return " / ".join(cats[:2]) + " 相关事件"

    return "未分类故障"


def cluster_events(
    evidence: list[dict],
    window_minutes: int = CLUSTER_WINDOW_MINUTES,
) -> list[dict]:
    """按时间窗口将证据聚类为故障簇。

    Args:
        evidence: evidence.json 中的 evidence 数组
        window_minutes: 聚类窗口（默认 10 分钟）

    Returns:
        故障簇列表，每簇按时间排序、包含根因推断
    """
    # 过滤有有效时间戳的证据
    timed_ev: list[tuple[datetime, dict]] = []
    for ev in evidence:
        dt = _get_evidence_time(ev)
        if dt:
            timed_ev.append((dt, ev))

    if not timed_ev:
        return []

    # 按时间排序
    timed_ev.sort(key=lambda x: x[0])

    # 聚类
    clusters: list[list[dict]] = []
    current: list[dict] = []
    current_dt: datetime | None = None
    window = timedelta(minutes=window_minutes)

    for dt, ev in timed_ev:
        if current_dt is None:
            current.append(ev)
            current_dt = dt
        elif dt - current_dt <= window:
            current.append(ev)
        else:
            clusters.append(current)
            current = [ev]
            current_dt = dt

    if current:
        clusters.append(current)

    # 构建输出
    result = []
    for idx, cluster in enumerate(clusters):
        # 按时间排序
        cluster.sort(key=lambda e: _get_evidence_time(e) or datetime.min.replace(tzinfo=timezone.utc))

        events_out = []
        for ev in cluster:
            dt = _get_evidence_time(ev)
            events_out.append({
                "time": dt.isoformat() if dt else None,
                "rule_id": ev.get("rule_id", ""),
                "severity": ev.get("severity", "info"),
                "category": ev.get("category", ""),
                "category_group": _get_evidence_category_group(ev.get("category", "")),
                "description": ev.get("description", ""),
                "source_file": ev.get("source_file", ""),
                "log_snippet": (ev.get("log_snippet", "") or "").split("\n")[0] if ev.get("log_snippet") else "",
            })

        # 根因 = 时间最早且级别最严重的事件
        root_cause = min(cluster, key=lambda e: (
            _get_evidence_severity(e),
            _get_evidence_time(e) or datetime.min.replace(tzinfo=timezone.utc),
        ))

        # 收集涉及的文件
        source_files = sorted(set(
            ev.get("source_file", "")
            for ev in cluster
            if ev.get("source_file")
        ))

        # 收集涉及的分类
        categories = list(set(
            _get_evidence_category_group(ev.get("category", ""))
            for ev in cluster
        ))

        sev_scores = [SEVERITY_ORDER.get(ev.get("severity", "info"), 99) for ev in cluster]
        cluster_severity = "info"
        if sev_scores:
            best = min(sev_scores)
            for k, v in SEVERITY_ORDER.items():
                if v == best:
                    cluster_severity = k
                    break

        result.append({
            "cluster_id": idx + 1,
            "start_time": events_out[0]["time"] if events_out else None,
            "end_time": events_out[-1]["time"] if events_out else None,
            "event_count": len(events_out),
            "severity": cluster_severity,
            "title": _build_fault_title(cluster),
            "root_cause": {
                "time": _get_evidence_time(root_cause).isoformat() if _get_evidence_time(root_cause) else None,
                "rule_id": root_cause.get("rule_id", ""),
                "description": root_cause.get("description", ""),
                "source_file": root_cause.get("source_file", ""),
                "log_snippet": (root_cause.get("log_snippet", "") or "").split("\n")[0] if root_cause.get("log_snippet") else "",
            },
            "source_files": source_files,
            "categories": categories,
            "events": events_out,
        })

    return result


def find_related_snapshots(
    cluster: dict,
    snapshot_manifest: list[dict],
) -> list[dict]:
    """查找故障时间附近的快照文件。

    Args:
        cluster: 故障簇
        snapshot_manifest: snapshot_manifest.json 中记录的根快照文件列表

    Returns:
        与故障时间相关的快照文件列表
    """
    start_str = cluster.get("start_time")
    end_str = cluster.get("end_time")
    if not start_str or not end_str:
        return []

    start_dt = _parse_timestamp(start_str)
    end_dt = _parse_timestamp(end_str)
    if not start_dt or not end_dt:
        return []

    # 故障前后各扩展 30 分钟
    search_start = start_dt - timedelta(minutes=30)
    search_end = end_dt + timedelta(minutes=30)

    related: list[dict] = []
    for snap in snapshot_manifest:
        snap_time_str = snap.get("timestamp")
        if not snap_time_str:
            continue
        snap_dt = _parse_timestamp(snap_time_str)
        if snap_dt and search_start <= snap_dt <= search_end:
            related.append({
                "file": snap.get("file", ""),
                "category": snap.get("category", ""),
                "timestamp": snap_time_str,
            })

    return related


def generate_timeline(
    evidence_data: dict,
    snapshot_manifest: list[dict] | None = None,
    window_minutes: int = CLUSTER_WINDOW_MINUTES,
) -> dict[str, Any]:
    """生成完整故障时间线数据供前端渲染。

    Args:
        evidence_data: evidence.json 解析结果
        snapshot_manifest: snapshot_manifest.json 列表（可选）
        window_minutes: 聚类窗口（分钟）

    Returns:
        {
            "timeline_events": [...每个事件的时间点],
            "fault_clusters": [...聚类后的故障簇],
            "metadata": {...统计信息},
        }
    """
    evidence = evidence_data.get("evidence", [])
    metadata = evidence_data.get("metadata", {})

    clusters = cluster_events(evidence, window_minutes=window_minutes)

    # 为每个故障簇关联快照
    if snapshot_manifest:
        for cluster in clusters:
            cluster["related_snapshots"] = find_related_snapshots(cluster, snapshot_manifest)
    else:
        for cluster in clusters:
            cluster["related_snapshots"] = []

    # 构建时间线事件（平铺所有证据时间点）
    timeline_events: list[dict] = []
    for ev in evidence:
        dt = _get_evidence_time(ev)
        if dt:
            timeline_events.append({
                "time": dt.isoformat(),
                "timestamp": int(dt.timestamp()),
                "severity": ev.get("severity", "info"),
                "category": ev.get("category", ""),
                "category_group": _get_evidence_category_group(ev.get("category", "")),
                "rule_id": ev.get("rule_id", ""),
                "description": ev.get("description", ""),
                "source_file": ev.get("source_file", ""),
            })

    # 按时间排序
    timeline_events.sort(key=lambda e: e["timestamp"])

    # 统计
    sev_total = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for ev in evidence:
        s = sev_total.get(ev.get("severity", "info"), "info")
        sev_total[s] = sev_total.get(s, 0) + 1

    return {
        "timeline_events": timeline_events,
        "fault_clusters": clusters,
        "metadata": {
            "total_evidence": metadata.get("total_evidence", 0),
            "files_analyzed": metadata.get("files_analyzed", 0),
            "clusters_found": len(clusters),
            "severity_summary": sev_total,
            "analyzed_at": metadata.get("analyzed_at", ""),
        },
    }


def load_evidence(evidence_path: str | Path) -> dict:
    """加载 evidence.json。"""
    path = Path(evidence_path)
    if not path.exists():
        logger.error("evidence.json 不存在: %s", path)
        return {"metadata": {}, "evidence": []}
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot_manifest(manifest_path: str | Path) -> list[dict]:
    """加载 snapshot_manifest.json。"""
    path = Path(manifest_path)
    if not path.exists():
        logger.warning("snapshot_manifest.json 不存在: %s", path)
        return []
    return json.loads(path.read_text(encoding="utf-8"))
