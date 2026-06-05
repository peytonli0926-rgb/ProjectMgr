#!/usr/bin/env python3
"""Parse an Oracle .lst report into a JSON summary."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.oracle_analysis import DEFAULT_LST, find_latest_lst, parse_lst


DEFAULT_INPUT = DEFAULT_LST
DEFAULT_OUTPUT = Path("output/result.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse Oracle .lst report into JSON.")
    parser.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT, help=f"input .lst path, default: {DEFAULT_INPUT}")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT, help=f"output JSON path, default: {DEFAULT_OUTPUT}")
    parser.add_argument("--latest", action="store_true", help="parse the latest .lst under the input file's directory")
    args = parser.parse_args()

    if args.latest:
        latest = find_latest_lst(args.input.parent)
        if not latest:
            raise SystemExit(f"No .lst file found under: {args.input.parent}")
        args.input = latest

    if not args.input.exists():
        raise SystemExit(f"Input file does not exist: {args.input}")

    result = parse_lst(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
