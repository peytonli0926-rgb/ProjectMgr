"""
awr_auto_analyzer.llm_client — DeepSeek / Ollama 本地模型客户端

封装与本地大语言模型的通信，构造专业 AWR 分析 Prompt。
"""

import json
import os
import re
import socket
from datetime import datetime
from pathlib import Path
from urllib import error, request

from .config import DEFAULT_DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_URL, OUTPUT_DIR


# ── 模型发现 ──


def discover_local_models(url: str = DEFAULT_DEEPSEEK_URL) -> list[str]:
    """探索本地模型列表。"""
    if "/api/chat" in url:
        tags_url = url.replace("/api/chat", "/api/tags")
    elif "/v1/chat/completions" in url:
        tags_url = url.replace("/v1/chat/completions", "/v1/models")
    else:
        return []
    try:
        with request.urlopen(tags_url, timeout=5) as response:
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
    """获取首选模型名。"""
    models = discover_local_models(url)
    if DEFAULT_DEEPSEEK_MODEL in models:
        return DEFAULT_DEEPSEEK_MODEL
    for model in models:
        if "deepseek" in model.lower():
            return model
    return models[0] if models else DEFAULT_DEEPSEEK_MODEL


# ── Prompt 构造 ──


def compact_awr_for_prompt(parsed: dict) -> str:
    """将 AWR 解析结果压缩为适合 Prompt 的文本。"""
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
        lines.extend(
            [
                "",
                f"## {section.get('title')} (line {section.get('line')})",
                "\n".join(section.get("lines", [])[:35]),
            ]
        )
    if len("\n".join(lines)) < 3000:
        lines.extend(["", "报告开头摘录：", parsed.get("text_excerpt", "")[:6000]])
    return "\n".join(lines)[:24000]


def build_awr_prompt(summary_markdown: str, rule_findings_markdown: str, rules_guide_markdown: str = "") -> str:
    """
    构造用于调用 DeepSeek 的 AWR 分析 Prompt。

    Args:
        summary_markdown: AWR 结构化摘要 Markdown
        rule_findings_markdown: 规则引擎发现 Markdown（展开的详细段落格式）
        rules_guide_markdown: 规则定义说明文档（每条规则的阈值、逻辑、优化建议）

    Returns:
        完整的 Prompt 字符串
    """
    # ── 规则引用指令（当有规则发现数据时启用）──
    rule_citation_rules = (
        "\n"
        "【必须遵守的规则引用指令】\n"
        "下面提供了经过规则引擎自动分析的结果。你必须在以下章节中显式引用这些规则发现：\n"
        "\n"
        "1. **风险等级（第2节）**：必须引用规则引擎中标记为\"高\"或\"中高\"的规则，"
        "将其映射为风险项，并在\"证据\"列中标注对应的规则编号（如 R1、R9）。"
        "\n"
        "2. **数据库负载画像（第3节）**：必须引用规则 R1（AAS 负载）和 R2（CPU 型负载）的判断结果。"
        "\n"
        "3. **Top Wait Events 分析（第4节）**：必须引用规则 R3（Top 等待集中）、R4（关键等待事件阈值）、"
        "R8（RAC Global Cache）的判断结果。"
        "\n"
        "4. **Top SQL 分析（第5节）**：必须引用规则 R7（Top SQL 负载集中）、R16（Top SQL by Gets）、"
        "R17（Top SQL by Reads）、R18（高频执行 SQL）的判断结果。"
        "\n"
        "5. **内存与参数建议（第7节）**：必须引用规则 R12（Buffer Hit）、R13（Library Cache）、"
        "R14（Latch Hit）、R15（Soft Parse）、R5（Hard Parse）、R6（Execute to Parse）的判断结果。"
        "\n"
        "6. **问题点清单（第8节）**：必须引用所有等级为\"高\"或\"中高\"的规则，"
        "以及 IO 吞吐相关规则 R9-R11、Segment 热点规则 R19-R20。"
        "\n"
        "7. **总体结论（第1节）**：至少 2 条结论必须直接引用规则引擎的发现。"
        "\n"
        "格式要求：引用规则时使用「R1」格式标注规则编号，"
        "并在证据中引用具体数值。例如：「规则 R1 显示 AAS/CPU=0.85，已达高风险阈值（≥0.7），"
        "系统处于饱和状态。」\n"
    )

    # ── 规则定义摘要（当有 rules_guide 数据时启用）──
    rules_def_block = ""
    if rules_guide_markdown.strip():
        rules_def_block = (
            "\n"
            "以下是规则引擎中所有规则的完整定义（包括判断逻辑、阈值范围、数据来源、优化建议解读）：\n"
            "\n"
            f"{rules_guide_markdown[:12000]}\n"
        )

    return (
        "你是资深 Oracle 数据库性能诊断专家，正在为金融行业客户交付 Oracle AWR 性能分析报告。"
        "只能使用下面提供的结构化 AWR 摘要、规则引擎发现和规则定义，不要编造未提供的指标；"
        "证据不足时必须明确写\"证据不足，不做强判断\"。\n\n"
        "硬性要求：\n"
        "1. 必须使用中文，语气正式、专业、适合金融行业客户交付。\n"
        "2. 总体结论最多 5 条，每条必须引用具体 AWR 指标。\n"
        "3. SQL 分析必须保留 SQL ID，并引用 Elapsed Time、CPU Time、Executions、Buffer Gets、Disk Reads 等已有指标。\n"
        "4. 必须区分 CPU 型、IO 型、等待型、逻辑读型、执行次数型、解析型、RAC 等待型负载。\n"
        "5. 如果 SQL Text 有 ROWNUM、全表扫描、聚合、排序、关联、分区表、监控 SQL 等特征，要明确指出。\n"
        "6. 不要输出代码块、寒暄或解释提示词。\n"
        f"{rule_citation_rules}"
        "请严格按以下 Markdown 结构输出：\n\n"
        "# Oracle AWR 性能分析报告\n\n"
        "## 1. 总体结论\n"
        "必须 5 条以内，每条引用具体 AWR 指标。至少 2 条必须引用规则引擎发现（标注 R 编号）。\n\n"
        "## 2. 风险等级\n"
        "| 风险项 | 风险等级 | 证据（含规则编号） | 影响 |\n"
        "| --- | --- | --- | --- |\n\n"
        "## 3. 数据库负载画像\n"
        "必须分析 DB Time、DB CPU、AAS、Host CPU、Load Profile，并判断 CPU 型 / IO 型 / 等待型。"
        "引用规则 R1、R2 的判断结果。\n\n"
        "## 4. Top Wait Events 分析\n"
        "逐条分析前 5 个等待事件，引用规则 R3、R4、R8 的判断结果：\n"
        "| Event | Wait Class | 指标 | 是否异常 | 规则编号 | 判断 | 建议 |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n\n"
        "## 5. Top SQL 分析\n"
        "逐条分析至少前 5 个 SQL，引用规则 R7、R16、R17、R18 的判断结果：\n"
        "| SQL ID | 消耗类型 | 关键指标 | 规则编号 | 问题判断 | 优化建议 |\n"
        "| --- | --- | --- | --- | --- | --- |\n\n"
        "## 6. 主机资源分析\n"
        "结合 Host CPU、Load Average、等待事件判断 CPU / IO / 系统负载问题。\n\n"
        "## 7. 内存与参数建议\n"
        "分析 Buffer Cache、Shared Pool、PGA、SGA Advisory，引用规则 R12、R13、R14、R15、R5、R6 的判断结果；"
        "证据不足时明确说明。\n\n"
        "## 8. 问题点清单\n"
        "| 序号 | 问题点 | 规则编号 | 严重等级 | 证据 | 建议 |\n"
        "| --- | --- | --- | --- | --- | --- |\n\n"
        "## 9. 整改建议\n"
        "分为短期建议、中期建议、长期建议，标注对应的规则编号。\n\n"
        "## 10. 后续取证清单\n"
        "列出 ASH、alert.log、listener.log、OS sar/nmon、SQL 执行计划、绑定变量、对象统计信息、批处理时间表、AWR 前后基线对比。\n\n"
        "## 11. 领导汇报摘要\n"
        "5 条以内，用管理语言表达，引用关键规则编号。\n\n"
        "## 12. 专家交付结论\n"
        "用正式技术语言总结，引用主要规则发现。\n\n"
        "以下是结构化 AWR 摘要：\n"
        f"{summary_markdown[:60000]}\n\n"
        "以下是规则引擎发现（逐条展开的详细分析结果）：\n"
        f"{rule_findings_markdown[:16000]}\n\n"
        f"{rules_def_block}"
    )


# ── API 调用 ──


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
    try:
        with request.urlopen(req, timeout=timeout) as response:
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
    try:
        with request.urlopen(req, timeout=timeout) as response:
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

    Args:
        url: API 地址
        model: 模型名称
        prompt: 提示词
        api_key: OpenAI 兼容 API 的密钥（可选）
        timeout: 超时秒数

    Returns:
        模型回答文本
    """
    if "/api/chat" in url:
        return _ask_ollama(url, model, prompt, timeout)
    return _ask_openai(url, model, prompt, api_key, timeout)


def ask_local_deepseek(url: str, model: str, prompt: str, timeout: int = 600) -> str:
    """兼容旧版调用（仅 Ollama 协议，无 API Key）。"""
    return ask_llm(url, model, prompt, api_key="", timeout=timeout)
