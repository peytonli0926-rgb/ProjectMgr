import json
import zipfile
from datetime import datetime
from pathlib import Path

from .config import EXCLUDED_PARTS, OFFICE_EXTENSIONS, SKIP_EXTENSIONS, SUPPORTED_EXTENSIONS, TARGET_SUFFIX
from .rules import merge_counts, redact_office_xml, redact_text


def target_dir_for(source_dir: Path) -> Path:
    return source_dir.parent / f"{source_dir.name}{TARGET_SUFFIX}"


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
        ext = item.suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            files.append(item)
        elif ext in SKIP_EXTENSIONS:
            skipped.append({"path": str(rel), "reason": f"unsupported {ext}"})
        else:
            skipped.append({"path": str(rel), "reason": "unknown or binary"})
    return files, skipped


def extension_counts(paths):
    counts = {}
    for path in paths:
        ext = Path(path).suffix.lower() or "(no extension)"
        counts[ext] = counts.get(ext, 0) + 1
    return dict(sorted(counts.items()))


def process_text_file(src: Path, dst: Path):
    raw = src.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            redacted, counts = redact_text(text)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(redacted, encoding=encoding if encoding != "utf-8-sig" else "utf-8")
            return counts
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, "unsupported text encoding")


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
