#!/usr/bin/env python3
"""Send parsed Oracle analysis data to a local DeepSeek-compatible chat endpoint."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.oracle_analysis import DEFAULT_DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_URL, ask_local_deepseek, build_deepseek_prompt


DEFAULT_INPUT = Path("output/result.json")
DEFAULT_URL = DEFAULT_DEEPSEEK_URL
DEFAULT_MODEL = DEFAULT_DEEPSEEK_MODEL


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask local DeepSeek to analyze parsed Oracle data.")
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT, help=f"input JSON path, default: {DEFAULT_INPUT}")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"chat endpoint, default: {DEFAULT_URL}")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model name, default: {DEFAULT_MODEL}")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file does not exist: {args.input}")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    answer = ask_local_deepseek(args.url, args.model, build_deepseek_prompt(payload))
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
