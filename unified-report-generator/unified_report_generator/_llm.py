"""
unified_report_generator._llm — LLM API 客户端

standalone 版本的 AI 调用模块，从 ..app.oracle_analysis 中提取的 ask_llm 实现。
支持 Ollama 和 OpenAI 兼容 API 两种协议。
"""

import json
import socket
from urllib import error, request


def _get_ssl_context():
    """创建宽松的 SSL 上下文，允许自签名证书。"""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _ask_ollama(url: str, model: str, prompt: str, timeout: int = 600) -> str:
    """调用 Ollama /api/chat 协议。"""
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
    """调用 OpenAI 兼容 API（/v1/chat/completions 协议）。"""
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
