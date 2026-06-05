"""
awr_auto_analyzer.parser — AWR 报告解析引擎

解析 HTML 格式的 Oracle AWR 报告，提取结构化数据：
- 基本信息（DB Name, Instance, Host 等）
- Load Profile, Host CPU, Instance Efficiency
- Top Timed Events / Foreground Wait Events
- SQL ordered by Elapsed Time / CPU Time / Gets / Reads / Executions / Parse Calls
- Segments by Logical Reads / Physical Reads / Row Lock Waits / ITL Waits
- Buffer Cache Advisory, PGA Advisory, Shared Pool Advisory, SGA Target Advisory
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import AWR_SUMMARY_JSON, AWR_SUMMARY_MD, DATA_DIR, OUTPUT_DIR

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    BeautifulSoup = None
    HAS_BS4 = False


# ── HTML / 文本工具 ──


def html_to_text(raw: str) -> str:
    """将 HTML 转为纯文本，保留表格/段落结构。"""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)</(?:tr|p|div|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    from html import unescape

    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_report_text(path: Path) -> str:
    """读取报告文件内容（支持 UTF-8/GB18030/Latin-1）。"""
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_cell(value) -> str:
    """标准化表格单元格内容。"""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


# ── 表格解析工具 ──


def fallback_read_html_tables(html: str) -> list:
    """不使用 pandas.read_html 的 HTML 表格解析回退方案。"""
    frames = []
    position = 0
    for match in re.finditer(r"(?is)<table[^>]*>(.*?)</table>", html):
        prefix = html[position : match.start()]
        context_prefix = html[max(0, match.start() - 1600) : match.start()]
        summary_match = re.search(r'(?is)\bsummary=["\']([^"\']+)["\']', match.group(0))
        summary_text = normalize_cell(summary_match.group(1)) if summary_match else ""
        heading_matches = re.findall(r"(?is)<h[1-6][^>]*>(.*?)</h[1-6]>", prefix)
        section = normalize_cell(html_to_text(heading_matches[-1])) if heading_matches else ""
        if not section:
            context = re.sub(r"(?is)<table[^>]*>.*?</table>", " ", context_prefix)
            context = re.sub(r"(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", " ", context)
            context_text = html_to_text(context)
            candidates = [normalize_cell(item) for item in context_text.splitlines()]
            candidates = [item for item in candidates if 2 <= len(item) <= 120]
            section = candidates[-1] if candidates else ""
        if summary_text and summary_text.lower() not in section.lower():
            section = normalize_cell(f"{section} {summary_text}")
        rows = []
        has_header = False
        for row_html in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", match.group(1)):
            has_header = has_header or bool(re.search(r"(?is)<th\b", row_html))
            cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", row_html)
            values = [normalize_cell(html_to_text(cell)) for cell in cells]
            if values:
                rows.append(values)
        if rows:
            width = max(len(row) for row in rows)
            normalized_rows = [row + [""] * (width - len(row)) for row in rows]
            headers = normalized_rows[0] if has_header else [f"col_{idx + 1}" for idx in range(width)]
            data = normalized_rows[1:] if has_header and len(normalized_rows) > 1 else normalized_rows
            columns = [header or f"col_{idx + 1}" for idx, header in enumerate(headers)]
            frame = pd.DataFrame(data, columns=columns)
            if section:
                frame.insert(0, "_section", section)
            frames.append(frame)
        position = match.end()
    return frames


def read_html_tables(path: Path) -> list:
    """读取 HTML AWR 报告中的所有表格。"""
    html = read_report_text(path)
    try:
        pd_tables = pd.read_html(str(path))
        for frame in pd_tables:
            if not frame.empty:
                frame = frame.dropna(how="all").dropna(axis=1, how="all")
                frame.columns = [normalize_cell(col) or f"col_{idx + 1}" for idx, col in enumerate(frame.columns)]
                frame = frame.fillna("")
    except Exception:
        pd_tables = []
    fallback = fallback_read_html_tables(html)
    return pd_tables + fallback


# ── 表格查询工具 ──


def table_text(frame) -> str:
    """获取表格所有文本（小写）。"""
    records = dataframe_to_records(frame, 8)
    return " ".join(" ".join(row.values()) for row in records).lower()


def section_text(frame) -> str:
    """获取表格所属章节名。"""
    if "_section" not in frame.columns or frame.empty:
        return ""
    return normalize_cell(frame["_section"].iloc[0])


def dataframe_to_records(frame, limit: int = 30) -> list[dict]:
    """DataFrame → list[dict]"""
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty:
        return []
    frame = frame.fillna("")
    columns = [normalize_cell(col) or f"col_{idx + 1}" for idx, col in enumerate(frame.columns)]
    records = []
    for _, row in frame.head(limit).iterrows():
        records.append({columns[idx]: normalize_cell(value) for idx, value in enumerate(row.tolist())})
    return records


def find_table_by_keywords(tables: list, keywords: tuple[str, ...]):
    """按关键词查找表格。"""
    lowered = tuple(k.lower() for k in keywords)
    for frame in tables:
        text = (section_text(frame) + " " + table_text(frame)).lower()
        if all(k in text for k in lowered):
            return dataframe_to_records(frame)
    return "未识别到该模块"


def find_table_by_section(tables: list, section_name: str, limit: int = 30):
    """按章节名查找表格。"""
    wanted = section_name.lower()
    for frame in tables:
        if wanted in section_text(frame).lower():
            return dataframe_to_records(frame, limit)
    return "未识别到该模块"


def find_first_table_by_sections(tables: list, section_names: tuple[str, ...], limit: int = 30):
    """按多个章节名依次查找表格。"""
    for name in section_names:
        result = find_table_by_section(tables, name, limit)
        if not isinstance(result, str):
            return result
    return "未识别到该模块"


def find_table_with_columns(tables: list, columns: tuple[str, ...], limit: int = 30):
    """按列名组合查找表格。"""
    wanted = tuple(c.lower() for c in columns)
    for frame in tables:
        frame_columns = " ".join(str(c).lower() for c in frame.columns)
        if all(c in frame_columns for c in wanted):
            return dataframe_to_records(frame, limit)
    return "未识别到该模块"


def first_record(records):
    """取第一条记录。"""
    return records[0] if isinstance(records, list) and records else {}


def compact_sql_rows(records, limit: int = 10) -> list[dict] | str:
    """精简 SQL 行数据，保留关键列并排序。"""
    if isinstance(records, str):
        return records
    keep_order = [
        "SQL Id",
        "SQL ID",
        "Elapsed Time (s)",
        "CPU Time (s)",
        "Executions",
        "Elapsed Time per Exec (s)",
        "CPU per Exec (s)",
        "%Total",
        "%CPU",
        "%IO",
        "Buffer Gets",
        "Gets per Exec",
        "Physical Reads",
        "Reads per Exec",
        "Rows Processed",
        "Rows per Exec",
        "Parse Calls",
        "% Total Parses",
        "Cluster Wait Time (s)",
        "SQL Module",
        "Module",
        "PDB Name",
        "SQL Text",
    ]
    compacted = []
    for row in records[:limit]:
        item = {}
        for key in keep_order:
            if key in row and row[key] != "":
                value = row[key]
                if key == "SQL Text":
                    value = normalize_cell(value)[:300]
                item[key] = value
        for key, value in row.items():
            if key not in item and key != "_section" and value != "" and len(item) < 14:
                item[key] = normalize_cell(value)[:300] if "sql text" in key.lower() else value
        compacted.append(item)
    return compacted


# ── 值解析工具 ──


def parse_number(value) -> float | None:
    """解析数值。"""
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def parse_duration_minutes(value) -> float | None:
    """解析时间段（分钟）。"""
    number = parse_number(value)
    if number is None:
        return None
    text = str(value).lower()
    if "sec" in text:
        return number / 60
    if "hour" in text:
        return number * 60
    return number


def parse_wait_ms(value) -> float | None:
    """解析等待时间（毫秒）。"""
    number = parse_number(value)
    if number is None:
        return None
    text = str(value).lower().replace(" ", "")
    if "us" in text:
        return number / 1000
    if "ms" in text:
        return number
    if "sec" in text or text.endswith("s"):
        return number * 1000
    return number


def row_value(row: dict, names: tuple[str, ...]):
    """从行记录中按多个可能的列名取值。"""
    lowered = {k.lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    for key, value in row.items():
        key_lower = key.lower()
        if any(name.lower() in key_lower for name in names):
            return value
    return ""


def regex_value(text: str, patterns: tuple[str, ...]) -> str:
    """用正则从文本中提取值。"""
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_cell(match.group(1))
    return "未识别到该模块"


# ── AWR 解析主逻辑 ──


def extract_awr_basic_info(soup, tables: list) -> dict:
    """提取 AWR 基本信息。"""
    from bs4 import Tag

    text = ""
    if isinstance(soup, Tag):
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    else:
        text = str(soup)

    db_record = first_record(find_table_with_columns(tables, ("DB Name", "DB Id"), 5))
    instance_record = first_record(find_table_with_columns(tables, ("Instance", "Inst Num"), 5))
    host_record = first_record(find_table_with_columns(tables, ("Host Name", "Platform", "CPUs"), 5))
    snap_records = find_table_with_columns(tables, ("Snap Id", "Snap Time"), 10)
    pdb_records = find_table_with_columns(tables, ("Container DB Id", "Container Name"), 20)

    begin_snap = end_snap = elapsed = db_time = "未识别到该模块"
    if isinstance(snap_records, list):
        for row in snap_records:
            label = row_value(row, ("col_1",))
            joined = " ".join(row.values())
            if "Begin Snap" in label:
                begin_snap = f"{row_value(row, ('Snap Id',))} {row_value(row, ('Snap Time',))}".strip()
            elif "End Snap" in label:
                end_snap = f"{row_value(row, ('Snap Id',))} {row_value(row, ('Snap Time',))}".strip()
            elif "Elapsed" in label:
                elapsed = row_value(row, ("Snap Time",)) or joined
            elif "DB Time" in label:
                db_time = row_value(row, ("Snap Time",)) or joined

    cpus = row_value(host_record, ("CPUs",))
    elapsed_mins = parse_duration_minutes(elapsed)
    db_time_mins = parse_duration_minutes(db_time)
    aas = ""
    if elapsed_mins and db_time_mins:
        aas = f"{db_time_mins / elapsed_mins:.2f}"

    basic = {
        "DB Name": row_value(db_record, ("DB Name",)) or regex_value(
            text, (r"\bDB Name\s+([A-Za-z0-9_$#.-]+)",)
        ),
        "Instance Name": row_value(instance_record, ("Instance", "Instance Name")) or regex_value(
            text,
            (
                r"\bInst:\s*([A-Za-z0-9_$#.-]+)",
                r"\bInstance\s+([A-Za-z0-9_$#.-]+)",
            ),
        ),
        "Host Name": row_value(host_record, ("Host Name",)) or regex_value(
            text, (r"\bHost Name\s+([A-Za-z0-9_.-]+)",)
        ),
        "Oracle Version": row_value(db_record, ("Release",)) or regex_value(
            text, (r"\bRelease\s+([0-9.]+)",)
        ),
        "Begin Snap": begin_snap,
        "End Snap": end_snap,
        "Elapsed Time": elapsed,
        "DB Time": db_time,
        "Average Active Sessions": aas or "未识别到该模块",
        "CPUs": cpus or "未识别到该模块",
        "RAC": row_value(db_record, ("RAC",)) or "未识别到该模块",
        "CDB": row_value(db_record, ("CDB",)) or "未识别到该模块",
        "PDB 信息": ", ".join(
            row_value(row, ("Container Name",))
            for row in pdb_records
            if row_value(row, ("Container Name",))
        )
        if isinstance(pdb_records, list)
        else "未识别到该模块",
    }

    # 补充缺失字段
    for frame in tables[:10]:
        records = dataframe_to_records(frame, 20)
        for row in records:
            joined = " ".join(row.values())
            for key in list(basic):
                if basic[key] != "未识别到该模块":
                    continue
                m = re.search(re.escape(key) + r"\s+([^|]{1,80})", joined, flags=re.IGNORECASE)
                if m:
                    basic[key] = normalize_cell(m.group(1))
    return basic


def parse_awr_summary(path: Path) -> dict:
    """解析 AWR HTML 报告，提取结构化摘要。"""
    html = read_report_text(path)
    soup = BeautifulSoup(html, "html.parser") if HAS_BS4 else html
    parser_note = "BeautifulSoup+fallback" if HAS_BS4 else "fallback only"

    try:
        pd.read_html(str(path))
    except Exception as exc:
        parser_note += f" (pandas.read_html 未成功: {exc})"

    tables = read_html_tables(path)

    summary = {
        "source_file": str(path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parser": parser_note,
        "basic_info": extract_awr_basic_info(soup, tables) if HAS_BS4 else {},
        "Load Profile": find_table_by_section(tables, "Load Profile", 60),
        "Host CPU": find_table_by_section(tables, "Host CPU", 20),
        "Instance Efficiency": find_table_by_section(tables, "Instance Efficiency", 20),
        "Top Timed Events / Foreground Wait Events": find_first_table_by_sections(
            tables, ("Foreground Wait Events", "Top Timed Events"), 10
        ),
        "SQL ordered by Elapsed Time": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Elapsed Time", 15)
        ),
        "SQL ordered by CPU Time": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by CPU Time", 15)
        ),
        "SQL ordered by Gets": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Gets", 15)
        ),
        "SQL ordered by Reads": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Reads", 15)
        ),
        "SQL ordered by Executions": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Executions", 15)
        ),
        "SQL ordered by Parse Calls": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Parse Calls", 15)
        ),
        "SQL ordered by Cluster Wait Time": compact_sql_rows(
            find_table_by_section(tables, "SQL ordered by Cluster Wait Time", 15)
        ),
        "Segments by Logical Reads": find_table_by_section(tables, "Segments by Logical Reads", 10),
        "Segments by Physical Reads": find_table_by_section(tables, "Segments by Physical Reads", 10),
        "Segments by Row Lock Waits": find_table_by_section(tables, "Segments by Row Lock Waits", 10),
        "Segments by ITL Waits": find_table_by_section(tables, "Segments by ITL Waits", 10),
        "Buffer Cache Advisory": find_first_table_by_sections(
            tables, ("Buffer Cache Advisory", "Buffer Pool Advisory"), 20
        ),
        "PGA Advisory": find_table_by_section(tables, "PGA Memory Advisory", 20),
        "Shared Pool Advisory": find_table_by_section(tables, "Shared Pool Advisory", 20),
        "SGA Target Advisory": find_table_by_section(tables, "SGA Target Advisory", 20),
    }
    return summary


def render_awr_summary_markdown(summary: dict) -> str:
    """渲染 AWR 结构化摘要为 Markdown。"""
    lines = [
        "# Oracle AWR 结构化摘要",
        "",
        f"- 源文件：`{summary.get('source_file')}`",
        f"- 生成时间：{summary.get('generated_at')}",
        "",
        "## 基本信息",
        "",
    ]
    for key, value in summary.get("basic_info", {}).items():
        lines.append(f"- {key}：{value}")
    module_names = [
        "Load Profile",
        "Host CPU",
        "Instance Efficiency",
        "Top Timed Events / Foreground Wait Events",
        "SQL ordered by Elapsed Time",
        "SQL ordered by CPU Time",
        "SQL ordered by Gets",
        "SQL ordered by Reads",
        "SQL ordered by Executions",
        "SQL ordered by Parse Calls",
        "SQL ordered by Cluster Wait Time",
        "Segments by Logical Reads",
        "Segments by Physical Reads",
        "Segments by Row Lock Waits",
        "Segments by ITL Waits",
        "Buffer Cache Advisory",
        "PGA Advisory",
        "Shared Pool Advisory",
        "SGA Target Advisory",
    ]
    for name in module_names:
        lines.extend(["", f"## {name}", ""])
        lines.extend(table_to_markdown(summary.get(name), limit=30))
    lines.append("")
    return "\n".join(lines)


def table_to_markdown(records, limit: int = 30) -> list[str]:
    """将记录列表渲染为 Markdown 表格。"""
    if isinstance(records, str):
        return [records]
    if not records:
        return ["未识别到该模块"]
    rows = records[:limit]
    columns = []
    for row in rows:
        for col in row.keys():
            if col != "_section" and col not in columns:
                columns.append(col)
    if not columns:
        return ["未识别到该模块"]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "/") for col in columns) + " |")
    return lines


# ── 对外暴露的主入口 ──


def write_awr_summary(path: Path) -> dict:
    """解析 AWR 报告并写出摘要文件。"""
    summary = parse_awr_summary(path)
    md_path = AWR_SUMMARY_MD
    json_path = AWR_SUMMARY_JSON
    md_path.write_text(render_awr_summary_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["markdown_path"] = str(md_path)
    summary["json_path"] = str(json_path)
    return summary
