"""命令行入口。"""

import argparse
import logging
import sys
from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Oracle TFA 日志自动分析工具 — 分析 TFA zip 包并生成 Word 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m oracle_tfa_analyzer.cli /path/to/tfa_orcl_20250101.zip
  python -m oracle_tfa_analyzer.cli /path/to/tfa_orcl_20250101.zip --output ./my_reports --keep-temp
        """,
    )
    parser.add_argument("zip_path", help="已脱敏的 Oracle TFA zip 包路径")
    parser.add_argument("--output", "-o", default=None, help="输出目录（默认 output/）")
    parser.add_argument("--keep-temp", action="store_true", help="保留临时解压目录")
    parser.add_argument("--verbose", "-v", action="store_true", help="输出调试日志")

    args = parser.parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        result = run_pipeline(args.zip_path, args.output, keep_temp=args.keep_temp)
        print()
        print("=" * 60)
        print("✅ 分析完成！")
        print(f"  证据文件: {result['evidence_path']}")
        print(f"  领导汇报版: {result['executive_path']}")
        print(f"  技术专家版: {result['technical_path']}")
        print(f"  共 {result['evidence_count']} 条证据，高风险 {result['risk_high']} 项，中风险 {result['risk_medium']} 项")
        print("=" * 60)
    except Exception as e:
        logging.exception("分析失败")
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
