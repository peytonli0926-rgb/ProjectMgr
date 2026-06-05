import json
import os
import re
import socket
import ssl
import zipfile
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib import error, request
from xml.sax.saxutils import escape as xml_escape


def _get_ssl_context():
    """返回一个可用的 SSL 上下文，优先使用 certifi 证书包。

    macOS 自带的 Python 无法自动找到系统证书链，需要显式指定。
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    # 尝试常见证书路径
    for path in ("/etc/ssl/cert.pem",
                  "/etc/ssl/certs/ca-certificates.crt",
                  "/usr/local/etc/openssl@3/cert.pem",
                  "/usr/local/etc/openssl@1.1/cert.pem",
                  "/opt/homebrew/etc/openssl@3/cert.pem",
                  "/opt/homebrew/etc/openssl@1.1/cert.pem"):
        if os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    # 最后手段：不验证证书（不推荐，但保证可用）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

import pandas as pd
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


from .config import TMP_DATA, TMP_OUTPUT

ROOT = Path(__file__).resolve().parent.parent

# ── 图表生成（软依赖，从 awr-auto-analyzer 独立模块导入） ──
try:
    import sys as _sys
    _AWR_AUTO_DIR = ROOT / "awr-auto-analyzer"
    if _AWR_AUTO_DIR.exists():
        _sys.path.insert(0, str(_AWR_AUTO_DIR))
        from awr_auto_analyzer.chart_generator import generate_all_charts as _generate_charts
    else:
        _generate_charts = None
except Exception:
    _generate_charts = None
DATA_DIR = TMP_DATA
AWR_DATA_DIR = TMP_DATA / "awr"
OUTPUT_DIR = TMP_OUTPUT
REPORT_TEMPLATE_DIR = ROOT / "templates" / "report_demo"
DEFAULT_LST = DATA_DIR / "oracle_perf_compare.lst"
DEFAULT_DEEPSEEK_URL = os.environ.get("LOCAL_DEEPSEEK_URL", "http://127.0.0.1:11434/api/chat")
DEFAULT_DEEPSEEK_MODEL = os.environ.get("LOCAL_DEEPSEEK_MODEL", "deepseek-r1")

SECTION_PATTERN = re.compile(r"^\s*\[(?P<index>\d+)]\s*(?P<title>.+?)\s*$")
METRIC_PATTERN = re.compile(r"^\s*(?P<key>[A-Za-z][A-Za-z0-9_ /().%-]{2,})\s*[:=]\s*(?P<value>.+?)\s*$")
DASH_ROW_PATTERN = re.compile(r"^\s*-+(?:\s+-+)+\s*$")
WINDOW_PATTERN = re.compile(r"^\s*(?P<name>问题时间窗口|对比时间窗口)：(?P<value>.+?)\s*$")


def list_lst_files(data_dir: Path = DATA_DIR) -> list[dict]:
    if not data_dir.exists():
        return []
    files = []
    for path in sorted(data_dir.glob("*.lst"), key=lambda item: item.stat().st_mtime, reverse=True):
        files.append({
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return files


def list_awr_files(data_dir: Path = DATA_DIR) -> list[dict]:
    if not data_dir.exists():
        return []
    candidates = []
    for pattern in ("*.html", "*.htm", "*.txt", "*.lst"):
        candidates.extend(data_dir.glob(pattern))
        candidates.extend((data_dir / "awr").glob(pattern) if (data_dir / "awr").exists() else [])
    awr_files = []
    for path in sorted(set(candidates), key=lambda item: item.stat().st_mtime, reverse=True):
        name = path.name.lower()
        if "awr" not in name and "ash" not in name and path.suffix.lower() not in {".html", ".htm"}:
            continue
        awr_files.append({
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return awr_files


def list_report_templates(template_dir: Path = REPORT_TEMPLATE_DIR) -> list[dict]:
    if not template_dir.exists():
        return []
    templates = []
    for path in sorted(template_dir.glob("*.docx")):
        templates.append({
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return templates


def safe_template_path(template_path: str | None) -> Path | None:
    if not template_path:
        return None
    candidate = Path(template_path).expanduser().resolve()
    allowed_root = REPORT_TEMPLATE_DIR.resolve()
    if candidate.suffix.lower() != ".docx":
        return None
    if allowed_root != candidate and allowed_root not in candidate.parents:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


def discover_local_models(url: str = DEFAULT_DEEPSEEK_URL) -> list[str]:
    if "/api/chat" in url:
        tags_url = url.replace("/api/chat", "/api/tags")
    elif "/v1/chat/completions" in url:
        tags_url = url.replace("/v1/chat/completions", "/v1/models")
    else:
        return []
    try:
        ssl_ctx = _get_ssl_context()
        with request.urlopen(tags_url, timeout=5, context=ssl_ctx) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    if isinstance(payload.get("models"), list):
        models = payload["models"]
        names = []
        for item in models:
            if isinstance(item, dict):
                names.append(item.get("name") or item.get("model") or item.get("id"))
            elif isinstance(item, str):
                names.append(item)
        return [name for name in names if name]
    if isinstance(payload.get("data"), list):
        return [item.get("id") for item in payload["data"] if isinstance(item, dict) and item.get("id")]
    return []


def preferred_model(url: str = DEFAULT_DEEPSEEK_URL) -> str:
    models = discover_local_models(url)
    if DEFAULT_DEEPSEEK_MODEL in models:
        return DEFAULT_DEEPSEEK_MODEL
    for model in models:
        if "deepseek" in model.lower():
            return model
    return models[0] if models else DEFAULT_DEEPSEEK_MODEL


def extract_docx_text(path: Path, limit: int = 6000) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""
    text_items = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, flags=re.DOTALL)
    if not text_items:
        text = re.sub(r"<[^>]+>", "", xml)
    else:
        text = "".join(unescape(re.sub(r"<[^>]+>", "", item)) for item in text_items)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def template_profile(template_path: Path | None) -> dict | None:
    if not template_path:
        return None
    text = extract_docx_text(template_path)
    headings = []
    toc_match = re.search(r"目录(.+?附件与材料清单)", text)
    toc_text = toc_match.group(1) if toc_match else text
    numbered_items = re.findall(r"\d+[.、]\s*([^0-9]{2,40}?)(?=\d+[.、]|$)", toc_text)
    candidates = numbered_items or re.findall(r"([^。；：]{2,28})", toc_text)
    for item in candidates:
        item = item.strip()
        if item and item not in headings and "填写" not in item:
            headings.append(item)
        if len(headings) >= 14:
            break
    return {
        "path": str(template_path),
        "name": template_path.name,
        "text_excerpt": text[:1800],
        "headings": headings,
    }


def is_placeholder(path: Path) -> bool:
    sample = path.read_text(encoding="utf-8", errors="replace")[:512]
    return "TODO: replace this file" in sample


def find_latest_lst(data_dir: Path = DATA_DIR) -> Path | None:
    candidates = [Path(item["path"]) for item in list_lst_files(data_dir)]
    real_reports = [candidate for candidate in candidates if not is_placeholder(candidate)]
    candidates = real_reports or candidates
    return candidates[0] if candidates else None


def split_fixed_width_row(line: str, spans: list[tuple[int, int | None]]) -> list[str]:
    return [line[start:end].strip() for start, end in spans]


def parse_tables(lines: list[str], section_by_line: dict[int, dict]) -> list[dict]:
    tables = []
    index = 1
    while index < len(lines):
        line = lines[index]
        previous = lines[index - 1] if index > 0 else ""
        if not DASH_ROW_PATTERN.match(line) or not previous.strip():
            index += 1
            continue

        dash_spans = [(match.start(), match.end()) for match in re.finditer(r"-+", line)]
        if len(dash_spans) < 2:
            index += 1
            continue

        spans = []
        for span_index, (start, _end) in enumerate(dash_spans):
            next_start = dash_spans[span_index + 1][0] if span_index + 1 < len(dash_spans) else None
            spans.append((start, next_start))

        columns = split_fixed_width_row(previous, spans)
        if not all(columns):
            index += 1
            continue

        rows = []
        row_index = index + 1
        while row_index < len(lines):
            row = lines[row_index]
            stripped = row.strip()
            if not stripped or stripped.startswith("prompt ") or SECTION_PATTERN.match(row) or DASH_ROW_PATTERN.match(row):
                break
            values = split_fixed_width_row(row, spans)
            if any(values):
                rows.append(dict(zip(columns, values)))
            row_index += 1

        nearest_section = None
        for line_no in range(index + 1, 0, -1):
            if line_no in section_by_line:
                nearest_section = section_by_line[line_no]
                break

        tables.append({
            "section": nearest_section,
            "line": index + 1,
            "columns": columns,
            "rows": rows,
        })
        index = max(row_index, index + 1)

    return tables


def parse_lst(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    sections = []
    section_by_line = {}
    metrics = {}
    windows = {}

    for index, line in enumerate(lines, start=1):
        section_match = SECTION_PATTERN.match(line)
        if section_match:
            section = {
                "index": int(section_match.group("index")),
                "title": section_match.group("title").strip(),
                "line": index,
            }
            sections.append(section)
            section_by_line[index] = section
            continue

        window_match = WINDOW_PATTERN.match(line)
        if window_match:
            windows[window_match.group("name")] = window_match.group("value").strip()
            continue

        metric_match = METRIC_PATTERN.match(line)
        if metric_match:
            metrics[metric_match.group("key").strip()] = metric_match.group("value").strip()

    return {
        "source_file": str(path),
        "line_count": len(lines),
        "windows": windows,
        "sections": sections,
        "tables": parse_tables(lines, section_by_line),
        "metrics": metrics,
        "notes": [],
    }


def html_to_text(raw: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?i)</(?:tr|p|div|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_report_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"} or re.search(r"(?is)<html|<table|<body", text[:4096]):
        return html_to_text(text)
    return "\n".join(line.rstrip() for line in text.splitlines())


def extract_awr_sections(lines: list[str]) -> list[dict]:
    wanted = (
        "workload repository report",
        "snapshot",
        "database summary",
        "load profile",
        "instance efficiency",
        "top timed events",
        "foreground wait events",
        "background wait events",
        "time model",
        "sql ordered by elapsed time",
        "sql ordered by cpu time",
        "sql ordered by gets",
        "sql ordered by reads",
        "sql ordered by executions",
        "sql ordered by parse calls",
        "segments by",
        "tablespace io",
        "file io",
        "buffer pool",
        "advisory",
        "latch",
        "enqueue",
    )
    sections = []
    current = None
    for index, line in enumerate(lines, start=1):
        normalized = line.lower().strip(" -=:_")
        is_heading = any(key in normalized for key in wanted) and len(line) <= 140
        if is_heading:
            current = {"title": line.strip(), "line": index, "lines": []}
            sections.append(current)
            continue
        if current and len(current["lines"]) < 45:
            current["lines"].append(line)
    return sections[:18]


def parse_awr(path: Path) -> dict:
    text = read_report_text(path)
    lines = [line for line in text.splitlines() if line.strip()]
    metrics = {}
    for line in lines[:300]:
        for key in ("DB Name", "Instance", "Host Name", "Platform", "Release", "RAC", "Snap Id", "Begin Snap", "End Snap"):
            if key.lower() in line.lower() and len(line) <= 180:
                metrics.setdefault(key, []).append(line.strip())
    return {
        "source_file": str(path),
        "line_count": len(lines),
        "sections": extract_awr_sections(lines),
        "metrics": metrics,
        "text_excerpt": "\n".join(lines[:220]),
    }


def normalize_cell(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def dataframe_to_records(frame, limit: int = 30) -> list[dict]:
    frame = frame.dropna(how="all").dropna(axis=1, how="all")
    if frame.empty:
        return []
    frame = frame.fillna("")
    columns = [normalize_cell(col) or f"col_{idx + 1}" for idx, col in enumerate(frame.columns)]
    records = []
    for _, row in frame.head(limit).iterrows():
        records.append({columns[idx]: normalize_cell(value) for idx, value in enumerate(row.tolist())})
    return records


def fallback_read_html_tables(html: str) -> list:
    frames = []
    position = 0
    for match in re.finditer(r"(?is)<table[^>]*>(.*?)</table>", html):
        prefix = html[position:match.start()]
        context_prefix = html[max(0, match.start() - 1600):match.start()]
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
            normalized = [row + [""] * (width - len(row)) for row in rows]
            headers = normalized[0] if has_header else [f"col_{idx + 1}" for idx in range(width)]
            data = normalized[1:] if has_header and len(normalized) > 1 else normalized
            columns = [header or f"col_{idx + 1}" for idx, header in enumerate(headers)]
            frame = pd.DataFrame(data, columns=columns)
            if section:
                frame.insert(0, "_section", section)
            frames.append(frame)
        position = match.end()
    return frames


def table_text(frame) -> str:
    records = dataframe_to_records(frame, 8)
    return " ".join(" ".join(row.values()) for row in records).lower()


def section_text(frame) -> str:
    if "_section" not in frame.columns or frame.empty:
        return ""
    return normalize_cell(frame["_section"].iloc[0])


def find_table_by_keywords(tables: list, keywords: tuple[str, ...]):
    lowered = tuple(keyword.lower() for keyword in keywords)
    for frame in tables:
        text = (section_text(frame) + " " + table_text(frame)).lower()
        if all(keyword in text for keyword in lowered):
            return dataframe_to_records(frame)
    return "未识别到该模块"


def find_table_by_section(tables: list, section_name: str, limit: int = 30):
    wanted = section_name.lower()
    for frame in tables:
        if wanted in section_text(frame).lower():
            return dataframe_to_records(frame, limit)
    return "未识别到该模块"


def find_first_table_by_sections(tables: list, section_names: tuple[str, ...], limit: int = 30):
    for name in section_names:
        result = find_table_by_section(tables, name, limit)
        if not isinstance(result, str):
            return result
    return "未识别到该模块"


def find_table_with_columns(tables: list, columns: tuple[str, ...], limit: int = 30):
    wanted = tuple(column.lower() for column in columns)
    for frame in tables:
        frame_columns = " ".join(str(column).lower() for column in frame.columns)
        if all(column in frame_columns for column in wanted):
            return dataframe_to_records(frame, limit)
    return "未识别到该模块"


def first_record(records):
    return records[0] if isinstance(records, list) and records else {}


def compact_sql_rows(records, limit: int = 10) -> list[dict] | str:
    if isinstance(records, str):
        return records
    keep_order = [
        "SQL Id", "SQL ID", "Elapsed Time (s)", "CPU Time (s)", "Executions",
        "Elapsed Time per Exec (s)", "CPU per Exec (s)", "%Total", "%CPU", "%IO",
        "Buffer Gets", "Gets per Exec", "Physical Reads", "Reads per Exec",
        "Rows Processed", "Rows per Exec", "Parse Calls", "% Total Parses",
        "Cluster Wait Time (s)", "SQL Module", "Module", "PDB Name", "SQL Text",
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


def parse_number(value) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def parse_duration_minutes(value) -> float | None:
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
    lowered = {key.lower(): value for key, value in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    for key, value in row.items():
        key_lower = key.lower()
        if any(name.lower() in key_lower for name in names):
            return value
    return ""


def metric_rows_to_map(records) -> dict:
    metrics = {}
    if not isinstance(records, list):
        return metrics
    for row in records:
        name = row_value(row, ("col_1", "Statistic", "Name", "Metric"))
        if not name:
            values = list(row.values())
            name = values[0] if values else ""
        if name:
            clean_name = normalize_cell(str(name)).rstrip(":")
            metrics[clean_name] = {key: value for key, value in row.items() if key != "_section"}
    return metrics


def table_to_markdown(records, limit: int = 30) -> list[str]:
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


def soup_text(soup) -> str:
    if BeautifulSoup:
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return html_to_text(str(soup))


def regex_value(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_cell(match.group(1))
    return "未识别到该模块"


def extract_awr_basic_info(soup, tables: list) -> dict:
    text = soup_text(soup)
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
        "DB Name": row_value(db_record, ("DB Name",)) or regex_value(text, (r"\bDB Name\s+([A-Za-z0-9_$#.-]+)",)),
        "Instance Name": row_value(instance_record, ("Instance", "Instance Name")) or regex_value(text, (r"\bInst:\s*([A-Za-z0-9_$#.-]+)", r"\bInstance\s+([A-Za-z0-9_$#.-]+)")),
        "Host Name": row_value(host_record, ("Host Name",)) or regex_value(text, (r"\bHost Name\s+([A-Za-z0-9_.-]+)",)),
        "Oracle Version": row_value(db_record, ("Release",)) or regex_value(text, (r"\bRelease\s+([0-9.]+)",)),
        "Begin Snap": begin_snap,
        "End Snap": end_snap,
        "Elapsed Time": elapsed,
        "DB Time": db_time,
        "Average Active Sessions": aas or "未识别到该模块",
        "CPUs": cpus or "未识别到该模块",
        "RAC": row_value(db_record, ("RAC",)) or "未识别到该模块",
        "CDB": row_value(db_record, ("CDB",)) or "未识别到该模块",
        "PDB 信息": ", ".join(row_value(row, ("Container Name",)) for row in pdb_records if row_value(row, ("Container Name",))) if isinstance(pdb_records, list) else "未识别到该模块",
    }
    for frame in tables[:10]:
        records = dataframe_to_records(frame, 20)
        for row in records:
            joined = " ".join(row.values())
            for key in list(basic):
                if basic[key] != "未识别到该模块":
                    continue
                match = re.search(re.escape(key) + r"\s+([^|]{1,80})", joined, flags=re.IGNORECASE)
                if match:
                    basic[key] = normalize_cell(match.group(1))
    return basic


def parse_awr_summary(path: Path) -> dict:
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else html
    parser_note = "BeautifulSoup+pandas.read_html+section fallback" if BeautifulSoup else "html_to_text fallback+pandas.read_html"
    try:
        pd.read_html(str(path))
    except Exception as exc:
        parser_note += f" (pandas.read_html 未成功: {exc})"
    tables = fallback_read_html_tables(html)
    summary = {
        "source_file": str(path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parser": parser_note,
        "basic_info": extract_awr_basic_info(soup, tables),
        "Load Profile": find_table_by_section(tables, "Load Profile", 60),
        "Host CPU": find_table_by_section(tables, "Host CPU", 20),
        "Instance Efficiency": find_table_by_section(tables, "Instance Efficiency", 20),
        "Top Timed Events / Foreground Wait Events": find_first_table_by_sections(tables, ("Foreground Wait Events", "Top Timed Events"), 10),
        "SQL ordered by Elapsed Time": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Elapsed Time", 15)),
        "SQL ordered by CPU Time": compact_sql_rows(find_table_by_section(tables, "SQL ordered by CPU Time", 15)),
        "SQL ordered by Gets": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Gets", 15)),
        "SQL ordered by Reads": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Reads", 15)),
        "SQL ordered by Executions": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Executions", 15)),
        "SQL ordered by Parse Calls": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Parse Calls", 15)),
        "SQL ordered by Cluster Wait Time": compact_sql_rows(find_table_by_section(tables, "SQL ordered by Cluster Wait Time", 15)),
        "Segments by Logical Reads": find_table_by_section(tables, "Segments by Logical Reads", 10),
        "Segments by Physical Reads": find_table_by_section(tables, "Segments by Physical Reads", 10),
        "Segments by Row Lock Waits": find_table_by_section(tables, "Segments by Row Lock Waits", 10),
        "Segments by ITL Waits": find_table_by_section(tables, "Segments by ITL Waits", 10),
        "Buffer Cache Advisory": find_first_table_by_sections(tables, ("Buffer Cache Advisory", "Buffer Pool Advisory"), 20),
        "PGA Advisory": find_table_by_section(tables, "PGA Memory Advisory", 20),
        "Shared Pool Advisory": find_table_by_section(tables, "Shared Pool Advisory", 20),
        "SGA Target Advisory": find_table_by_section(tables, "SGA Target Advisory", 20),
    }
    return summary


def render_awr_summary_markdown(summary: dict) -> str:
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


def write_awr_summary(path: Path) -> dict:
    summary = parse_awr_summary(path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / "awr_summary.md"
    json_path = OUTPUT_DIR / "awr_summary.json"
    md_path.write_text(render_awr_summary_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["markdown_path"] = str(md_path)
    summary["json_path"] = str(json_path)
    return summary


def add_rule_finding(findings: list[dict], rule: str, level: str, finding: str, evidence: str, recommendation: str):
    findings.append({
        "rule": rule,
        "level": level,
        "finding": finding,
        "evidence": evidence,
        "recommendation": recommendation,
    })


def find_metric_row(records, metric_name: str) -> dict:
    if not isinstance(records, list):
        return {}
    wanted = metric_name.lower()
    for row in records:
        values = [normalize_cell(value).lower() for value in row.values()]
        if any(wanted in value for value in values):
            return row
    return {}


def metric_per_second(records, metric_name: str) -> float | None:
    row = find_metric_row(records, metric_name)
    return parse_number(row_value(row, ("Per Second",))) if row else None


def efficiency_value(records, metric_name: str) -> float | None:
    if not isinstance(records, list):
        return None
    wanted = metric_name.lower()
    for row in records:
        items = list(row.values())
        for index, value in enumerate(items):
            if wanted in normalize_cell(value).lower():
                if index + 1 < len(items):
                    return parse_number(items[index + 1])
    return None


def event_row(records, event_name: str) -> dict:
    if not isinstance(records, list):
        return {}
    wanted = event_name.lower()
    for row in records:
        event = row_value(row, ("Event", "Wait Class"))
        if wanted in normalize_cell(event).lower():
            return row
    return {}


def event_percent_db_time(row: dict) -> float | None:
    return parse_number(row_value(row, ("% DB time", "%DB time", "% of DB Time")))


def render_rule_findings_markdown(result: dict) -> str:
    lines = [
        "# Oracle AWR 规则引擎发现",
        "",
        f"- 源文件：`{result.get('source_file')}`",
        f"- 生成时间：{result.get('generated_at')}",
        "",
        "## 关键计算指标",
        "",
    ]
    for key, value in result.get("computed_metrics", {}).items():
        lines.append(f"- {key}：{value}")
    lines.extend([
        "",
        "## 规则判断结果",
        "",
        "| 规则 | 等级 | 判断 | 证据 | 建议 |",
        "| --- | --- | --- | --- | --- |",
    ])
    for item in result.get("findings", []):
        lines.append(
            "| "
            + " | ".join(str(item.get(col, "")).replace("|", "/") for col in ("rule", "level", "finding", "evidence", "recommendation"))
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_awr_rule_findings(summary: dict) -> dict:
    findings = []
    basic = summary.get("basic_info") or {}
    load_profile = summary.get("Load Profile")
    efficiency = summary.get("Instance Efficiency")
    waits = summary.get("Top Timed Events / Foreground Wait Events")
    sql_elapsed = summary.get("SQL ordered by Elapsed Time")
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

    if aas is not None and cpus:
        ratio = aas / cpus
        level = "高" if ratio >= 0.7 else "中" if ratio >= 0.3 else "低"
        add_rule_finding(findings, "AAS 负载", level, f"AAS/CPU={ratio:.2f}", f"DB Time={basic.get('DB Time')}，Elapsed={basic.get('Elapsed Time')}，CPUs={basic.get('CPUs')}", "结合业务峰值和 OS CPU 使用率确认是否存在容量压力。")
    else:
        add_rule_finding(findings, "AAS 负载", "信息不足", "证据不足，不做强判断", "缺少 DB Time、Elapsed Time 或 CPUs", "补充完整 AWR 基本信息。")

    db_time_s = metric_per_second(load_profile, "DB Time")
    db_cpu_s = metric_per_second(load_profile, "DB CPU")
    if db_time_s and db_cpu_s is not None:
        ratio = db_cpu_s / db_time_s
        computed["DB CPU / DB Time"] = f"{ratio:.2%}"
        if ratio > 0.7:
            add_rule_finding(findings, "CPU 型负载", "高", "DB CPU 占 DB Time 超过 70%", f"DB CPU(s)={db_cpu_s}，DB Time(s)={db_time_s}", "优先核查 CPU 消耗 Top SQL、执行计划和主机 CPU 饱和度。")
        else:
            add_rule_finding(findings, "CPU 型负载", "低", "DB CPU 占比未超过 70%", f"DB CPU(s)={db_cpu_s}，DB Time(s)={db_time_s}", "CPU 不是唯一主导瓶颈，继续结合等待事件判断。")
    else:
        add_rule_finding(findings, "CPU 型负载", "信息不足", "证据不足，不做强判断", "缺少 Load Profile 中 DB CPU(s) 或 DB Time(s)", "补充 Load Profile。")

    top_wait = first_record(waits if isinstance(waits, list) else [])
    top_wait_pct = event_percent_db_time(top_wait)
    if top_wait and top_wait_pct is not None:
        event = row_value(top_wait, ("Event",))
        if top_wait_pct > 40:
            add_rule_finding(findings, "Top 等待集中", "高", "Top 1 等待事件超过 DB Time 40%", f"{event}，%DB Time={top_wait_pct}", "优先围绕该等待事件做 SQL、对象和系统层取证。")
        else:
            add_rule_finding(findings, "Top 等待集中", "低", "Top 1 等待事件未超过 DB Time 40%", f"{event}，%DB Time={top_wait_pct}", "等待分布相对分散，需综合 Top SQL 和资源画像判断。")
    else:
        add_rule_finding(findings, "Top 等待集中", "信息不足", "证据不足，不做强判断", "未识别 Top Timed/Foreground Wait Events", "补充等待事件表。")

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
            add_rule_finding(findings, label, "信息不足", "证据不足，不做强判断", f"未识别 {event_name} 平均等待", "补充等待事件明细或直方图。")
        elif avg_ms > threshold:
            add_rule_finding(findings, label, "中高", f"{event_name} 平均等待超过 {threshold}ms", f"Avg Wait={row_value(row, ('Avg wait', 'Avg Wait', 'Avg Wait Time'))}", "结合存储延迟、redo 写入、SQL 访问路径或 Direct Path 读来源继续取证。")
        else:
            add_rule_finding(findings, label, "低", f"{event_name} 平均等待未超过阈值", f"Avg Wait={row_value(row, ('Avg wait', 'Avg Wait', 'Avg Wait Time'))}", "当前证据不支持该类等待为主要风险。")

    hard_parse = metric_per_second(load_profile, "Hard parses")
    if hard_parse is None:
        add_rule_finding(findings, "Hard Parse", "信息不足", "证据不足，不做强判断", "未识别 Hard parses", "补充 Load Profile。")
    elif hard_parse > 10:
        add_rule_finding(findings, "Hard Parse", "中", "Hard Parse 偏高", f"Hard parses/s={hard_parse}", "检查绑定变量、共享池压力、SQL 版本数和应用解析行为。")
    else:
        add_rule_finding(findings, "Hard Parse", "低", "Hard Parse 未见明显偏高", f"Hard parses/s={hard_parse}", "持续观察解析峰值和 SQL 版本数。")

    execute_to_parse = efficiency_value(efficiency, "Execute to Parse")
    if execute_to_parse is None:
        add_rule_finding(findings, "Execute to Parse", "信息不足", "证据不足，不做强判断", "未识别 Execute to Parse %", "补充 Instance Efficiency。")
    elif execute_to_parse < 70:
        add_rule_finding(findings, "Execute to Parse", "中", "Execute to Parse 偏低，游标复用不足", f"Execute to Parse %={execute_to_parse}", "检查会话缓存游标、应用短连接和 SQL 解析模式。")
    else:
        add_rule_finding(findings, "Execute to Parse", "低", "Execute to Parse 未见明显偏低", f"Execute to Parse %={execute_to_parse}", "当前证据不支持游标复用为主要问题。")

    top_sql = first_record(sql_elapsed if isinstance(sql_elapsed, list) else [])
    top_sql_pct = parse_number(row_value(top_sql, ("%Total", "% Total", "%DB Time")))
    if top_sql and top_sql_pct is not None:
        if top_sql_pct > 20:
            add_rule_finding(findings, "Top SQL 负载集中", "高", "单条 SQL 占 DB Time/Elapsed 总量超过 20%", f"SQL ID={row_value(top_sql, ('SQL Id', 'SQL ID'))}，%Total={top_sql_pct}", "优先获取执行计划、绑定变量、对象统计信息并评估 SQL 改写。")
        else:
            add_rule_finding(findings, "Top SQL 负载集中", "低", "Top SQL 占比未超过 20%", f"SQL ID={row_value(top_sql, ('SQL Id', 'SQL ID'))}，%Total={top_sql_pct}", "SQL 负载相对分散，继续按类别分析。")
    else:
        add_rule_finding(findings, "Top SQL 负载集中", "信息不足", "证据不足，不做强判断", "未识别 SQL ordered by Elapsed Time 或 %Total", "补充 Top SQL 表。")

    rac_rows = [row for row in waits if isinstance(waits, list) for value in row.values() if "gc " in normalize_cell(value).lower()]
    rac_pct = max((event_percent_db_time(row) or 0 for row in rac_rows), default=0)
    if rac_pct > 10:
        add_rule_finding(findings, "RAC Global Cache", "中高", "RAC gc 等待占比较高", f"最高 gc 等待 %DB Time={rac_pct}", "检查跨实例访问、热点块、服务部署亲和性和对象分区策略。")
    elif rac_rows:
        add_rule_finding(findings, "RAC Global Cache", "低", "识别到 gc 等待但占比不高", f"最高 gc 等待 %DB Time={rac_pct}", "保留为观察项。")
    else:
        add_rule_finding(findings, "RAC Global Cache", "信息不足", "证据不足，不做强判断", "未识别 RAC gc 等待", "如果为 RAC 环境，补充 Global Cache 章节。")

    return {
        "source_file": summary.get("source_file"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "computed_metrics": computed,
        "findings": findings,
    }


def write_awr_rule_findings(summary: dict) -> dict:
    result = build_awr_rule_findings(summary)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = OUTPUT_DIR / "awr_rule_findings.md"
    json_path = OUTPUT_DIR / "awr_rule_findings.json"
    md_path.write_text(render_rule_findings_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["markdown_path"] = str(md_path)
    result["json_path"] = str(json_path)
    return result


def compact_awr_for_prompt(parsed: dict) -> str:
    lines = [
        f"源文件：{parsed.get('source_file')}",
        f"行数：{parsed.get('line_count')}",
        "",
        "基础信息：",
    ]
    for key, values in (parsed.get("metrics") or {}).items():
        for value in values[:3]:
            lines.append(f"- {key}: {value}")
    lines.extend(["", "AWR 关键章节摘录："])
    for section in parsed.get("sections", [])[:14]:
        lines.extend([
            "",
            f"## {section.get('title')} (line {section.get('line')})",
            "\n".join(section.get("lines", [])[:35]),
        ])
    if len("\n".join(lines)) < 3000:
        lines.extend(["", "报告开头摘录：", parsed.get("text_excerpt", "")[:6000]])
    return "\n".join(lines)[:24000]


def build_awr_prompt(summary_markdown: str, rule_findings_markdown: str, profile: dict | None = None) -> str:
    template_instructions = ""
    if profile:
        template_instructions = (
            "\n所选 Word 模板信息：\n"
            f"- 模板文件：{profile.get('name')}\n"
            f"- 模板章节：{'、'.join(profile.get('headings') or [])}\n"
            f"- 模板摘录：{profile.get('text_excerpt')}\n\n"
            "请尽量沿用该模板的章节顺序、措辞风格和交付报告口吻。\n"
        )
    return (
        "你是资深 Oracle 数据库性能诊断专家，正在为金融行业客户交付 Oracle AWR 性能分析报告。"
        "只能使用下面提供的结构化 AWR 摘要和规则引擎发现，不要编造未提供的指标；证据不足时必须明确写“证据不足，不做强判断”。\n\n"
        "硬性要求：\n"
        "1. 必须使用中文，语气正式、专业、适合金融行业客户交付。\n"
        "2. 总体结论最多 5 条，每条必须引用具体 AWR 指标。\n"
        "3. SQL 分析必须保留 SQL ID，并引用 Elapsed Time、CPU Time、Executions、Buffer Gets、Disk Reads 等已有指标。\n"
        "4. 必须区分 CPU 型、IO 型、等待型、逻辑读型、执行次数型、解析型、RAC 等待型负载。\n"
        "5. 如果 SQL Text 有 ROWNUM、全表扫描、聚合、排序、关联、分区表、监控 SQL 等特征，要明确指出。\n"
        "6. 不要输出代码块、寒暄或解释提示词。\n\n"
        "请严格按以下 Markdown 结构输出：\n\n"
        "# Oracle AWR 性能分析报告\n\n"
        "## 1. 总体结论\n"
        "必须 5 条以内，每条引用具体 AWR 指标。\n\n"
        "## 2. 风险等级\n"
        "| 风险项 | 风险等级 | 证据 | 影响 |\n"
        "| --- | --- | --- | --- |\n\n"
        "## 3. 数据库负载画像\n"
        "必须分析 DB Time、DB CPU、AAS、Host CPU、Load Profile，并判断 CPU 型 / IO 型 / 等待型。\n\n"
        "## 4. Top Wait Events 分析\n"
        "逐条分析前 5 个等待事件：\n"
        "| Event | Wait Class | 指标 | 是否异常 | 判断 | 建议 |\n"
        "| --- | --- | --- | --- | --- | --- |\n\n"
        "## 5. Top SQL 分析\n"
        "逐条分析至少前 5 个 SQL：\n"
        "| SQL ID | 消耗类型 | 关键指标 | 问题判断 | 优化建议 |\n"
        "| --- | --- | --- | --- | --- |\n\n"
        "## 6. 主机资源分析\n"
        "结合 Host CPU、Load Average、等待事件判断 CPU / IO / 系统负载问题。\n\n"
        "## 7. 内存与参数建议\n"
        "分析 Buffer Cache、Shared Pool、PGA、SGA Advisory；证据不足时明确说明。\n\n"
        "## 8. 问题点清单\n"
        "| 序号 | 问题点 | 严重等级 | 证据 | 建议 |\n"
        "| --- | --- | --- | --- | --- |\n\n"
        "## 9. 整改建议\n"
        "分为短期建议、中期建议、长期建议。\n\n"
        "## 10. 后续取证清单\n"
        "列出 ASH、alert.log、listener.log、OS sar/nmon、SQL 执行计划、绑定变量、对象统计信息、批处理时间表、AWR 前后基线对比。\n\n"
        "## 11. 领导汇报摘要\n"
        "5 条以内，用管理语言表达。\n\n"
        "## 12. 专家交付结论\n"
        "用正式技术语言总结。\n\n"
        f"{template_instructions}"
        "以下是结构化 AWR 摘要：\n"
        f"{summary_markdown[:60000]}\n\n"
        "以下是规则引擎发现：\n"
        f"{rule_findings_markdown[:16000]}"
    )


def compact_report_for_prompt(parsed: dict) -> str:
    lines = [
        f"源文件：{parsed.get('source_file')}",
        f"行数：{parsed.get('line_count')}",
        f"问题时间窗口：{parsed.get('windows', {}).get('问题时间窗口', '-')}",
        f"对比时间窗口：{parsed.get('windows', {}).get('对比时间窗口', '-')}",
        f"章节数：{len(parsed.get('sections') or [])}",
        f"表格数：{len(parsed.get('tables') or [])}",
        "",
        "关键表格：",
    ]
    for table in (parsed.get("tables") or [])[:10]:
        section = table.get("section") or {}
        title = section.get("title") or f"line {table.get('line')}"
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        lines.extend([
            "",
            f"## [{section.get('index', '-')}] {title}",
            f"列：{', '.join(columns)}",
            "行数据：",
        ])
        for row in rows[:12]:
            lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines)


def build_deepseek_prompt(parsed: dict, profile: dict | None = None) -> str:
    compact = compact_report_for_prompt(parsed)
    template_instructions = ""
    if profile:
        template_instructions = (
            "\n所选 Word 模板信息：\n"
            f"- 模板文件：{profile.get('name')}\n"
            f"- 模板章节：{'、'.join(profile.get('headings') or [])}\n"
            f"- 模板摘录：{profile.get('text_excerpt')}\n\n"
            "请尽量沿用该模板的报告类型、章节顺序、措辞风格和交付报告口吻；"
            "遇到模板中的【填写】项时，根据本次 Oracle 性能分析材料补充，无法确认的写“当前材料未提供”。\n"
        )
    return (
        "你是资深 Oracle 性能诊断工程师。请基于下面的 Oracle Production Performance Compare Report 解析结果，"
        "直接输出一份可下载阅读的正式中文生产性能分析报告。\n\n"
        "硬性要求：\n"
        "0. 必须使用中文输出。\n"
        "1. 先给结论，判断问题窗口是否真的比对比窗口异常。\n"
        "2. 分析 ASH、等待事件、Top SQL、模块、对象、执行计划相关信号。\n"
        "3. 区分事实、推断和待验证项。\n"
        "4. 给出下一步排查 SQL/操作建议。\n"
        "5. 不要编造报表里不存在的数据。\n"
        "6. 按报告格式输出，包含：分析结论、分析背景、关键证据链、可能原因、影响评估、排查步骤、优化建议、风险与注意事项、管理层摘要。\n"
        "7. 内容适合直接写入 Word 文档，不要输出寒暄、说明或代码块。\n\n"
        "8. 不要解释 JSON 结构，不要说你需要更多信息，直接根据已给数据形成报告。\n\n"
        f"{template_instructions}"
        f"报表事实摘要：\n{compact}"
    )


def _ask_ollama(url: str, model: str, prompt: str, timeout: int = 600) -> str:
    """调用 Ollama 本地 API（/api/chat 协议）。"""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 8192,
        },
    }
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    ssl_ctx = _get_ssl_context()
    try:
        with request.urlopen(req, timeout=timeout, context=ssl_ctx) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama 接口返回 {exc.code}: {err_body or exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError("模型分析超时，请换更小模型或减少输入内容") from exc
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower():
            raise RuntimeError("模型分析超时，请换更小模型或减少输入内容") from exc
        raise
    return payload.get("message", {}).get("content", json.dumps(payload, ensure_ascii=False, indent=2))


def _ask_openai(url: str, model: str, prompt: str, api_key: str = "", timeout: int = 600) -> str:
    """调用 OpenAI 兼容 API（/v1/chat/completions 协议）。

    适用于 DeepSeek 官方在线 API、OpenAI API 等兼容服务。
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 8192,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body).encode("utf-8")
    req = request.Request(url, data=data, headers=headers)
    ssl_ctx = _get_ssl_context()
    try:
        with request.urlopen(req, timeout=timeout, context=ssl_ctx) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"在线 API 返回 {exc.code}: {err_body or exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise RuntimeError("在线 API 请求超时，请检查网络连接") from exc
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc.reason).lower():
            raise RuntimeError("在线 API 请求超时，请检查网络连接") from exc
        raise
    choices = payload.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def ask_llm(url: str, model: str, prompt: str, api_key: str = "", timeout: int = 600) -> str:
    """自动识别 API 协议类型并调用。

    支持两种协议：
    - Ollama（URL 包含 /api/chat）→ 调用 _ask_ollama
    - OpenAI 兼容（其他）→ 调用 _ask_openai
    """
    if "/api/chat" in url:
        return _ask_ollama(url, model, prompt, timeout)
    return _ask_openai(url, model, prompt, api_key, timeout)


def ask_local_deepseek(url: str, model: str, prompt: str, timeout: int = 600) -> str:
    """兼容旧版调用（仅 Ollama 协议，无 API Key）。"""
    return ask_llm(url, model, prompt, api_key="", timeout=timeout)


def build_analysis_summary(parsed: dict, deepseek_answer: str) -> str:
    tables = []
    for table in parsed.get("tables", [])[:8]:
        section = table.get("section") or {}
        title = section.get("title") or f"line {table.get('line')}"
        tables.append(f"- {title}: {len(table.get('rows') or [])} rows")
    return (
        "# Oracle 性能对比分析材料\n\n"
        "## 原始报告\n"
        f"- 文件：{parsed.get('source_file')}\n"
        f"- 行数：{parsed.get('line_count')}\n"
        f"- 问题时间窗口：{parsed.get('windows', {}).get('问题时间窗口', '-')}\n"
        f"- 对比时间窗口：{parsed.get('windows', {}).get('对比时间窗口', '-')}\n\n"
        "## 结构化解析摘要\n"
        f"- 章节数：{len(parsed.get('sections') or [])}\n"
        f"- 表格数：{len(parsed.get('tables') or [])}\n"
        + "\n".join(tables)
        + "\n\n## 本地模型分析\n"
        f"{deepseek_answer.strip()}\n\n"
    )


def word_text(text) -> str:
    return xml_escape(str(text or ""), {'"': '&quot;'})


def word_run(text, bold=False, size=22, color="333333"):
    bold_xml = "<w:b/>" if bold else ""
    return (
        "<w:r><w:rPr>"
        '<w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/>'
        f"{bold_xml}<w:sz w:val=\"{size}\"/><w:szCs w:val=\"{size}\"/><w:color w:val=\"{color}\"/>"
        f"</w:rPr><w:t xml:space=\"preserve\">{word_text(text)}</w:t></w:r>"
    )


def word_paragraph(text="", bold=False, size=22, color="333333", spacing_after=120):
    return (
        f'<w:p><w:pPr><w:spacing w:after="{spacing_after}"/></w:pPr>'
        f"{word_run(text, bold=bold, size=size, color=color)}</w:p>"
    )


def word_heading(text, level=1):
    sizes = {1: 36, 2: 30, 3: 26}
    colors = {1: "0F766E", 2: "0D9488", 3: "111C34"}
    return word_paragraph(text, bold=True, size=sizes.get(level, 24), color=colors.get(level, "111C34"), spacing_after=160)


def word_bullet(text):
    return (
        '<w:p><w:pPr><w:ind w:left="480" w:hanging="240"/><w:spacing w:after="80"/></w:pPr>'
        f"{word_run('• ' + str(text), size=22)}</w:p>"
    )


def report_markdown_to_word_body(markdown_text: str) -> str:
    body = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            body.append(word_paragraph("", spacing_after=80))
            continue
        if line.startswith("### "):
            body.append(word_heading(line[4:].strip(), 3))
        elif line.startswith("## "):
            body.append(word_heading(line[3:].strip(), 2))
        elif line.startswith("# "):
            body.append(word_heading(line[2:].strip(), 1))
        elif line.startswith(("- ", "* ")):
            body.append(word_bullet(line[2:].strip()))
        elif re.match(r"^\d+[.、]\s+", line):
            body.append(word_bullet(line))
        else:
            body.append(word_paragraph(line))
    return "".join(body)


def template_sectpr(template_path: Path | None) -> str | None:
    if not template_path:
        return None
    try:
        with zipfile.ZipFile(template_path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return None
    matches = re.findall(r"<w:sectPr[\s\S]*?</w:sectPr>", xml)
    return matches[-1] if matches else None


def write_docx_package(output_path: Path, document_xml: str, template_path: Path | None = None):
    if template_path:
        with zipfile.ZipFile(template_path, "r") as source, zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                if item.filename == "word/document.xml":
                    target.writestr(item, document_xml)
                else:
                    target.writestr(item, source.read(item.filename))
        return

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)


def create_oracle_docx(output_path: Path, title: str, report_text: str, parsed: dict, model: str, template_path: Path | None = None):
    now_text = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    body = [
        word_paragraph(parsed.get("report_title", "Oracle 性能分析报告"), bold=True, size=46, color="0F766E", spacing_after=120),
        word_paragraph(title, bold=True, size=30, color="111C34", spacing_after=200),
        word_paragraph(f"生成时间：{now_text}", size=20, color="666666"),
        word_paragraph(f"本地模型：{model}", size=20, color="666666"),
        word_paragraph(f"源文件：{parsed.get('source_file')}", size=20, color="666666"),
        word_paragraph(f"问题窗口：{parsed.get('windows', {}).get('问题时间窗口', '-')}", size=20, color="666666"),
        word_paragraph(f"对比窗口：{parsed.get('windows', {}).get('对比时间窗口', '-')}", size=20, color="666666", spacing_after=240),
        report_markdown_to_word_body(report_text),
    ]
    sect_pr = template_sectpr(template_path) or '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1200" w:right="1080" w:bottom="1200" w:left="1080"/></w:sectPr>'
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + sect_pr
        + "</w:body></w:document>"
    )
    write_docx_package(output_path, document_xml, template_path)


def analyze_lst_with_deepseek(path: Path, url: str, model: str, template_path: Path | None = None, api_key: str = "") -> dict:
    parsed = parse_lst(path)
    profile = template_profile(template_path)
    prompt = build_deepseek_prompt(parsed, profile)
    answer = ask_llm(url, model, prompt, api_key=api_key)
    analysis_summary = build_analysis_summary(parsed, answer)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(parsed["source_file"]).stem
    json_path = OUTPUT_DIR / f"{stem}_deepseek_analysis.json"
    md_path = OUTPUT_DIR / f"{stem}_local_model_report.md"
    word_path = OUTPUT_DIR / f"{stem}_local_model_report.docx"
    title = f"{Path(parsed['source_file']).name} 性能分析"
    create_oracle_docx(word_path, title, answer, parsed, model, template_path)
    result = {
        "source_file": parsed["source_file"],
        "parsed": parsed,
        "deepseek": {
            "url": url,
            "model": model,
            "answer": answer,
        },
        "analysis_summary": analysis_summary,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "word_path": str(word_path),
        "template": profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(answer, encoding="utf-8")
    return result


def analyze_awr_with_deepseek(path: Path, url: str, model: str, template_path: Path | None = None, api_key: str = "") -> dict:
    parsed = parse_awr(path)
    parsed["report_title"] = "Oracle AWR 性能分析报告"
    summary = write_awr_summary(path)
    rule_findings = write_awr_rule_findings(summary)

    # 生成性能图表
    try:
        if _generate_charts:
            print("📊 生成性能可视化图表...")
            _generate_charts(summary)
    except Exception as exc:
        print(f"   ⚠️ 图表生成异常（可忽略）：{exc}")
    profile = template_profile(template_path)
    summary_markdown = Path(summary["markdown_path"]).read_text(encoding="utf-8")
    rule_findings_markdown = Path(rule_findings["markdown_path"]).read_text(encoding="utf-8")
    prompt = build_awr_prompt(summary_markdown, rule_findings_markdown, profile)
    answer = ask_llm(url, model, prompt, api_key=api_key)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(parsed["source_file"]).stem
    json_path = OUTPUT_DIR / f"{stem}_awr_analysis.json"
    md_path = OUTPUT_DIR / "awr_analysis_report.md"
    word_path = OUTPUT_DIR / f"{stem}_awr_report.docx"
    title = f"{Path(parsed['source_file']).name} AWR 性能分析"
    create_oracle_docx(word_path, title, answer, parsed, model, template_path)
    result = {
        "source_file": parsed["source_file"],
        "parsed": parsed,
        "deepseek": {"url": url, "model": model, "answer": answer},
        "summary": summary,
        "rule_findings": rule_findings,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "word_path": str(word_path),
        "template": profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(answer, encoding="utf-8")
    return result
