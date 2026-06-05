"""
awr_auto_analyzer.analyzer — AWR 规则引擎分析

基于结构化 AWR 摘要，通过预定义规则自动判断风险：
- AAS 负载分析
- CPU 型 / IO 型 / 等待型负载判别
- Top 等待事件集中度分析
- 关键等待事件阈值检查（log file sync, db file sequential read 等）
- Hard Parse / Execute to Parse 分析
- Top SQL 负载集中度分析
- RAC Global Cache 等待分析
- IO 吞吐分析（逻辑读、物理读、Redo 生成率）
- 命中率分析（Buffer Hit、Library Cache、Latch Hit、Soft Parse）
- SQL 分类分析（Top SQL by Gets / Reads、高频执行 SQL）
- Segment 热点分析（Row Lock Waits、ITL Waits）
"""

import json
from datetime import datetime
from pathlib import Path

from .config import AWR_RULE_FINDINGS_JSON, AWR_RULE_FINDINGS_MD, OUTPUT_DIR
from .parser import (
    AWR_SUMMARY_JSON,
    first_record,
    parse_duration_minutes,
    parse_number,
    parse_wait_ms,
    row_value,
)


# ── 指标查询辅助（供 analyzer 内部使用）──


def find_metric_row(records, metric_name: str) -> dict:
    """在记录列表中查找包含指标名的行。"""
    if not isinstance(records, list):
        return {}
    wanted = metric_name.lower()
    for row in records:
        values = [normalize_cell_lower(v) for v in row.values()]
        if any(wanted in v for v in values):
            return row
    return {}


def normalize_cell_lower(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\xa0", " ").lower().strip()


def metric_per_second(records, metric_name: str) -> float | None:
    """从 Load Profile 中获取 Per Second 指标值。"""
    row = find_metric_row(records, metric_name)
    return parse_number(row_value(row, ("Per Second",))) if row else None


def efficiency_value(records, metric_name: str) -> float | None:
    """从 Instance Efficiency 中获取指标值。"""
    if not isinstance(records, list):
        return None
    wanted = metric_name.lower()
    for row in records:
        items = list(row.values())
        for index, value in enumerate(items):
            if wanted in normalize_cell_lower(value):
                if index + 1 < len(items):
                    return parse_number(items[index + 1])
    return None


def event_row(records, event_name: str) -> dict:
    """从等待事件表中查找指定事件的记录。"""
    if not isinstance(records, list):
        return {}
    wanted = event_name.lower()
    for row in records:
        event = row_value(row, ("Event", "Wait Class"))
        if wanted in normalize_cell_lower(event):
            return row
    return {}


def event_percent_db_time(row: dict) -> float | None:
    """获取等待事件的 % DB Time。"""
    return parse_number(row_value(row, ("% DB time", "%DB time", "% of DB Time")))


# ── 规则条目 ──


def add_rule_finding(
    findings: list[dict],
    rule: str,
    level: str,
    finding: str,
    evidence: str,
    recommendation: str,
):
    findings.append(
        {
            "rule": rule,
            "level": level,
            "finding": finding,
            "evidence": evidence,
            "recommendation": recommendation,
        }
    )


# ── 规则引擎主逻辑 ──


def build_awr_rule_findings(summary: dict) -> dict:
    """
    对结构化 AWR 摘要执行规则引擎分析，返回结果。

    Args:
        summary: parse_awr_summary() 返回的结构化摘要

    Returns:
        包含 computed_metrics 和 findings 的字典
    """
    findings = []
    basic = summary.get("basic_info") or {}
    load_profile = summary.get("Load Profile")
    efficiency = summary.get("Instance Efficiency")
    waits = summary.get("Top Timed Events / Foreground Wait Events")
    sql_elapsed = summary.get("SQL ordered by Elapsed Time")
    sql_gets = summary.get("SQL ordered by Gets")
    sql_reads = summary.get("SQL ordered by Reads")
    sql_executions = summary.get("SQL ordered by Executions")
    segments_row_lock = summary.get("Segments by Row Lock Waits")
    segments_itl = summary.get("Segments by ITL Waits")

    elapsed_mins = parse_duration_minutes(basic.get("Elapsed Time"))
    db_time_mins = parse_duration_minutes(basic.get("DB Time"))
    cpus = parse_number(basic.get("CPUs"))
    aas = parse_number(basic.get("Average Active Sessions"))
    if aas is None and elapsed_mins and db_time_mins:
        aas = db_time_mins / elapsed_mins

    computed = {
        "Elapsed Time(mins)": f"{elapsed_mins:.2f}" if elapsed_mins is not None else "未识别",
        "DB Time(mins)": f"{db_time_mins:.2f}" if db_time_mins is not None else "未识别",
        "Average Active Sessions": f"{aas:.2f}" if aas is not None else "未识别",
        "CPUs": f"{cpus:.0f}" if cpus is not None else "未识别",
    }

    # ── 1. AAS 负载 ──
    if aas is not None and cpus:
        ratio = aas / cpus
        level = "高" if ratio >= 0.7 else "中" if ratio >= 0.3 else "低"
        add_rule_finding(
            findings,
            "AAS 负载",
            level,
            f"AAS/CPU={ratio:.2f}",
            f"DB Time={basic.get('DB Time')}，Elapsed={basic.get('Elapsed Time')}，CPUs={basic.get('CPUs')}",
            "结合业务峰值和 OS CPU 使用率确认是否存在容量压力。",
        )
    else:
        add_rule_finding(
            findings,
            "AAS 负载",
            "信息不足",
            "证据不足，不做强判断",
            "缺少 DB Time、Elapsed Time 或 CPUs",
            "补充完整 AWR 基本信息。",
        )

    # ── 2. CPU 型负载 ──
    db_time_s = metric_per_second(load_profile, "DB Time")
    db_cpu_s = metric_per_second(load_profile, "DB CPU")
    if db_time_s and db_cpu_s is not None:
        ratio = db_cpu_s / db_time_s
        computed["DB CPU / DB Time"] = f"{ratio:.2%}"
        if ratio > 0.7:
            add_rule_finding(
                findings,
                "CPU 型负载",
                "高",
                "DB CPU 占 DB Time 超过 70%",
                f"DB CPU(s)={db_cpu_s}，DB Time(s)={db_time_s}",
                "优先核查 CPU 消耗 Top SQL、执行计划和主机 CPU 饱和度。",
            )
        else:
            add_rule_finding(
                findings,
                "CPU 型负载",
                "低",
                "DB CPU 占比未超过 70%",
                f"DB CPU(s)={db_cpu_s}，DB Time(s)={db_time_s}",
                "CPU 不是唯一主导瓶颈，继续结合等待事件判断。",
            )
    else:
        add_rule_finding(
            findings,
            "CPU 型负载",
            "信息不足",
            "证据不足，不做强判断",
            "缺少 Load Profile 中 DB CPU(s) 或 DB Time(s)",
            "补充 Load Profile。",
        )

    # ── 3. Top 等待集中度 ──
    top_wait = first_record(waits if isinstance(waits, list) else [])
    top_wait_pct = event_percent_db_time(top_wait)
    if top_wait and top_wait_pct is not None:
        event = row_value(top_wait, ("Event",))
        if top_wait_pct > 40:
            add_rule_finding(
                findings,
                "Top 等待集中",
                "高",
                "Top 1 等待事件超过 DB Time 40%",
                f"{event}，%DB Time={top_wait_pct}",
                "优先围绕该等待事件做 SQL、对象和系统层取证。",
            )
        else:
            add_rule_finding(
                findings,
                "Top 等待集中",
                "低",
                "Top 1 等待事件未超过 DB Time 40%",
                f"{event}，%DB Time={top_wait_pct}",
                "等待分布相对分散，需综合 Top SQL 和资源画像判断。",
            )
    else:
        add_rule_finding(
            findings,
            "Top 等待集中",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Top Timed/Foreground Wait Events",
            "补充等待事件表。",
        )

    # ── 4. 关键等待事件阈值检查 ──
    wait_thresholds = [
        ("log file sync", 10, "提交延迟风险"),
        ("log file parallel write", 10, "日志写风险"),
        ("db file sequential read", 10, "单块读 I/O 风险"),
        ("db file scattered read", 20, "多块读 I/O 风险"),
        ("direct path read", 20, "直接路径读 I/O 风险"),
    ]
    for event_name, threshold, label in wait_thresholds:
        row = event_row(waits, event_name)
        avg_ms = parse_wait_ms(row_value(row, ("Avg wait", "Avg Wait", "Avg Wait Time"))) if row else None
        if avg_ms is None:
            add_rule_finding(
                findings,
                label,
                "信息不足",
                "证据不足，不做强判断",
                f"未识别 {event_name} 平均等待",
                "补充等待事件明细或直方图。",
            )
        elif avg_ms > threshold:
            add_rule_finding(
                findings,
                label,
                "中高",
                f"{event_name} 平均等待超过 {threshold}ms",
                f"Avg Wait={row_value(row, ('Avg wait', 'Avg Wait', 'Avg Wait Time'))}",
                "结合存储延迟、redo 写入、SQL 访问路径或 Direct Path 读来源继续取证。",
            )
        else:
            add_rule_finding(
                findings,
                label,
                "低",
                f"{event_name} 平均等待未超过阈值",
                f"Avg Wait={row_value(row, ('Avg wait', 'Avg Wait', 'Avg Wait Time'))}",
                "当前证据不支持该类等待为主要风险。",
            )

    # ── 5. Hard Parse ──
    hard_parse = metric_per_second(load_profile, "Hard parses")
    if hard_parse is None:
        add_rule_finding(
            findings,
            "Hard Parse",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Hard parses",
            "补充 Load Profile。",
        )
    elif hard_parse > 10:
        add_rule_finding(
            findings,
            "Hard Parse",
            "中",
            "Hard Parse 偏高",
            f"Hard parses/s={hard_parse}",
            "检查绑定变量、共享池压力、SQL 版本数和应用解析行为。",
        )
    else:
        add_rule_finding(
            findings,
            "Hard Parse",
            "低",
            "Hard Parse 未见明显偏高",
            f"Hard parses/s={hard_parse}",
            "持续观察解析峰值和 SQL 版本数。",
        )

    # ── 6. Execute to Parse ──
    execute_to_parse = efficiency_value(efficiency, "Execute to Parse")
    if execute_to_parse is None:
        add_rule_finding(
            findings,
            "Execute to Parse",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Execute to Parse %",
            "补充 Instance Efficiency。",
        )
    elif execute_to_parse < 70:
        add_rule_finding(
            findings,
            "Execute to Parse",
            "中",
            "Execute to Parse 偏低，游标复用不足",
            f"Execute to Parse %={execute_to_parse}",
            "检查会话缓存游标、应用短连接和 SQL 解析模式。",
        )
    else:
        add_rule_finding(
            findings,
            "Execute to Parse",
            "低",
            "Execute to Parse 未见明显偏低",
            f"Execute to Parse %={execute_to_parse}",
            "当前证据不支持游标复用为主要问题。",
        )

    # ── 7. Top SQL 负载集中度 ──
    top_sql = first_record(sql_elapsed if isinstance(sql_elapsed, list) else [])
    top_sql_pct = parse_number(row_value(top_sql, ("%Total", "% Total", "%DB Time")))
    if top_sql and top_sql_pct is not None:
        if top_sql_pct > 20:
            add_rule_finding(
                findings,
                "Top SQL 负载集中",
                "高",
                "单条 SQL 占 DB Time/Elapsed 总量超过 20%",
                f"SQL ID={row_value(top_sql, ('SQL Id', 'SQL ID'))}，%Total={top_sql_pct}",
                "优先获取执行计划、绑定变量、对象统计信息并评估 SQL 改写。",
            )
        else:
            add_rule_finding(
                findings,
                "Top SQL 负载集中",
                "低",
                "Top SQL 占比未超过 20%",
                f"SQL ID={row_value(top_sql, ('SQL Id', 'SQL ID'))}，%Total={top_sql_pct}",
                "SQL 负载相对分散，继续按类别分析。",
            )
    else:
        add_rule_finding(
            findings,
            "Top SQL 负载集中",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 SQL ordered by Elapsed Time 或 %Total",
            "补充 Top SQL 表。",
        )

    # ── 8. RAC Global Cache ──
    if isinstance(waits, list):
        rac_rows = []
        for row in waits:
            for value in row.values():
                if "gc " in normalize_cell_lower(value):
                    rac_rows.append(row)
                    break
        rac_pct = max((event_percent_db_time(row) or 0 for row in rac_rows), default=0)
    else:
        rac_rows = []
        rac_pct = 0

    if rac_pct > 10:
        add_rule_finding(
            findings,
            "RAC Global Cache",
            "中高",
            "RAC gc 等待占比较高",
            f"最高 gc 等待 %DB Time={rac_pct}",
            "检查跨实例访问、热点块、服务部署亲和性和对象分区策略。",
        )
    elif rac_rows:
        add_rule_finding(
            findings,
            "RAC Global Cache",
            "低",
            "识别到 gc 等待但占比不高",
            f"最高 gc 等待 %DB Time={rac_pct}",
            "保留为观察项。",
        )
    else:
        add_rule_finding(
            findings,
            "RAC Global Cache",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 RAC gc 等待",
            "如果为 RAC 环境，补充 Global Cache 章节。",
        )

    # ════════════════════════════════════════════════════
    # A 组 — IO 吞吐分析（逻辑读 / 物理读 / Redo 生成率）
    # ════════════════════════════════════════════════════

    # ── 9. 逻辑读吞吐 ──
    logical_reads_s = metric_per_second(load_profile, "Logical reads")
    if logical_reads_s is None:
        add_rule_finding(
            findings,
            "逻辑读吞吐",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Logical reads/s",
            "补充 Load Profile。",
        )
    elif logical_reads_s >= 500000:
        computed["Logical reads/s"] = f"{logical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "逻辑读吞吐",
            "高",
            "逻辑读吞吐量偏高",
            f"Logical reads/s={logical_reads_s:.0f}（≥500K/s）",
            "结合 Top SQL by Gets 确认逻辑读消耗来源，优化 SQL 访问路径和索引使用。",
        )
    elif logical_reads_s >= 100000:
        computed["Logical reads/s"] = f"{logical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "逻辑读吞吐",
            "中",
            "逻辑读吞吐量中等",
            f"Logical reads/s={logical_reads_s:.0f}（100K~500K/s）",
            "关注 Top SQL 变化趋势，定期审查执行计划。",
        )
    else:
        computed["Logical reads/s"] = f"{logical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "逻辑读吞吐",
            "低",
            "逻辑读吞吐量正常",
            f"Logical reads/s={logical_reads_s:.0f}",
            "当前逻辑读负载在合理范围内。",
        )

    # ── 10. 物理读吞吐 ──
    physical_reads_s = metric_per_second(load_profile, "Physical reads")
    if physical_reads_s is None:
        add_rule_finding(
            findings,
            "物理读吞吐",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Physical reads/s",
            "补充 Load Profile。",
        )
    elif physical_reads_s >= 50000:
        computed["Physical reads/s"] = f"{physical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "物理读吞吐",
            "高",
            "物理读吞吐量偏高",
            f"Physical reads/s={physical_reads_s:.0f}（≥50K/s）",
            "检查 I/O 子系统和 Top SQL by Reads，确认是否需要增大 Buffer Cache 或优化 SQL 减少物理 I/O。",
        )
    elif physical_reads_s >= 10000:
        computed["Physical reads/s"] = f"{physical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "物理读吞吐",
            "中",
            "物理读吞吐量中等",
            f"Physical reads/s={physical_reads_s:.0f}（10K~50K/s）",
            "结合 Buffer Hit % 和 Top SQL 持续观察，评估 I/O 容量。",
        )
    else:
        computed["Physical reads/s"] = f"{physical_reads_s:.0f}"
        add_rule_finding(
            findings,
            "物理读吞吐",
            "低",
            "物理读吞吐量正常",
            f"Physical reads/s={physical_reads_s:.0f}",
            "当前物理读负载在合理范围内。",
        )

    # ── 11. Redo 生成率 ──
    redo_size_s = metric_per_second(load_profile, "Redo size")
    if redo_size_s is None:
        add_rule_finding(
            findings,
            "Redo 生成率",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Redo size/s",
            "补充 Load Profile。",
        )
    elif redo_size_s >= 5_000_000:
        computed["Redo size/s"] = f"{redo_size_s:.0f} ({(redo_size_s / 1024 / 1024):.1f}MB)"
        add_rule_finding(
            findings,
            "Redo 生成率",
            "高",
            "Redo 生成率偏高",
            f"Redo size/s={redo_size_s:.0f}（{(redo_size_s / 1024 / 1024):.1f}MB/s，≥5MB/s）",
            "检查是否有大批量 DML 操作（大量 INSERT/UPDATE/DELETE），评估归档日志空间和 Data Guard 带宽。",
        )
    elif redo_size_s >= 1_000_000:
        computed["Redo size/s"] = f"{redo_size_s:.0f} ({(redo_size_s / 1024 / 1024):.1f}MB)"
        add_rule_finding(
            findings,
            "Redo 生成率",
            "中",
            "Redo 生成率中等偏高",
            f"Redo size/s={redo_size_s:.0f}（{(redo_size_s / 1024 / 1024):.1f}MB/s，1~5MB/s）",
            "关注日志切换频率和归档能力，排除潜在的压力源。",
        )
    else:
        computed["Redo size/s"] = f"{redo_size_s:.0f} ({(redo_size_s / 1024 / 1024):.1f}MB)"
        add_rule_finding(
            findings,
            "Redo 生成率",
            "低",
            "Redo 生成率正常",
            f"Redo size/s={redo_size_s:.0f}（{(redo_size_s / 1024 / 1024):.1f}MB/s）",
            "当前 Redo 负载在合理范围内。",
        )

    # ════════════════════════════════════════════════════
    # B 组 — 命中率分析
    # ════════════════════════════════════════════════════

    # ── 12. Buffer Hit 命中率 ──
    buffer_hit = efficiency_value(efficiency, "Buffer Hit")
    if buffer_hit is None:
        add_rule_finding(
            findings,
            "Buffer Hit 命中率",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Buffer Hit %",
            "补充 Instance Efficiency。",
        )
    elif buffer_hit < 90:
        computed["Buffer Hit %"] = f"{buffer_hit:.1f}"
        add_rule_finding(
            findings,
            "Buffer Hit 命中率",
            "高",
            "Buffer Hit 命中率偏低",
            f"Buffer Hit %={buffer_hit:.1f}（<90%）",
            "检查 Buffer Cache 大小、Top SQL 逻辑读分布和 DB Cache Advisory。",
        )
    elif buffer_hit < 95:
        computed["Buffer Hit %"] = f"{buffer_hit:.1f}"
        add_rule_finding(
            findings,
            "Buffer Hit 命中率",
            "中",
            "Buffer Hit 命中率中等",
            f"Buffer Hit %={buffer_hit:.1f}（90%~95%）",
            "关注物理读趋势，评估是否需要扩容 Buffer Cache。",
        )
    else:
        computed["Buffer Hit %"] = f"{buffer_hit:.1f}"
        add_rule_finding(
            findings,
            "Buffer Hit 命中率",
            "低",
            "Buffer Hit 命中率良好",
            f"Buffer Hit %={buffer_hit:.1f}",
            "Buffer Cache 命中率处于健康范围。",
        )

    # ── 13. Library Cache 命中率 ──
    library_hit = efficiency_value(efficiency, "Library Hit")
    if library_hit is None:
        add_rule_finding(
            findings,
            "Library Cache 命中率",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Library Hit %",
            "补充 Instance Efficiency。",
        )
    elif library_hit < 95:
        computed["Library Hit %"] = f"{library_hit:.1f}"
        add_rule_finding(
            findings,
            "Library Cache 命中率",
            "高",
            "Library Cache 命中率偏低",
            f"Library Hit %={library_hit:.1f}（<95%）",
            "检查共享池大小、解析压力和 SQL 版本数。",
        )
    elif library_hit < 98:
        computed["Library Hit %"] = f"{library_hit:.1f}"
        add_rule_finding(
            findings,
            "Library Cache 命中率",
            "中",
            "Library Cache 命中率中等",
            f"Library Hit %={library_hit:.1f}（95%~98%）",
            "关注解析行为和应用连接池复用情况。",
        )
    else:
        computed["Library Hit %"] = f"{library_hit:.1f}"
        add_rule_finding(
            findings,
            "Library Cache 命中率",
            "低",
            "Library Cache 命中率良好",
            f"Library Hit %={library_hit:.1f}",
            "Library Cache 命中率处于健康范围。",
        )

    # ── 14. Latch Hit 命中率 ──
    latch_hit = efficiency_value(efficiency, "Latch Hit")
    if latch_hit is None:
        add_rule_finding(
            findings,
            "Latch Hit 命中率",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Latch Hit %",
            "补充 Instance Efficiency。",
        )
    elif latch_hit < 98:
        computed["Latch Hit %"] = f"{latch_hit:.2f}"
        add_rule_finding(
            findings,
            "Latch Hit 命中率",
            "高",
            "Latch Hit 命中率偏低",
            f"Latch Hit %={latch_hit:.2f}（<98%）",
            "检查 Latch 争用涉及的子类（如 shared pool、library cache 等），分析 Top SQL 热点。",
        )
    elif latch_hit < 99:
        computed["Latch Hit %"] = f"{latch_hit:.2f}"
        add_rule_finding(
            findings,
            "Latch Hit 命中率",
            "中",
            "Latch Hit 命中率中等",
            f"Latch Hit %={latch_hit:.2f}（98%~99%）",
            "持续观察等待事件中 latch 相关的活动。",
        )
    else:
        computed["Latch Hit %"] = f"{latch_hit:.2f}"
        add_rule_finding(
            findings,
            "Latch Hit 命中率",
            "低",
            "Latch Hit 命中率良好",
            f"Latch Hit %={latch_hit:.2f}",
            "Latch 命中率处于健康范围。",
        )

    # ── 15. Soft Parse 比例 ──
    soft_parse = efficiency_value(efficiency, "Soft Parse")
    if soft_parse is None:
        add_rule_finding(
            findings,
            "Soft Parse 比例",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 Soft Parse %",
            "补充 Instance Efficiency。",
        )
    elif soft_parse < 95:
        computed["Soft Parse %"] = f"{soft_parse:.1f}"
        add_rule_finding(
            findings,
            "Soft Parse 比例",
            "高",
            "Soft Parse 比例偏低，硬解析占比高",
            f"Soft Parse %={soft_parse:.1f}（<95%）",
            "检查应用是否缺少绑定变量、SQL 是否大量拼接，以及共享池参数设置。",
        )
    elif soft_parse < 99:
        computed["Soft Parse %"] = f"{soft_parse:.1f}"
        add_rule_finding(
            findings,
            "Soft Parse 比例",
            "中",
            "Soft Parse 比例中等，硬解析占比可见",
            f"Soft Parse %={soft_parse:.1f}（95%~99%）",
            "关注 Hard Parse 数量和 SQL 解析类型分布。",
        )
    else:
        computed["Soft Parse %"] = f"{soft_parse:.1f}"
        add_rule_finding(
            findings,
            "Soft Parse 比例",
            "低",
            "Soft Parse 比例良好",
            f"Soft Parse %={soft_parse:.1f}",
            "软解析比例处于健康范围。",
        )

    # ════════════════════════════════════════════════════
    # C 组 — SQL 分类分析
    # ════════════════════════════════════════════════════

    # ── 16. Top SQL by Gets（Buffer Gets 偏高） ──
    top_gets = first_record(sql_gets if isinstance(sql_gets, list) else [])
    gets_value = parse_number(row_value(top_gets, ("Buffer Gets", "Buffer Gets/Exec", "Buffer Gets per Exec")))
    if top_gets and gets_value is not None:
        gets_sql_id = row_value(top_gets, ("SQL Id", "SQL ID", "SQL ID"))
        if gets_value > 5000:
            add_rule_finding(
                findings,
                "Top SQL by Gets",
                "高",
                "Top SQL by Gets Buffer Gets 偏高",
                f"SQL ID={gets_sql_id}，Buffer Gets={gets_value}（>5000）",
                "审查该 SQL 执行计划是否全表扫描或者索引使用不当，优化索引或 SQL 改写。",
            )
        else:
            add_rule_finding(
                findings,
                "Top SQL by Gets",
                "低",
                "Top SQL by Gets 未见异常",
                f"SQL ID={gets_sql_id}，Buffer Gets={gets_value}",
                "当前 Top SQL by Gets 处于合理范围。",
            )
    else:
        add_rule_finding(
            findings,
            "Top SQL by Gets",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 SQL ordered by Gets",
            "补充 SQL ordered by Gets 章节。",
        )

    # ── 17. Top SQL by Reads（物理读偏高） ──
    top_reads = first_record(sql_reads if isinstance(sql_reads, list) else [])
    reads_value = parse_number(row_value(top_reads, ("Physical Reads", "Physical Reads/Exec", "Physical Reads per Exec")))
    if top_reads and reads_value is not None:
        reads_sql_id = row_value(top_reads, ("SQL Id", "SQL ID"))
        if reads_value > 1000:
            add_rule_finding(
                findings,
                "Top SQL by Reads",
                "高",
                "Top SQL by Reads 物理读偏高",
                f"SQL ID={reads_sql_id}，Physical Reads={reads_value}（>1000）",
                "检查该 SQL 的访问路径、对象统计信息，评估 Hint 或物化视图等方式减少物理 I/O。",
            )
        else:
            add_rule_finding(
                findings,
                "Top SQL by Reads",
                "低",
                "Top SQL by Reads 未见异常",
                f"SQL ID={reads_sql_id}，Physical Reads={reads_value}",
                "当前 Top SQL by Reads 处于合理范围。",
            )
    else:
        add_rule_finding(
            findings,
            "Top SQL by Reads",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 SQL ordered by Reads",
            "补充 SQL ordered by Reads 章节。",
        )

    # ── 18. 高频执行 SQL ──
    top_exec = first_record(sql_executions if isinstance(sql_executions, list) else [])
    exec_value = parse_number(row_value(top_exec, ("Executions", "Execs")))
    if top_exec and exec_value is not None:
        exec_sql_id = row_value(top_exec, ("SQL Id", "SQL ID"))
        if exec_value > 100000:
            add_rule_finding(
                findings,
                "高频执行 SQL",
                "高",
                "单条 SQL 执行频率非常高",
                f"SQL ID={exec_sql_id}，Executions={exec_value}（>100K）",
                "评估该 SQL 的每次执行效率（逻辑读/执行、I/O 等），确认是否需要批量处理或改进缓存。",
            )
        elif exec_value > 50000:
            add_rule_finding(
                findings,
                "高频执行 SQL",
                "中",
                "单条 SQL 执行频率较高",
                f"SQL ID={exec_sql_id}，Executions={exec_value}（50K~100K）",
                "关注该 SQL 消耗趋势，评估应用是否有优化空间。",
            )
        else:
            add_rule_finding(
                findings,
                "高频执行 SQL",
                "低",
                "SQL 执行频率未超过观察阈值",
                f"SQL ID={exec_sql_id}，Executions={exec_value}",
                "当前执行频率处于合理范围。",
            )
    else:
        add_rule_finding(
            findings,
            "高频执行 SQL",
            "信息不足",
            "证据不足，不做强判断",
            "未识别 SQL ordered by Executions",
            "补充 SQL ordered by Executions 章节。",
        )

    # ════════════════════════════════════════════════════
    # D 组 — Segment 热点分析
    # ════════════════════════════════════════════════════

    # ── 19. 热点段争用（Row Lock Waits） ──
    top_row_lock = first_record(segments_row_lock if isinstance(segments_row_lock, list) else [])
    if top_row_lock:
        lock_waits = parse_number(row_value(top_row_lock, ("Row Lock Waits", "Row Lock")))
        lock_object = row_value(top_row_lock, ("Object Name",))
        if lock_waits is not None and lock_waits > 0:
            add_rule_finding(
                findings,
                "热点段争用",
                "高",
                f"段级别 Row Lock Waits 存在争用",
                f"Object={lock_object}，Row Lock Waits={lock_waits}",
                "检查该段上是否存在大量并发 DML 导致的锁争用，评估分区、并发控制或应用逻辑改造方案。",
            )
        else:
            add_rule_finding(
                findings,
                "热点段争用",
                "信息不足",
                "识别到 Row Lock Waits 段记录但无具体等待数",
                f"Object={lock_object}，Row Lock Waits={lock_waits}",
                "补充段级等待详情。",
            )
    else:
        add_rule_finding(
            findings,
            "热点段争用",
            "低",
            "未识别到段级别 Row Lock 争用",
            "Segments by Row Lock Waits 为空",
            "当前段级锁争用不突出，可作为基线参考。",
        )

    # ── 20. ITL 等待（ITL Waits） ──
    top_itl = first_record(segments_itl if isinstance(segments_itl, list) else [])
    if top_itl:
        itl_waits = parse_number(row_value(top_itl, ("ITL Waits", "ITL Wait")))
        itl_object = row_value(top_itl, ("Object Name",))
        if itl_waits is not None and itl_waits > 0:
            add_rule_finding(
                findings,
                "ITL 等待",
                "中高",
                f"段级别 ITL Waits 存在争用",
                f"Object={itl_object}，ITL Waits={itl_waits}",
                "检查该对象的 INITRANS、PCTFREE 设置，考虑增大 INITRANS 或减小数据块大小以减少 ITL 争用。",
            )
        else:
            add_rule_finding(
                findings,
                "ITL 等待",
                "信息不足",
                "识别到 ITL Waits 段记录但无具体等待数",
                f"Object={itl_object}，ITL Waits={itl_waits}",
                "补充段级等待详情。",
            )
    else:
        add_rule_finding(
            findings,
            "ITL 等待",
            "低",
            "未识别到段级别 ITL 争用",
            "Segments by ITL Waits 为空",
            "当前 ITL 争用不突出，可作为基线参考。",
        )

    return {
        "source_file": summary.get("source_file"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "computed_metrics": computed,
        "findings": findings,
    }


def render_rule_findings_markdown(result: dict) -> str:
    """渲染规则引擎结果为详细的 Markdown 段落（供 DeepSeek 分析和 Word 附录使用）。

    每条规则单独展开为结构化段落，包含：规则编号、风险等级（带图标）、
    判断依据、详细证据数值、优化建议，以及关联的 AWR 数据章节。
    """
    lines = [
        "# Oracle AWR 规则引擎发现",
        "",
        f"- **源文件**：`{result.get('source_file')}`",
        f"- **生成时间**：{result.get('generated_at')}",
        "",
    ]

    # ── 规则统计概要 ──
    findings = result.get("findings", [])
    computed = result.get("computed_metrics", {})
    high_count = sum(1 for f in findings if f.get("level") == "高")
    mid_high_count = sum(1 for f in findings if f.get("level") == "中高")
    mid_count = sum(1 for f in findings if f.get("level") == "中")
    low_count = sum(1 for f in findings if f.get("level") == "低")
    info_missing = sum(1 for f in findings if f.get("level") == "信息不足")
    lines.extend(
        [
            "---",
            "",
            "### 📊 规则引擎概要",
            "",
            f"- **总计触发规则**：{len(findings)} 条",
            f"- 🟥 **高风险**：{high_count} 条",
            f"- 🟧 **中高风险**：{mid_high_count} 条",
            f"- 🟨 **中风险**：{mid_count} 条",
            f"- 🟩 **低风险（正常）**：{low_count} 条",
            f"- ⚪ **信息不足**：{info_missing} 条",
            "",
        ]
    )

    # ── 关键计算指标 ──
    if computed:
        lines.extend(
            [
                "---",
                "",
                "### 📐 关键计算指标",
                "",
            ]
        )
        for key, value in computed.items():
            lines.append(f"- **{key}**：{value}")
        lines.append("")

    # ── 规则详情（逐条展开）──
    if findings:
        lines.extend(
            [
                "---",
                "",
                "### 📋 规则判断详情",
                "",
                "以下按严重等级从高到低排列，每条规则包含完整判断依据和数据引用。",
                "",
            ]
        )

        # 等级排序：高 > 中高 > 中 > 低 > 信息不足
        level_order = {"高": 0, "中高": 1, "中": 2, "低": 3, "信息不足": 4}
        level_icons = {"高": "🟥", "中高": "🟧", "中": "🟨", "低": "🟩", "信息不足": "⚪"}
        sorted_findings = sorted(findings, key=lambda f: level_order.get(f.get("level", "信息不足"), 99))

        for idx, item in enumerate(sorted_findings, 1):
            rule = item.get("rule", "")
            level = item.get("level", "")
            finding = item.get("finding", "")
            evidence = item.get("evidence", "")
            recommendation = item.get("recommendation", "")
            icon = level_icons.get(level, "⚪")

            lines.extend(
                [
                    f"#### R{idx} {rule} | {icon} {level}",
                    "",
                    f"| 字段 | 内容 |",
                    f"| --- | --- |",
                    f"| **判断依据** | {finding} |",
                    f"| **详细证据** | {evidence} |",
                    f"| **优化建议** | {recommendation} |",
                    "",
                ]
            )

    lines.append("")
    return "\n".join(lines)


def write_awr_rule_findings(summary: dict) -> dict:
    """执行规则引擎并写出结果文件。"""
    result = build_awr_rule_findings(summary)
    md_path = AWR_RULE_FINDINGS_MD
    json_path = AWR_RULE_FINDINGS_JSON
    md_path.write_text(render_rule_findings_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["markdown_path"] = str(md_path)
    result["json_path"] = str(json_path)
    return result
