import json
import mimetypes
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .config import HOST, PORT
from .jobs import create_job, get_job, run_job
from .processor import extension_counts, scan_files, target_dir_for
from .reporting import generate_report, generate_weekly_report

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
ALLOWED_DOWNLOADS = set()
ALLOWED_DOWNLOADS_LOCK = threading.Lock()


def read_template(name: str) -> bytes:
    return (TEMPLATE_DIR / name).read_bytes()


def static_path(path: str):
    rel = path.removeprefix("/static/")
    candidate = (STATIC_DIR / rel).resolve()
    if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


def register_download(path):
    if not path:
        return
    resolved = Path(path).expanduser().resolve()
    with ALLOWED_DOWNLOADS_LOCK:
        ALLOWED_DOWNLOADS.add(resolved)


def downloadable_path(path: str):
    if not path:
        return None
    target = Path(unquote(path)).expanduser().resolve()
    with ALLOWED_DOWNLOADS_LOCK:
        allowed = target in ALLOWED_DOWNLOADS
    if not allowed or not target.exists() or not target.is_file():
        return None
    return target


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {fmt % args}")

    def send_bytes(self, body: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head_only(self, content_length: int, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.end_headers()

    def send_json(self, payload, status=200):
        self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_bytes(read_template("index.html"), "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            path = static_path(parsed.path)
            if not path:
                self.send_json({"error": "not found"}, 404)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self.send_bytes(path.read_bytes(), content_type)
            return
        if parsed.path == "/status":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            job = get_job(job_id)
            if not job:
                self.send_json({"error": "任务不存在"}, 404)
                return
            self.send_json(job)
            return
        if parsed.path == "/download":
            query = parse_qs(parsed.query)
            target = downloadable_path(query.get("path", [""])[0])
            if not target:
                self.send_json({"error": "文件不存在"}, 404)
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(target.name)}")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json({"error": "not found"}, 404)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_head_only((TEMPLATE_DIR / "index.html").stat().st_size, "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            path = static_path(parsed.path)
            if not path:
                self.send_head_only(0, "application/json; charset=utf-8", 404)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type == "application/javascript":
                content_type += "; charset=utf-8"
            self.send_head_only(path.stat().st_size, content_type)
            return
        if parsed.path == "/download":
            query = parse_qs(parsed.query)
            target = downloadable_path(query.get("path", [""])[0])
            if not target:
                self.send_head_only(0, "application/json; charset=utf-8", 404)
                return
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_head_only(target.stat().st_size, content_type)
            return
        self.send_head_only(0, "application/json; charset=utf-8", 404)

    def do_POST(self):
        try:
            payload = self.read_json()
            source = payload.get("source_dir", "")
            source_dir = Path(source).expanduser().resolve()
            if self.path == "/scan":
                if not source or not source_dir.exists() or not source_dir.is_dir():
                    self.send_json({"error": "源目录不存在或不是目录"}, 400)
                    return
                files, skipped = scan_files(source_dir)
                self.send_json({
                    "source_dir": str(source_dir),
                    "target_dir": str(target_dir_for(source_dir)),
                    "total": len(files),
                    "skipped_count": len(skipped),
                    "files": [str(f.relative_to(source_dir)) for f in files],
                    "skipped": skipped,
                    "supported_extension_counts": extension_counts(files),
                    "skipped_extension_counts": extension_counts(item["path"] for item in skipped),
                })
                return
            if self.path == "/start":
                if not source:
                    self.send_json({"error": "source_dir 不能为空"}, 400)
                    return
                job_id = uuid.uuid4().hex
                create_job(job_id)
                threading.Thread(target=run_job, args=(job_id, source), daemon=True).start()
                self.send_json({"job_id": job_id})
                return
            if self.path == "/reports/weekly":
                result = generate_weekly_report(
                    payload.get("ledger_path", ""),
                    payload.get("start_date", ""),
                    payload.get("end_date", ""),
                    payload.get("document_root", ""),
                )
                register_download(result.get("report_path"))
                register_download(result.get("word_path"))
                self.send_json(result)
                return
            if self.path == "/reports/generate":
                result = generate_report(
                    payload.get("report_type", ""),
                    payload.get("ledger_path", ""),
                    payload.get("start_date", ""),
                    payload.get("end_date", ""),
                    payload.get("document_root", ""),
                )
                register_download(result.get("report_path"))
                register_download(result.get("word_path"))
                self.send_json(result)
                return
            self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def serve(host=HOST, port=PORT):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Web 服务已启动：http://{host}:{port}")
    print("在网页中输入源目录路径，先扫描文件，再确认脱敏。按 Ctrl+C 停止服务。")
    server.serve_forever()
