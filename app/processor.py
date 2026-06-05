import json
import zipfile
from datetime import datetime
from pathlib import Path

from .config import ALL_EXTENSIONS, EXCLUDED_PARTS, HTML_EXTENSIONS, OFFICE_EXTENSIONS, SKIP_EXTENSIONS, SUPPORTED_EXTENSIONS, TARGET_SUFFIX, TMP_DESENSITIZE
from .rules import merge_counts, redact_html_text, redact_office_xml, redact_text


def target_dir_for(source_dir: Path) -> Path:
    # 脱敏目标目录统一存到 TMP_DESENSITIZE 下，以源目录名命名
    return TMP_DESENSITIZE / f"{source_dir.name}{TARGET_SUFFIX}"


def target_file_for(source_file: Path) -> Path:
    stem = source_file.stem
    suffix = source_file.suffix
    candidate = source_file.with_name(f"{stem}{TARGET_SUFFIX}{suffix}")
    if not candidate.exists():
        return candidate
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return source_file.with_name(f"{stem}{TARGET_SUFFIX}_{timestamp}{suffix}")


def is_hidden_or_cache(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS or part.startswith(".~") for part in path.parts)


def scan_files(source_dir: Path):
    files = []
    skipped = []
    target_dir = target_dir_for(source_dir)
    for item in source_dir.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(source_dir)
        if is_hidden_or_cache(rel):
            skipped.append({"path": str(rel), "reason": "excluded"})
            continue
        if target_dir in item.parents:
            continue
        # ALL_EXTENSIONS = True 时，所有文件都参与脱敏（尝试以文本方式处理）
        files.append(item)
    return files, skipped


def extension_counts(paths):
    counts = {}
    for path in paths:
        ext = Path(path).suffix.lower() or "(no extension)"
        counts[ext] = counts.get(ext, 0) + 1
    return dict(sorted(counts.items()))


def process_text_file(src: Path, dst: Path):
    raw = src.read_bytes()
    # 尝试一系列常见编码解码
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk", "latin-1", "shift_jis", "euc-jp", "euc-kr", "big5", "cp1252"):
        try:
            text = raw.decode(encoding)
            redactor = redact_html_text if src.suffix.lower() in HTML_EXTENSIONS else redact_text
            redacted, counts = redactor(text)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(redacted, encoding="utf-8")
            return counts
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 最后的兜底：latin-1 可以解码任意字节序列，保证不丢失文件
    text = raw.decode("latin-1")
    redactor = redact_html_text if src.suffix.lower() in HTML_EXTENSIONS else redact_text
    redacted, counts = redactor(text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(redacted, encoding="utf-8")
    return counts


def process_office_file(src: Path, dst: Path):
    counts = {}
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith(".xml") or info.filename.endswith(".rels"):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(info, data)
                    continue
                redacted, file_counts = redact_office_xml(text)
                merge_counts(counts, file_counts)
                zout.writestr(info, redacted.encode("utf-8"))
            else:
                zout.writestr(info, data)
    return counts


def process_file(src: Path, dst: Path):
    if src.suffix.lower() in OFFICE_EXTENSIONS:
        return process_office_file(src, dst)
    return process_text_file(src, dst)


def redact_single_file(source_file: Path, target_file: Path | None = None) -> dict:
    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(f"源文件不存在或不是文件：{source_file}")
    ext = source_file.suffix.lower()

    target = target_file or target_file_for(source_file)
    started_at = datetime.now().isoformat(timespec="seconds")
    counts = process_file(source_file, target)
    report = {
        "source_file": str(source_file),
        "target_file": str(target),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "extension": ext,
    }
    report_path = target.with_name(f"{target.stem}_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def write_report(target_dir: Path, report: dict) -> Path:
    path = target_dir / "desensitization_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_report(source_dir, target_dir, started_at, files, skipped, failed, counts):
    return {
        "source_dir": str(source_dir),
        "target_dir": str(target_dir),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(files),
        "processed": len(files),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "counts": counts,
        "skipped": skipped,
        "failed": failed,
    }
