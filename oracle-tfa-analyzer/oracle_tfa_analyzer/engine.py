"""核心分析引擎。"""

import json
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable
from .config import ANALYSIS_CATEGORIES, OUTPUT_DIR
from .extractor import discover_files
from .rules.registry import get_all_rules

logger = logging.getLogger(__name__)

# 常见日志行首的时间戳格式（按优先级排列）
_TIMESTAMP_PATTERNS = [
    # ISO 8601: 2022-07-26T10:30:00.665345+08:00 或 2022-07-26T<IP>.665345+08:00
    re.compile(r"^(\d{4}-\d{2}-\d{2})T\S+"),
    # ISO 无毫秒: 2022-07-26 10:30:00
    re.compile(r"^(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}"),
    # ISO 短: 2022-07-26
    re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s|$)"),
    # DD-MON-YYYY: 25-APR-2026 <IP> * (CONNECT_DATA=...
    re.compile(r"^(\d{2}-[A-Z]{3}-\d{4})\s"),
    # yyyy/mm/dd: 2026/04/25 <IP> CST : Scanning...
    re.compile(r"^(\d{4}/\d{2}/\d{2})\s"),
    # Trace 文件 *** 标记行: *** MODULE NAME:xxx 2026-04-15T...
    re.compile(r"^\*\*\* .*?(\d{4}-\d{2}-\d{2})T"),
    # Oracle alert log 旧版: Fri Aug 19 <IP> 2022
    re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\S+\s+\S+\s+(\d{4})"),
    # TFA 收集日志: Sat Apr 25 <IP> 2026
    re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\S+\s+(\d{4})"),
    # CRS 日志: 2022-07-26 <IP>.718
    re.compile(r"^(\d{4}-\d{2}-\d{2})\s+\S+"),
]

_MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _extract_date_from_line(line: str) -> str | None:
    """尝试从行首提取日期字符串 yyyy-mm-dd，失败返回 None。"""
    for pat in _TIMESTAMP_PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        # DD-MON-YYYY 格式 (m.lastindex == 1 且值包含 - 且长度为 11)
        if m.lastindex == 1:
            raw = m.group(1)
            if len(raw) == 11 and raw[2] == "-" and raw[6] == "-":
                # DD-MON-YYYY → 转换
                converted = _convert_named_month_date(raw)
                if converted:
                    return converted
            if len(raw) == 10 and raw[4] == "/":
                # yyyy/mm/dd → 转换
                converted = _convert_slash_date(raw)
                if converted:
                    return converted
            return raw  # ISO: yyyy-mm-dd
        # Oracle alert 风格: "Fri Aug 19 <IP> 2022" → 捕获了月份和年份
        if m.lastindex >= 2:
            month_str = m.group(2)
            year_str = m.group(m.lastindex)
            month = _MONTH_MAP.get(month_str)
            if month:
                return f"{year_str}-{month:02d}-01"
    return None


def _convert_named_month_date(date_str: str) -> str | None:
    """将 DD-MON-YYYY 转换为 yyyy-mm-dd，如 25-APR-2026 → 2026-04-25"""
    if not date_str or len(date_str) != 11:
        return None
    try:
        day = int(date_str[:2])
        month = _MONTH_MAP.get(date_str[3:6].capitalize())
        year = int(date_str[7:11])
        if month and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        pass
    return None


def _convert_slash_date(date_str: str) -> str | None:
    """将 yyyy/mm/dd 转换为 yyyy-mm-dd，如 2026/04/25 → 2026-04-25"""
    if not date_str or len(date_str) != 10:
        return None
    try:
        parts = date_str.split("/")
        if len(parts) == 3:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            if len(parts[0]) == 4 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
    except (ValueError, IndexError):
        pass
    return None


def _line_is_within_range(line: str, cutoff_date: datetime | None, date_start: datetime | None = None, date_end: datetime | None = None) -> bool:
    """
    判断日志行是否在时间范围内。
    - 如果所有日期参数为 None，返回 True（不过滤）
    - 能提取到日期且:
      - 在 date_start~date_end 之间（自定义模式）→ True
      - 早于 cutoff_date（天数模式）→ False（跳过）
    - 提取不到日期 → True（保留，兼容无时间戳的日志）
    """
    if cutoff_date is None and date_start is None and date_end is None:
        return True
    date_str = _extract_date_from_line(line)
    if date_str is None:
        return True  # 无法判断时间，保留
    try:
        line_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return True

    # 自定义起止日期模式
    if date_start is not None and date_end is not None:
        return date_start <= line_date <= date_end
    # 天数模式（最近 N 天）
    if cutoff_date is not None:
        return line_date >= cutoff_date
    return True


def _filter_lines_by_time(content: str, cutoff_date: datetime | None, date_start: datetime | None = None, date_end: datetime | None = None) -> str:
    """按时间范围过滤日志行，跳过早于 cutoff_date 的行。
    
    对于没有时间戳的行，继承该文件中最近找到的时间戳。
    第一个带日期行之前出现的无日期行（如 trace 文件头部元信息）直接丢弃。
    """
    if cutoff_date is None and date_start is None and date_end is None:
        return content
    filtered_lines = []
    last_valid_date = None  # 继承最近找到的日期
    found_first_date = False  # 是否已遇到第一个带日期的行
    
    for line in content.splitlines():
        date_str = _extract_date_from_line(line)
        if date_str:
            found_first_date = True
            try:
                last_valid_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, OverflowError):
                pass
        
        # 在遇到第一个带日期行之前，无日期行直接丢弃
        if not found_first_date:
            continue
        
        line_date = last_valid_date
        if line_date is None:
            filtered_lines.append(line)
            continue
        
        # 自定义起止日期模式
        if date_start is not None and date_end is not None:
            if date_start <= line_date <= date_end:
                filtered_lines.append(line)
        # 天数模式（最近 N 天）
        elif cutoff_date is not None:
            if line_date >= cutoff_date:
                filtered_lines.append(line)
        else:
            filtered_lines.append(line)
    return "\n".join(filtered_lines)


def analyze(
    extract_dir: Path,
    output_dir: str | Path | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
    time_filter_days: int | None = None,
    time_start: str | None = None,
    time_end: str | None = None,
    first_match_only: bool = False,
) -> dict[str, Any]:
    """
    核心分析：
    1. 发现文件
    2. 每条文件逐条规则匹配
    3. 汇总 evidence.json

    Args:
        extract_dir: 解压后的 TFA 目录
        output_dir: 输出目录
        progress_callback: 进度回调
        time_filter_days: 时间过滤天数（如 1 表示只分析当天的数据）
        time_start: 自定义起始日期 yyyy-mm-dd（优先级高于 time_filter_days）
        time_end: 自定义截止日期 yyyy-mm-dd
        first_match_only: 如果为 True，找到第一条证据后立即停止分析（用于"不限时间"模式）
    """
    # 计算截止日期
    cutoff_date = None
    custom_date_start = None
    custom_date_end = None

    if time_start and time_end:
        try:
            custom_date_start = datetime.strptime(time_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            custom_date_end = datetime.strptime(time_end, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError as e:
            logger.warning("自定义日期格式无效: %s", e)
    elif time_filter_days is not None and time_filter_days > 0:
        cutoff_date = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        from datetime import timedelta
        cutoff_date -= timedelta(days=time_filter_days - 1)

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    discovered = discover_files(extract_dir)
    total_categories = sum(len(files) for files in discovered.values())
    processed = 0

    if progress_callback:
        progress_callback("扫描文件", 0, total_categories)

    all_rules = get_all_rules()
    all_evidence: list[dict] = []
    files_analyzed = 0
    total_lines_before = 0
    total_lines_after = 0

    _found_first = False

    for cat, files in discovered.items():
        if _found_first:
            break
        for fpath in files:
            if not fpath.is_file():
                continue
            rel_path = str(fpath.relative_to(extract_dir))
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = fpath.read_text(encoding="latin-1", errors="replace")

            file_lines = content.count("\n") + 1
            total_lines_before += file_lines

            # 时间过滤
            filtered_content = _filter_lines_by_time(content, cutoff_date, custom_date_start, custom_date_end)
            filtered_lines = filtered_content.count("\n") + 1 if filtered_content else 0
            total_lines_after += filtered_lines

            # 如果过滤后为空，跳过后续分析
            if not filtered_content.strip():
                files_analyzed += 1
                processed += 1
                if progress_callback:
                    progress_callback(f"跳过(无有效时间): {rel_path}", processed, total_categories)
                continue

            files_analyzed += 1
            processed += 1

            if progress_callback:
                progress_callback(f"分析: {rel_path} ({file_lines}行→{filtered_lines}行)", processed, total_categories)

            for rule in all_rules:
                try:
                    result = rule.match(rel_path, filtered_content)
                    if result.matched:
                        for ev in result.evidence:
                            d = ev.to_dict()
                            # 从 log_snippet 第一行提取证据发现时间
                            snippet_first_line = (ev.log_snippet or "").split("\n")[0].strip()
                            date_found = _extract_date_from_line(snippet_first_line)
                            if date_found:
                                d["discovered_at"] = date_found
                            elif ev.line_number > 0:
                                # 尝试从对应行号提取日期
                                lines = filtered_content.splitlines()
                                if ev.line_number - 1 < len(lines):
                                    date_found = _extract_date_from_line(lines[ev.line_number - 1])
                                    if date_found:
                                        d["discovered_at"] = date_found
                            if "discovered_at" not in d:
                                d["discovered_at"] = None
                            all_evidence.append(d)
                            if first_match_only:
                                _found_first = True
                                break
                    if _found_first:
                        break
                except Exception as e:
                    logger.warning("规则 %s 分析 %s 时出错: %s", rule.rule_id, rel_path, e)
            if _found_first:
                break

    if progress_callback:
        progress_callback("汇总结果", total_categories, total_categories)

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
            "time_filter_days": time_filter_days,
            "time_filter_cutoff": cutoff_date.isoformat() if cutoff_date else None,
            "time_start": time_start,
            "time_end": time_end,
            "total_lines_before_filter": total_lines_before,
            "total_lines_after_filter": total_lines_after,
        },
        "risk_summary": risk_counts,
        "by_category": by_category,
        "evidence": all_evidence,
    }

    evidence_path = out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if progress_callback:
        progress_callback("完成", total_categories, total_categories)

    logger.info("evidence.json 已写入 %s（共 %d 条证据）", evidence_path, len(all_evidence))
    if cutoff_date:
        logger.info(
            "时间过滤: >= %s, 行数 %d → %d (%.1f%%)",
            cutoff_date.date(),
            total_lines_before,
            total_lines_after,
            total_lines_after / total_lines_before * 100 if total_lines_before else 0,
        )
    return evidence_data
