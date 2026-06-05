#!/usr/bin/env python3
"""
awr-auto-analyzer — Oracle AWR 性能分析自动化工具

命令行入口。支持三种模式：
1. 完整分析（解析 + 规则引擎 + LLM + 报告）
2. 仅解析 + 规则引擎（无 LLM）
3. 仅 Markdown → Word 转换

用法：
    python run.py <awr_html_path> [--model MODEL] [--url URL] [--skip-llm]
    python run.py --to-word [--markdown PATH]
    python run.py --discover-models
"""

import argparse
import json
import sys
from pathlib import Path

# 确保包在路径中
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def main():
    parser = argparse.ArgumentParser(
        description="Oracle AWR 性能分析自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  # 完整分析\n"
            "  python run.py /path/to/awr_report.html\n\n"
            "  # 仅解析 + 规则引擎（跳过 LLM）\n"
            "  python run.py /path/to/awr_report.html --skip-llm\n\n"
            "  # 指定模型和地址\n"
            "  python run.py /path/to/awr_report.html --model deepseek-r1:14b --url http://127.0.0.1:11434/api/chat\n\n"
            "  # 仅 Markdown → Word\n"
            "  python run.py --to-word\n\n"
            "  # 查看可用模型\n"
            "  python run.py --discover-models\n"
        ),
    )

    # 模式
    parser.add_argument("awr_path", nargs="?", help="AWR HTML 报告路径")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM 分析，仅执行解析和规则引擎")
    parser.add_argument("--to-word", action="store_true", help="仅将已有 Markdown 报告转为 Word")
    parser.add_argument("--markdown", help="Markdown 报告路径（与 --to-word 配合）")
    parser.add_argument("--discover-models", action="store_true", help="发现本地可用模型")

    # LLM 参数
    parser.add_argument("--model", help="DeepSeek / Ollama 模型名称")
    parser.add_argument("--url", help="模型 API 地址（默认：http://127.0.0.1:11434/api/chat）")
    parser.add_argument("--output", help="输出目录（默认：./output）")

    # 输出格式
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果摘要")

    args = parser.parse_args()

    # ── 模式 1：发现本地模型 ──
    if args.discover_models:
        from awr_auto_analyzer.llm_client import discover_local_models, preferred_model

        models = discover_local_models(args.url)
        print(f"🌐 API 地址：{args.url or '默认'}")
        print(f"📋 可用模型（{len(models)} 个）：")
        for m in models:
            print(f"   - {m}")
        if models:
            print(f"\n👉 推荐模型：{preferred_model(args.url)}")
        return

    # ── 模式 2：仅 Markdown → Word ──
    if args.to_word:
        from awr_auto_analyzer.reporter import markdown_to_word

        if args.output:
            from awr_auto_analyzer.config import AWR_ANALYSIS_DOCX

            # 重新设置路径有点复杂，直接用传参概念
        result = markdown_to_word(Path(args.markdown) if args.markdown else None)
        print(f"✅ Word 报告生成成功：{result['word_path']}")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ── 模式 3：完整分析 ──
    if not args.awr_path:
        parser.print_help()
        sys.exit(1)

    from awr_auto_analyzer.reporter import run_full_analysis

    if args.output:
        import os

        os.environ["AWR_OUTPUT_DIR"] = args.output

    result = run_full_analysis(
        awr_path=args.awr_path,
        url=args.url,
        model=args.model,
        skip_llm=args.skip_llm,
    )

    # 输出摘要
    summary = result.get("summary", {})
    rule_findings = result.get("rule_findings", {})
    llm = result.get("llm_analysis")

    print(f"\n{'='*60}")
    print(f"📊 AWR 分析完成摘要")
    print(f"{'='*60}")
    print(f"  源文件    : {result['source_file']}")
    print(f"  生成时间   : {result['generated_at']}")
    print(f"  Markdown  : {result.get('markdown_path', 'N/A')}")
    print(f"  Word      : {result.get('word_path', 'N/A')}")
    print(f"  规则发现  : {len(rule_findings.get('findings', []))} 条")
    if llm:
        print(f"  LLM 模型  : {llm.get('model', 'N/A')}")
        answer = llm.get("answer", "")
        print(f"  LLM 回答  : {len(answer)} 字符")

    if args.json:
        # 精简输出
        output = {
            "source_file": result["source_file"],
            "generated_at": result["generated_at"],
            "markdown_path": result.get("markdown_path"),
            "word_path": result.get("word_path"),
            "rule_findings_count": len(rule_findings.get("findings", [])),
            "computed_metrics": rule_findings.get("computed_metrics", {}),
        }
        print("\n" + json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
