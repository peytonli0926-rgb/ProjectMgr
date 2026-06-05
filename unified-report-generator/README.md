# Unified Report Generator — 统一报告生成模块

从 Excel 服务台账自动生成 Markdown / Word (.docx) 服务交付报告。

## 功能特性

- **Excel 台账读取** — 支持「一线支持」「二线支持」工作表
- **报告类型** — 周报、月报、季度报、年度报
- **交付文档提取** — 自动搜索并提取 .docx / .pptx / .xlsx / .txt / .md / .log 文件内容
- **Markdown 报告** — 生成结构化的 MD 报告
- **Word 报告** — 生成金融风格 .docx 文档（含封面、目录、表格、品牌色）
- **AI 增强** — 可选 LLM 润色 + 统计图表（matplotlib）

## 安装

```bash
pip install openpyxl
# AI 增强需要额外安装：
pip install matplotlib
```

## 快速开始

```python
from unified_report_generator import generate_report

result = generate_report(
    report_type="weekly",
    ledger_path="/path/to/ledger.xlsx",
    start_date_text="2025-01-01",
    end_date_text="2025-01-07",
)
print(f"Markdown: {result['report_path']}")
print(f"Word: {result['word_path']}")
```

## AI 增强报告

```python
from unified_report_generator import generate_report_with_ai

result = generate_report_with_ai(
    report_type="monthly",
    ledger_path="/path/to/ledger.xlsx",
    start_date_text="2025-01-01",
    end_date_text="2025-01-31",
    url="http://localhost:11434/api/chat",  # Ollama 或 OpenAI 兼容 API
    model="deepseek-r1:14b",
)
```

## 配置

默认报告输出目录可通过环境变量 `UNIFIED_REPORT_TMP_DIR` 或在代码中调用 `set_reports_dir()` 设置：

```python
from unified_report_generator import set_reports_dir
set_reports_dir("/custom/report/output/path")
```
