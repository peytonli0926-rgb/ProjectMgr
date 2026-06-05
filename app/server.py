import json
import mimetypes
import re
import socket
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .config import HOST, PORT, TMP_DIR, TMP_UPLOADS, TMP_TFA_UPLOAD, TMP_TFA_TEMP
from .awr_word_report import markdown_to_word
from .jobs import create_job, get_job, run_job, create_tfa_job, get_tfa_job, run_tfa_job
from .oracle_analysis import (
    AWR_DATA_DIR,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_DEEPSEEK_URL,
    analyze_awr_with_deepseek,
    analyze_lst_with_deepseek,
    discover_local_models,
    find_latest_lst,
    list_awr_files,
    list_lst_files,
    list_report_templates,
    preferred_model,
    safe_template_path,
)
from .processor import extension_counts, redact_single_file, scan_files, target_dir_for
from .reporting import generate_report, generate_report_with_ai, generate_weekly_report

# ── DeepSeek 配置持久化（双面板：本地 + 联网） ──
DEEPSPEK_CONFIG_PATH: Path = TMP_DIR / "deepseek_config.json"
_DEFAULT_ONLINE_URL = "https://api.deepseek.com/chat/completions"
_DEFAULT_ONLINE_MODEL = "deepseek-chat"


def _default_deepseek_config() -> dict:
    """返回默认双面板配置结构。"""
    return {
        "active_mode": "local",
        "local": {"url": "", "model": ""},
        "online": {"url": _DEFAULT_ONLINE_URL, "model": _DEFAULT_ONLINE_MODEL, "api_key": ""},
    }


def load_deepseek_config() -> dict:
    """读取已保存的 DeepSeek 双面板配置。"""
    try:
        if DEEPSPEK_CONFIG_PATH.exists():
            raw = json.loads(DEEPSPEK_CONFIG_PATH.read_text(encoding="utf-8"))
            # 兼容旧版单面板配置（url / model / api_key 顶级字段）
            if "active_mode" not in raw:
                return {
                    "active_mode": "local",
                    "local": {"url": raw.get("url", ""), "model": raw.get("model", "")},
                    "online": {
                        "url": _DEFAULT_ONLINE_URL,
                        "model": _DEFAULT_ONLINE_MODEL,
                        "api_key": raw.get("api_key", ""),
                    },
                }
            return raw
    except Exception:
        pass
    return _default_deepseek_config()


def save_deepseek_config(config: dict) -> dict:
    """将 DeepSeek 双面板配置持久化到磁盘。"""
    # 确保结构完整
    ensured = {
        "active_mode": config.get("active_mode", "local"),
        "local": {
            "url": (config.get("local", {})).get("url", ""),
            "model": (config.get("local", {})).get("model", ""),
        },
        "online": {
            "url": (config.get("online", {})).get("url", _DEFAULT_ONLINE_URL),
            "model": (config.get("online", {})).get("model", _DEFAULT_ONLINE_MODEL),
            "api_key": (config.get("online", {})).get("api_key", ""),
        },
    }
    DEEPSPEK_CONFIG_PATH.write_text(
        json.dumps(ensured, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ensured


def resolve_active_deepseek_config(cfg: dict) -> tuple:
    """从双面板配置中解析当前生效的 (url, model, api_key)。"""
    active = cfg.get("active_mode", "local")
    panel = cfg.get(active, {})
    url = panel.get("url", "") or ""
    model = panel.get("model", "") or ""
    api_key = panel.get("api_key", "") if active == "online" else ""
    return url, model, api_key

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
ALLOWED_DOWNLOADS = set()
ALLOWED_DOWNLOADS_LOCK = threading.Lock()

# ── TFA 分析（oracle-tfa-analyzer 子项目） ──
import sys as _sys
_TFA_ROOT = ROOT / "oracle-tfa-analyzer"
if _TFA_ROOT.exists() and (_TFA_ROOT / "oracle_tfa_analyzer").exists():
    _sys.path.insert(0, str(_TFA_ROOT))
    from oracle_tfa_analyzer.pipeline import run_pipeline as _tfa_run_pipeline
    # TFA zip 上传目录 → 统一存到 TMP_TFA_UPLOAD
    TFA_UPLOAD_DIR = TMP_TFA_UPLOAD
else:
    _tfa_run_pipeline = None
    TFA_UPLOAD_DIR = TMP_TFA_UPLOAD


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


def uploaded_awr_path(filename: str) -> Path:
    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".html", ".htm"}:
        raise ValueError("仅支持上传 .html 或 .htm 格式的 AWR 报告")
    AWR_DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = AWR_DATA_DIR / safe_name
    if not target.exists():
        return target
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return AWR_DATA_DIR / f"{target.stem}_{timestamp}{target.suffix}"


def parse_multipart_file(headers, body: bytes, field_name: str):
    content_type = headers.get("Content-Type", "")
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("上传请求缺少 multipart boundary")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = ("--" + boundary).encode("utf-8")
    for part in body.split(delimiter):
        part = part.strip(b"\r\n")
        if not part or part == b"--" or b"\r\n\r\n" not in part:
            continue
        header_blob, data = part.split(b"\r\n\r\n", 1)
        header_text = header_blob.decode("utf-8", errors="replace")
        if f'name="{field_name}"' not in header_text:
            continue
        filename_match = re.search(r'filename="([^"]+)"', header_text)
        if not filename_match:
            raise ValueError("上传文件缺少文件名")
        return filename_match.group(1), data.rstrip(b"\r\n")
    raise ValueError("未找到上传文件字段")


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
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(path.read_bytes())
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
        if parsed.path == "/oracle/lst-files":
            models = discover_local_models(DEFAULT_DEEPSEEK_URL)
            saved_cfg = load_deepseek_config()
            self.send_json({
                "files": list_lst_files(),
                "awr_files": list_awr_files(),
                "templates": list_report_templates(),
                "default_url": DEFAULT_DEEPSEEK_URL,
                "default_model": preferred_model(DEFAULT_DEEPSEEK_URL),
                "models": models,
                "saved_config": saved_cfg,
            })
            return
        if parsed.path == "/oracle/load-deepseek-config":
            self.send_json(load_deepseek_config())
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
        if parsed.path == "/tfa/status":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            job = get_tfa_job(job_id)
            if not job:
                self.send_json({"error": "TFA 分析任务不存在"}, 404)
                return
            self.send_json(job)
            return
        if parsed.path == "/tfa/timeline":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            job = get_tfa_job(job_id)
            if not job:
                self.send_json({"error": "TFA 分析任务不存在"}, 404)
                return
            result: dict = job.get("result") or {}
            timeline_data: dict = result.get("timeline_data") or {}
            if not timeline_data or not timeline_data.get("fault_clusters"):
                self.send_json({"timeline_events": [], "fault_clusters": [], "metadata": {
                    "total_evidence": 0, "files_analyzed": 0, "clusters_found": 0,
                    "severity_summary": {}, "analyzed_at": "",
                }})
                return
            self.send_json(timeline_data)
            return
        if parsed.path == "/tfa/analysis-chains":
            query = parse_qs(parsed.query)
            job_id = query.get("job_id", [""])[0]
            job = get_tfa_job(job_id)
            if not job:
                self.send_json({"error": "TFA 分析任务不存在"}, 404)
                return
            result: dict = job.get("result") or {}
            chains: list = result.get("analysis_chains") or []
            self.send_json(chains)
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
            if self.path == "/oracle/upload-awr":
                length = int(self.headers.get("Content-Length", "0"))
                filename, data = parse_multipart_file(self.headers, self.rfile.read(length), "awr_file")
                target = uploaded_awr_path(filename)
                target.write_bytes(data)
                self.send_json({
                    "message": "上传成功",
                    "file": {
                        "path": str(target),
                        "name": target.name,
                        "size": target.stat().st_size,
                        "modified_at": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
                    }
                })
                return
            if self.path == "/tfa/upload":
                length = int(self.headers.get("Content-Length", "0"))
                filename, data = parse_multipart_file(self.headers, self.rfile.read(length), "tfa_file")
                safe_name = Path(filename).name
                if not safe_name.lower().endswith(".zip"):
                    raise ValueError("仅支持上传 .zip 格式的 TFA 包")
                TFA_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                target = TFA_UPLOAD_DIR / safe_name
                if target.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    target = TFA_UPLOAD_DIR / f"{target.stem}_{timestamp}.zip"
                target.write_bytes(data)
                self.send_json({
                    "message": "上传成功",
                    "file_path": str(target),
                    "file_name": target.name,
                })
                return
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
            if self.path == "/redact-file":
                file_path = payload.get("file_path", "")
                if not file_path:
                    self.send_json({"error": "file_path 不能为空"}, 400)
                    return
                result = redact_single_file(Path(file_path).expanduser().resolve())
                register_download(result.get("target_file"))
                register_download(result.get("report_path"))
                self.send_json(result)
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
                url = (payload.get("url") or "").strip()
                model = (payload.get("model") or "").strip()
                api_key = (payload.get("api_key") or "").strip()

                if url and model:
                    result = generate_report_with_ai(
                        payload.get("report_type", ""),
                        payload.get("ledger_path", ""),
                        payload.get("start_date", ""),
                        payload.get("end_date", ""),
                        payload.get("document_root", ""),
                        url=url,
                        model=model,
                        api_key=api_key,
                    )
                else:
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
            if self.path == "/oracle/save-deepseek-config":
                config = {
                    "active_mode": (payload.get("active_mode") or "local").strip(),
                    "local": {
                        "url": ((payload.get("local") or {}).get("url") or "").strip(),
                        "model": ((payload.get("local") or {}).get("model") or "").strip(),
                    },
                    "online": {
                        "url": ((payload.get("online") or {}).get("url") or "").strip(),
                        "model": ((payload.get("online") or {}).get("model") or "").strip(),
                        "api_key": ((payload.get("online") or {}).get("api_key") or "").strip(),
                    },
                }
                if not config["local"]["url"] and not config["online"]["url"]:
                    self.send_json({"error": "请至少配置一个接口地址"}, 400)
                    return
                saved = save_deepseek_config(config)
                self.send_json({"message": "DeepSeek 配置已保存", "config": saved})
                return

            if self.path == "/oracle/analyze":
                use_latest = bool(payload.get("use_latest"))
                lst_path = payload.get("lst_path", "")
                target = find_latest_lst() if use_latest or not lst_path else Path(lst_path).expanduser().resolve()
                if not target:
                    self.send_json({"error": "未找到 .lst 文件"}, 400)
                    return
                if not target.exists() or not target.is_file() or target.suffix.lower() != ".lst":
                    self.send_json({"error": "请选择有效的 .lst 文件"}, 400)
                    return
                # 优先使用请求中传入的配置，其次使用已保存的配置（双面板），最后使用默认值
                saved_cfg = load_deepseek_config()
                _active_url, _active_model, _active_api_key = resolve_active_deepseek_config(saved_cfg)
                url = payload.get("url") or _active_url or DEFAULT_DEEPSEEK_URL
                model = payload.get("model") or _active_model or preferred_model(url)
                api_key = payload.get("api_key") or _active_api_key
                available_models = discover_local_models(url)
                if available_models and model not in available_models:
                    model = preferred_model(url)
                template_path = safe_template_path(payload.get("template_path"))
                result = analyze_lst_with_deepseek(target, url, model, template_path, api_key=api_key)
                register_download(result.get("json_path"))
                register_download(result.get("markdown_path"))
                register_download(result.get("word_path"))
                self.send_json({
                    "source_file": result["source_file"],
                    "generated_at": result["generated_at"],
                    "json_path": result["json_path"],
                    "markdown_path": result["markdown_path"],
                    "word_path": result["word_path"],
                    "parsed_summary": {
                        "windows": result["parsed"].get("windows", {}),
                        "sections": len(result["parsed"].get("sections", [])),
                        "tables": len(result["parsed"].get("tables", [])),
                        "line_count": result["parsed"].get("line_count", 0),
                    },
                    "deepseek_answer": result["deepseek"]["answer"],
                    "template": result.get("template"),
                })
                return
            if self.path == "/oracle/analyze-awr":
                awr_path = payload.get("awr_path", "")
                if not awr_path:
                    self.send_json({"error": "awr_path 不能为空"}, 400)
                    return
                target = Path(awr_path).expanduser().resolve()
                if not target.exists() or not target.is_file() or target.suffix.lower() not in {".html", ".htm", ".txt", ".lst"}:
                    self.send_json({"error": "请选择有效的 AWR 报告文件，支持 .html、.htm、.txt、.lst"}, 400)
                    return
                # 优先使用请求中传入的配置，其次使用已保存的配置（双面板），最后使用默认值
                saved_cfg = load_deepseek_config()
                _active_url, _active_model, _active_api_key = resolve_active_deepseek_config(saved_cfg)
                url = payload.get("url") or _active_url or DEFAULT_DEEPSEEK_URL
                model = payload.get("model") or _active_model or preferred_model(url)
                api_key = payload.get("api_key") or _active_api_key
                available_models = discover_local_models(url)
                if available_models and model not in available_models:
                    model = preferred_model(url)
                template_path = safe_template_path(payload.get("template_path"))
                result = analyze_awr_with_deepseek(target, url, model, template_path, api_key=api_key)
                summary = result.get("summary", {})
                rule_findings = result.get("rule_findings", {})
                register_download(summary.get("markdown_path"))
                register_download(summary.get("json_path"))
                register_download(rule_findings.get("markdown_path"))
                register_download(rule_findings.get("json_path"))
                register_download(result.get("json_path"))
                register_download(result.get("markdown_path"))
                register_download(result.get("word_path"))
                self.send_json({
                    "source_file": result["source_file"],
                    "generated_at": result["generated_at"],
                    "summary_json_path": summary["json_path"],
                    "summary_markdown_path": summary["markdown_path"],
                    "rule_findings_json_path": rule_findings["json_path"],
                    "rule_findings_markdown_path": rule_findings["markdown_path"],
                    "markdown_path": result["markdown_path"],
                    "json_path": result["json_path"],
                    "word_path": result["word_path"],
                    "parsed_summary": {
                        "line_count": result["parsed"].get("line_count", 0),
                        "sections": len(result["parsed"].get("sections", [])),
                        "tables": len(result["parsed"].get("tables", [])),
                        "windows": {},
                    },
                    "deepseek_answer": result["deepseek"]["answer"],
                    "template": result.get("template"),
                    "model": model,
                    "message": "AWR 分析完成",
                })
                return
            if self.path == "/oracle/awr-word-report":
                try:
                    result = markdown_to_word()
                except FileNotFoundError as exc:
                    self.send_json({"error": str(exc)}, 400)
                    return
                register_download(result.get("word_path"))
                self.send_json(result)
                return
            if self.path == "/tfa/analyze":
                if _tfa_run_pipeline is None:
                    self.send_json({"error": "oracle-tfa-analyzer 子项目未就绪"}, 500)
                    return
                zip_path = payload.get("zip_path", "")
                if not zip_path:
                    self.send_json({"error": "zip_path 不能为空"}, 400)
                    return
                time_filter_days = payload.get("time_filter_days")
                time_start = payload.get("time_start")
                time_end = payload.get("time_end")
                first_match_only = payload.get("first_match_only", False)
                if time_filter_days is not None:
                    time_filter_days = int(time_filter_days)
                job_id = uuid.uuid4().hex
                create_tfa_job(job_id, zip_path)
                kwargs = {}
                if time_filter_days is not None:
                    kwargs["time_filter_days"] = time_filter_days
                if time_start and time_end:
                    kwargs["time_start"] = time_start
                    kwargs["time_end"] = time_end
                if first_match_only:
                    kwargs["first_match_only"] = True
                threading.Thread(
                    target=run_tfa_job,
                    args=(job_id, zip_path),
                    kwargs=kwargs,
                    daemon=True,
                ).start()
                self.send_json({"job_id": job_id})
                return
            self.send_json({"error": "not found"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def serve(host=HOST, port=PORT):
    server = ThreadingHTTPServer((host, port), Handler)
    server.allow_reuse_address = True
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    print(f"Web 服务已启动：http://{host}:{port}")
    print("在网页中输入源目录路径，先扫描文件，再确认脱敏。按 Ctrl+C 停止服务。")
    server.serve_forever()
