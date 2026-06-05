# awr-auto-analyzer

Oracle AWR 性能分析自动化工具。解析 HTML 格式的 AWR 报告，通过规则引擎和本地大语言模型（DeepSeek / Ollama）自动生成专业的性能分析报告（Markdown + Word）。

## 功能

- **AWR HTML 解析** — 自动解析 AWR 报告，提取 Load Profile、等待事件、Top SQL、Segment、Advisory 等关键信息
- **规则引擎分析** — 内置 8 类规则引擎，自动判断 AAS 负载、CPU/IO 型负载、等待事件风险、Hard Parse、游标复用、RAC gc 等
- **LLM 智能分析** — 结合结构化摘要和规则发现，调用本地 DeepSeek/Ollama 模型生成专业的 12 章节 AWR 分析报告
- **Word 报告生成** — 自动生成格式精美的 Word 文档，含封面、结论摘要、风险色标、斑马纹表格

## 安装

```bash
cd awr-auto-analyzer
pip install -r requirements.txt
```

## 用法

```bash
# 完整分析（需要本地运行 DeepSeek / Ollama）
python run.py /path/to/awr_report.html

# 仅解析 + 规则引擎（跳过 LLM）
python run.py /path/to/awr_report.html --skip-llm

# 指定模型和地址
python run.py /path/to/awr_report.html \
    --model deepseek-r1:14b \
    --url http://127.0.0.1:11434/api/chat

# 仅 Markdown → Word 转换
python run.py --to-word

# 发现本地可用模型
python run.py --discover-models

# 指定输出目录
python run.py /path/to/awr_report.html --output /tmp/awr_output

# JSON 格式输出
python run.py /path/to/awr_report.html --skip-llm --json
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `output/awr_summary.json` | AWR 结构化摘要（JSON） |
| `output/awr_summary.md` | AWR 结构化摘要（Markdown） |
| `output/awr_rule_findings.json` | 规则引擎发现（JSON） |
| `output/awr_rule_findings.md` | 规则引擎发现（Markdown） |
| `output/awr_analysis_report.md` | LLM 生成的完整分析报告 |
| `output/awr_analysis_report.docx` | 格式化的 Word 报告 |

## 规则引擎

内置 8 类规则：

1. **AAS 负载** — AAS/CPU 比值，判断系统饱和度
2. **CPU 型负载** — DB CPU / DB Time 比值
3. **Top 等待集中** — Top 1 等待事件占 DB Time 比例
4. **关键等待阈值** — log file sync、db file sequential read 等 5 类等待延迟
5. **Hard Parse** — 硬解析速率
6. **Execute to Parse** — 游标复用效率
7. **Top SQL 集中度** — 单条 SQL 消耗占比
8. **RAC Global Cache** — gc 等待占比

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AWR_OUTPUT_DIR` | `./output` | 输出目录 |
| `AWR_DATA_DIR` | `./data` | 数据目录 |
| `LOCAL_DEEPSEEK_URL` | `http://127.0.0.1:11434/api/chat` | LLM API 地址 |
| `LOCAL_DEEPSEEK_MODEL` | `deepseek-r1` | 默认模型名称 |

## 目录结构

```
awr-auto-analyzer/
├── run.py                        # CLI 入口
├── requirements.txt              # 依赖
├── README.md                     # 使用说明
├── awr_auto_analyzer/            # 核心包
│   ├── __init__.py               # 包初始化
│   ├── config.py                 # 全局配置
│   ├── parser.py                 # AWR HTML 解析引擎
│   ├── analyzer.py               # 规则引擎分析
│   ├── llm_client.py             # DeepSeek LLM 客户端
│   └── reporter.py               # Markdown + Word 报告生成
├── data/                         # 数据目录（可配置）
└── output/                       # 输出目录（可配置）
```

## 依赖

- Python 3.10+
- python-docx — Word 报告生成
- pandas — 表格解析
- beautifulsoup4 — HTML 解析
- lxml — HTML 解析加速
