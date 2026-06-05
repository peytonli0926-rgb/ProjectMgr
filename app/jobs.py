import threading
import time
from datetime import datetime
from pathlib import Path

from .config import TARGET_SUFFIX
from .processor import build_report, process_file, scan_files, target_dir_for, write_report
from .rules import merge_counts

JOBS = {}
JOBS_LOCK = threading.Lock()

# ── TFA job 存储 ──
TFA_JOBS = {}
TFA_JOBS_LOCK = threading.Lock()


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


# ── TFA job 管理 ──


def create_tfa_job(job_id: str, zip_path: str):
    with TFA_JOBS_LOCK:
        TFA_JOBS[job_id] = {
            "status": "pending",
            "zip_path": zip_path,
            "phase": "",
            "message": "等待启动...",
            "current": 0,
            "total": 0,
            "result": None,
            "error": None,
        }


def update_tfa_job(job_id: str, **changes):
    with TFA_JOBS_LOCK:
        if job_id in TFA_JOBS:
            TFA_JOBS[job_id].update(changes)


def get_tfa_job(job_id: str):
    with TFA_JOBS_LOCK:
        job = TFA_JOBS.get(job_id)
        return dict(job) if job else None


def _register_tfa_downloads(result: dict) -> None:
    """将 TFA 分析输出文件注册到下载白名单，避免下载时报 '文件不存在'。"""
    try:
        from app.server import register_download
        keys = ["evidence_path", "executive_path", "technical_path", "timeline_path", "snapshot_manifest_path"]
        for k in keys:
            v = result.get(k, "")
            if v:
                register_download(str(v))
    except Exception:
        pass  # 允许静默失败，不影响主流程


def run_tfa_job(job_id: str, zip_path: str, output_dir: str | None = None, keep_temp: bool = False, time_filter_days: int | None = None, time_start: str | None = None, time_end: str | None = None, first_match_only: bool = False):
    update_tfa_job(job_id, status="running", phase="extract", message="正在解压 TFA zip 包...", current=0, total=100)

    def progress_callback(phase: str, message: str, current: int, total: int):
        update_tfa_job(job_id, phase=phase, message=message, current=current, total=total)

    try:
        import sys as _sys
        _tfa_root = Path(__file__).resolve().parent.parent / "oracle-tfa-analyzer"
        if _tfa_root.exists():
            _sys.path.insert(0, str(_tfa_root))
        from oracle_tfa_analyzer.pipeline import run_pipeline

        result = run_pipeline(
            zip_path,
            output_dir=output_dir,
            keep_temp=keep_temp,
            progress_callback=progress_callback,
            time_filter_days=time_filter_days,
            time_start=time_start,
            time_end=time_end,
            first_match_only=first_match_only,
        )
        # ── 注册输出文件到下载白名单 ──
        _register_tfa_downloads(result)
        update_tfa_job(
            job_id,
            status="done",
            phase="done",
            message="分析完成",
            current=100,
            total=100,
            result=result,
        )
    except Exception as exc:
        update_tfa_job(
            job_id,
            status="failed",
            phase="error",
            message=str(exc),
            current=0,
            total=0,
            error=str(exc),
        )


def run_job(job_id: str, source: str, existing_strategy: str = "error"):
    source_dir = Path(source).expanduser().resolve()
    target_dir = target_dir_for(source_dir)
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        if not source_dir.exists() or not source_dir.is_dir():
            update_job(job_id, status="failed", error="源目录不存在或不是目录")
            return
        if target_dir.exists():
            if existing_strategy == "timestamp":
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                target_dir = source_dir.parent / f"{source_dir.name}{TARGET_SUFFIX}_{timestamp}"
            elif existing_strategy == "overwrite":
                import shutil
                shutil.rmtree(target_dir)
            else:
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
            except Exception as exc:
                failed.append({"path": str(rel), "reason": str(exc)})
            update_job(job_id, processed=index, counts=counts, failed=failed)
            time.sleep(0.05)

        report = build_report(source_dir, target_dir, started_at, files, skipped, failed, counts)
        report_path = write_report(target_dir, report)
        update_job(job_id, status="done", current_file="", report=str(report_path))
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
