# Oracle TFA Analyzer

本地运行的 Oracle TFA 日志自动分析工具。

## 功能

1. 输入已脱敏的 Oracle TFA zip 包
2. 程序在本地解压、扫描、分析，**不上传任何原始日志**
3. 自动识别并分析八大方向：
   - 数据库错误与稳定性
   - RAC/Clusterware
   - ASM/存储
   - OS 资源
   - I/O 性能
   - 连接/监听
   - SQL/性能争用
   - ADG/备份
4. 基于规则库提取证据，生成 `evidence.json`
5. 基于 `evidence.json` 生成两份 Word 报告：
   - **领导汇报版**：简洁、结论先行、突出风险等级和整改优先级
   - **技术专家版**：详细、包含日志证据、技术解释、建议命令和整改方案

## 安装

```bash
cd oracle-tfa-analyzer
pip install -r requirements.txt
```

## 使用

### CLI 命令行

```bash
python run.py /path/to/tfa_orcl_20250101.zip
python run.py /path/to/tfa_orcl_20250101.zip --output ./my_reports --keep-temp
```

### 作为模块

```bash
python -m oracle_tfa_analyzer.cli /path/to/tfa_orcl_20250101.zip
```

## 项目结构

```
oracle-tfa-analyzer/
├── requirements.txt
├── run.py
├── README.md
├── oracle_tfa_analyzer/
│   ├── __init__.py
│   ├── config.py
│   ├── extractor.py
│   ├── engine.py
│   ├── pipeline.py
│   ├── cli.py
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── db_stability.py
│   │   ├── rac_cluster.py
│   │   ├── asm_storage.py
│   │   ├── os_resource.py
│   │   ├── io_perf.py
│   │   ├── connection_listener.py
│   │   ├── sql_contention.py
│   │   └── adg_backup.py
│   └── reporting/
│       ├── __init__.py
│       ├── word_report.py
│       ├── executive_report.py
│       └── technical_report.py
├── tests/
└── sample_data/
```

## 设计原则

- **不编造事实**：所有结论必须能追溯到 evidence.json 中的证据
- **本地处理**：所有代码在本地运行，不上传任何数据
- **模块化**：规则可按方向独立扩展，不影响其他模块
- **可追溯**：每条证据都包含来源文件、行号、日志原文
- **清晰报告**：领导版结论先行，技术版证据密集
