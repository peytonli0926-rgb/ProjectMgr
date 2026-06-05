# ProjectMgr — 统一服务管理平台 PRD

*原始版本：2025-03-26 · 最后更新：2025-03-26*

---

## 目录

- [1. 产品定位](#1-产品定位)
- [2. 目标用户](#2-目标用户)
- [3. 架构总览](#3-架构总览)
- [4. 模块详情](#4-模块详情)
  - [4.1 文件扫描与脱敏](#41-文件扫描与脱敏-data-shield)
  - [4.2 统一报告生成](#42-统一报告生成)
  - [4.3 Oracle AWR 性能分析](#43-oracle-awr-性能分析)
  - [4.4 TFA 日志自动分析](#44-tfa-日志自动分析)
  - [4.5 DeepSeek 模型管理](#45-deepseek-模型管理)
  - [4.6 前端界面](#46-前端界面)
- [5. 技术栈](#5-技术栈)
- [6. 安全与合规](#6-安全与合规)
- [7. 已知限制与未来方向](#7-已知限制与未来方向)
- [8. 核心数据流](#8-核心数据流)

---

## 1. 产品定位

ProjectMgr 是一个面向 Oracle 数据库运维团队和金融科技服务部门的本地化统一工作台。它将**文件脱敏、Oracle 性能分析（AWR / .lst）、TFA 日志分析、周报/月报/季度报自动生成**四个场景整合到一套 Web 界面中，**所有数据处理均在本地完成，不上传任何原始数据**。

---

## 2. 目标用户

| 角色 | 核心场景 |
|------|----------|
| **数据库管理员（DBA）** | AWR 性能分析、TFA 故障日志分析、SQL 优化 |
| **服务交付经理** | 生成统一周报/月报/季度报，关联台账与交付文档 |
| **安全合规专员** | 对包含敏感信息的文件/日志目录批量脱敏 |
| **运维工程师** | 本地 DeepSeek 模型驱动的自动化报告生成 |

---

## 3. 架构总览

```
                    ┌─────────────────────────────┐
                    │   前端：static/app.js        │
                    │   Single-page 工作台         │
                    │   HTTP GET/POST 与后端交互    │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │   后端：app/server.py        │
                    │   Python http.server         │
                    │   线程池并发                 │
                    └─────────────┬───────────────┘
                                  │
        ┌──────────┬──────────────┼──────────────┬──────────────┐
        ▼          ▼              ▼              ▼              ▼
  扫描脱敏    统一报告       AWR 分析        TFA 分析      DeepSeek
  processor   reporting    oracle_analysis  pipeline       API 调用
  .py         .py          .py             (子项目)        (远程)
  rules.py    jobs.py      awr_word_                     scripts/
                            report.py
```

---

## 4. 模块详情

### 4.1 文件扫描与脱敏（Data Shield）

**核心文件**：`app/processor.py`、`app/rules.py`

**功能**：
- 输入一个本地目录，递归扫描全部文件（不限扩展名）
- 在父目录创建 `_desensitized` 副本目录，逐文件处理
- Office 文件（`.docx` / `.pptx` / `.xlsx`）：解包 → 脱敏 XML 文本节点 → 重新打包
- 文本/HTML 文件：尝试多编码（utf-8 / gb18030 / latin-1）解码 → 正则替换敏感信息
- 支持单文件脱敏：直接对单个文件生成 `*_desensitized.*` 副本

**敏感信息规则（约 60 条正则）**：
- **个人信息**：身份证（15/18 位）、护照、港澳台证件、手机号、电话、邮箱、车牌
- **金融信息**：银行卡号（13-19位）、Swift/BIC 码、CNAPS 码、证券账户、股票/基金代码
- **商务信息**：信用代码、合同号、交易号、发票号、纳税人号
- **网络信息**：IP（v4/v6）、MAC、URL、主机域名
- **数据库信息**：Oracle SID / HOME / SYS密码类、数据文件路径、ASM 磁盘组
- **结构化字段**（JSON/YAML/XML 中按 key 名匹配）：密码类、姓名、地址、定位、生日、账户、金额、利率、评分、公司名、法定代表人、反洗钱标识、医疗信息、生物识别、宗教、未成年人信息

**规则引擎格式**：
```python
("rule_name", re.compile(r"正则表达式"), "<REPLACEMENT_TAG>")
```

---

### 4.2 统一报告生成

**核心文件**：`app/reporting.py`

**功能**：
- 读取 Excel 台账（工作表 `一线支持` / `二线支持`），字段包括日期、类别、系统名称、事件级别、业务影响、结果、工作内容、交付文档、实施人等
- 按日期范围（起止日）过滤记录
- 排除「纳入汇报=否」的记录
- 自动统计：按类别、系统名称、数据来源、结果、实施人
- 风险管理：标记事件级别=高/中 或 业务影响=已影响/有风险的记录
- **交付文档关联**：
  - 从台账的「交付文档」字段提取文件名
  - 在用户指定的搜索目录（默认台账目录）中按文件名精确匹配 + 模糊匹配（SequenceMatcher > 0.32）
  - 支持 .docx / .pptx / .xlsx / .txt / .md / .log 格式文档内容提取和摘要生成
- 输出 Markdown + Word（.docx）双格式报告
- Word 报告包含：封面、目录、服务概览、管理摘要、分类统计、重点事项、风险与问题、交付文档重点内容、后续计划、交付文档清单

**报告类型**：周报 / 月报 / 季度报 / 年度报告

---

### 4.3 Oracle AWR 性能分析

**核心文件**：`app/oracle_analysis.py`、`app/awr_word_report.py`

**功能**：
1. **AWR HTML 解析**：
   - 支持标准 AWR HTML 报告
   - 提取：基本信息（DB Name / Instance / Host / Version）、Load Profile、Host CPU、Instance Efficiency、Top Timed Events、Top SQL（Elapsed / CPU / Gets / Reads / Executions / Parse Calls）、Segments、Buffer/PGA/Shared Pool/SGA Advisory
   - 输出结构化 JSON + Markdown 摘要

2. **.lst 性能对比报告解析**：
   - 解析章节结构 `[序号] 标题`、指标行 `键: 值`、固定宽度表格
   - 输出结构化 JSON（含 sections、tables、metrics、windows）

3. **规则引擎发现**：
   - 自动计算 AAS、AAS/CPU 比率、DB CPU / DB Time 占比
   - 等待事件分析：log file sync、db file sequential/scattered read、direct path read 等阈值判断
   - Top SQL 集中度、Hard Parse、Execute to Parse、RAC gc 等待
   - 输出规则发现 Markdown + JSON

4. **DeepSeek 模型调用**：
   - 构造提示词（AWR 摘要 + 规则发现 + 可选 Word 模板）
   - 调用本地 API（Ollama / 兼容 OpenAI 的接口）
   - 模型生成完整中文分析报告（12个章节：总体结论、风险等级、负载画像、等待事件、Top SQL、主机资源、内存建议、问题清单、整改建议、后续取证、领导汇报摘要、专家交付结论）

5. **Word 报告生成**：
   - 支持从 `templates/report_demo/` 选择 .docx 模板
   - 分析模板的目录结构和文本风格，指导 DeepSeek 按模板风格输出
   - 输出封面 + Markdown 转 Word 正文的 .docx 报告

---

### 4.4 TFA 日志自动分析

**核心文件**：`oracle-tfa-analyzer/`（子项目）

**功能**：
- 输入已脱敏的 Oracle TFA zip 包
- **本地解压、扫描、分析，不离开用户环境**
- 八大分析方向（规则可独立扩展）：
  - 数据库错误与稳定性（ORA-00600、ORA-7445、ORA-04031 等）
  - RAC/Clusterware（节点逐出、心跳超时、OCR/表决盘异常）
  - ASM/存储（磁盘组挂载/卸载、磁盘路径丢失、ASM 实例崩溃）
  - OS 资源（OOM Killer、swap 耗尽、文件句柄超限）
  - I/O 性能（I/O 延迟、提交等待、直接路径读异常）
  - 连接/监听（监听停止、连接风暴、PROTOCOL.ERROR）
  - SQL/性能争用（行锁、ITL 争用、热点对象）
  - ADG/备份（GAP 检测、归档中断、RMAN 失败）
- 时间过滤：仅分析最近 N 天 / 自定义起止日期
- 输出 `evidence.json`（包含 `discovered_at` 日期字段）
- 生成两份 Word 报告：
  - **领导汇报版**：简洁、结论先行、风险等级 + 整改优先级
  - **技术专家版**：详细（含日志证据、技术解释、建议命令、整改方案）

---

### 4.5 DeepSeek 模型管理

**核心文件**：`app/oracle_analysis.py`

**功能**：
- 自动发现本地模型列表（Ollama `/api/tags` 或 OpenAI 兼容 `/v1/models`）
- 首选 `deepseek-r1` 模型（可通过环境变量 `LOCAL_DEEPSEEK_MODEL` 覆盖）
- 接口地址默认 `http://127.0.0.1:11434/api/chat`（可通过 `LOCAL_DEEPSEEK_URL` 覆盖）
- 连接状态检测（前端实时显示绿/红状态指示灯）
- 超时处理（600 秒超时 + 友好错误提示：建议换更小模型或减少输入内容）

---

### 4.6 前端界面

**核心文件**：`static/app.js`、`static/styles.css`、`templates/index.html`

**设计**：
- 左侧导航菜单，右侧单页面板切换
- 导航项：
  - 🔒 脱敏工作台（扫描、脱敏、进度、结果、规则说明）
  - 📦 统一报告生成（台账路径、文档目录、日期范围、报告类型选择）
  - 📊 AWR/Oracle 分析（.lst 选择、AWR 上传、模板选择、模型配置）
  - 📋 TFA 日志分析（上传 zip、时间过滤、分析进度、下载）
- 面板切换逻辑（`PANEL_COPY` 定义标题/副标题）
- 报告类型选择按钮组（周报/月报/季度报/年度报）
- TFA 进度条：三步骤可视化（解压→分析→报告）
- 下载链接通过 `/download?path=...` 受控访问（白名单注册机制）

---

## 5. 技术栈

| 层 | 技术 |
|---|------|
| 语言 | Python 3.10+ |
| Web 服务 | `http.server`（标准库） |
| 前端 | 原生 JS（无框架） + CSS |
| 文档 | `python-docx`（.docx）、`openpyxl`（.xlsx） |
| HTML 解析 | `beautifulsoup4` + `lxml` |
| 数据分析 | `pandas` |
| 模型通信 | `requests`（本地 REST API） |
| 正则脱敏 | `re`（标准库） |

**无数据库**：所有数据存储于文件系统（JSON、Markdown、.docx）。

---

## 6. 安全与合规

- **所有处理在本地完成**，不上传原始日志/文件到外部
- 脱敏后的文件在源目录旁创建 `_desensitized` 副本，**不修改源文件**
- 下载通过白名单机制（`ALLOWED_DOWNLOADS` 集合），只有任务生成的文件可下载
- 路径安全：`downloadable_path` 验证文件属于白名单且存在
- 静态文件服务限制在 `/static/` 目录内

---

## 7. 已知限制与未来方向

### 当前限制
- **单用户单线程**：`http.server` 非异步，长耗时任务（DeepSeek 调用、TFA 分析）通过后台线程 + 轮询实现进度反馈
- **无持久化数据库**：Job 状态存于内存字典，服务重启后丢失
- **TFA 子项目独立打包**：路径需硬编码 `sys.path.insert(0, ...)` 引入

### 建议未来方向
- [ ] 迁移至 FastAPI 或 Flask 实现异步任务和 WebSocket 实时推送
- [ ] 加入 SQLite 持久化 Job 状态和 Last-Modified 缓存
- [ ] TFA 分析结果支持按 `discovered_at` 时间线编排，生成可视化甘特图/时间轴
- [ ] 支持多种 LLM 后端（OpenAI API、Azure AI、Claude）
- [ ] 脱敏规则支持用户自定义（UI 增删改）
- [ ] 统一报告支持更多数据源（Jira API、ServiceNow、Zabbix）
- [ ] 多用户场景：认证、权限、审计日志

---

## 8. 核心数据流

### 脱敏流程
```
源目录 → scan_files() → 文件列表
                        ├── Office文件 → process_office_file() → 解zip → 脱敏XML → 重打包
                        └── 文本文件  → process_text_file()   → 多编码尝试 → 逐条正则替换 → 写utf-8
                                  ↓
                    desensitization_report.json（含命中规则统计）
```

### 统一报告流程
```
Excel台账 → load_records() → 记录列表
                              ├── filter_weekly_records() → 按日期范围 + 纳入汇报
                              ├── top_counts() → 多维度统计
                              └── collect_delivery_document_summaries()
                                    ├── build_document_index() → 扫描目录索引
                                    └── find_delivery_document() → 精确/模糊匹配
                              ↓
                    Markdown + Word（create_docx_report()） 
```

### AWR 分析流程
```
AWR HTML → parse_awr_summary() → 结构化JSON摘要
         → build_awr_rule_findings() → 规则引擎发现（Markdown + JSON）
         → 构造 Prompt（摘要 + 发现 + 模板）
         → 调用本地 DeepSeek → Markdown 分析报告
         → create_oracle_docx() → Word .docx 报告
```

### TFA 分析流程
```
TFA zip → extrator.py → 解压到 .tfa_temp/
                      → engine.py → 200+ 规则匹配
                      → evidence.json（含 discovered_at）
                      → executive_report.py → 领导版 Word
                      → technical_report.py → 技术版 Word
```
