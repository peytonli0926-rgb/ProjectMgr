import threading
import time
from datetime import datetime
from pathlib import Path

from .processor import build_report, process_file, scan_files, target_dir_for, write_report
from .rules import merge_counts

JOBS = {}
JOBS_LOCK = threading.Lock()


def create_job(job_id):
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "total": 0, "processed": 0, "current_file": ""}


def update_job(job_id, **changes):
    with JOBS_LOCK:
        JOBS[job_id].update(changes)


def get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def run_job(job_id: str, source: str):
    source_dir = Path(source).expanduser().resolve()
    target_dir = target_dir_for(source_dir)
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        if not source_dir.exists() or not source_dir.is_dir():
            update_job(job_id, status="failed", error="源目录不存在或不是目录")
            return
        if target_dir.exists():
            update_job(job_id, status="failed", error=f"目标目录已存在：{target_dir}")
            return

        files, skipped = scan_files(source_dir)
        target_dir.mkdir(parents=True, exist_ok=False)
        update_job(
            job_id,
            status="running",
            source_dir=str(source_dir),
            target_dir=str(target_dir),
            total=len(files),
            processed=0,
            current_file="",
            skipped=skipped,
            failed=[],
            counts={},
            started_at=started_at,
        )

        counts = {}
        failed = []
        for index, src in enumerate(files, start=1):
            rel = src.relative_to(source_dir)
            update_job(job_id, current_file=str(rel), processed=index - 1)
            try:
                file_counts = process_file(src, target_dir / rel)
                merge_counts(counts, file_counts)
            except Exception as exc:  # Keep the batch moving for a test tool.
                failed.append({"path": str(rel), "reason": str(exc)})
            update_job(job_id, processed=index, counts=counts, failed=failed)
            time.sleep(0.05)

        report = build_report(source_dir, target_dir, started_at, files, skipped, failed, counts)
        report_path = write_report(target_dir, report)
        update_job(job_id, status="done", current_file="", report=str(report_path))
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
