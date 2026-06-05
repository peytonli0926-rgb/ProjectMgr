# Oracle AWR 性能分析模块 — 产品需求文档 (PRD)

> **版本：** v3.0  
> **适用平台：** ProjectMgr Web 应用（Python http.server + 前端静态页面）  
> **核心能力：** AWR HTML / .lst 报告解析 → 规则引擎诊断 → LLM 生成分析报告 → Word / Markdown / JSON 交付  
> **配置文件：** [`app/config.py`](../ProjectMgr/app/config.py) · [`app/server.py`](../ProjectMgr/app/server.py) · [`app/oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py)  
> **前端页面：** [`templates/index.html`](../ProjectMgr/templates/index.html) · [`static/app.js`](../ProjectMgr/static/app.js) · [`static/styles.css`](../ProjectMgr/static/styles.css)  
> **独立模块：** [`awr-auto-analyzer/`](../ProjectMgr/awr-auto-analyzer/)（图表生成）  

---

## 目录

1. [产品概述](#1-产品概述)
2. [系统架构](#2-系统架构)
3. [用户界面说明](#3-用户界面说明)
4. [核心功能详解](#4-核心功能详解)
5. [数据解析引擎](#5-数据解析引擎)
6. [规则诊断引擎](#6-规则诊断引擎)
7. [LLM 报告生成](#7-llm-报告生成)
8. [图表可视化](#8-图表可视化)
9. [Word 报告交付](#9-word-报告交付)
10. [DeepSeek 配置管理](#10-deepseek-配置管理)
11. [API 接口规范](#11-api-接口规范)
12. [数据流全景](#12-数据流全景)
13. [错误处理与边界情况](#13-错误处理与边界情况)
14. [附录：规则引擎说明](#14-附录规则引擎说明)

---

## 1. 产品概述

### 1.1 产品定位

Oracle AWR 性能分析模块是 ProjectMgr 的核心诊断子模块，面向 **Oracle DBA 和金融行业数据库运维团队**，提供从原始 AWR 报告采集 → 结构化解析 → 自动化规则诊断 → LLM 智能分析 → 专业 Word 报告的**全链路自动化**解决方案。

### 1.2 目标用户

| 角色 | 使用场景 | 核心诉求 |
|------|---------|---------|
| Oracle DBA | 日常巡检、故障排查、性能容量评估 | 快速定位瓶颈、生成可交付报告 |
| 运维团队负责人 | 周报/月报、向上汇报 | 获取管理层摘要、风险等级评估 |
| 金融行业客户 | 数据库健康评估、IT 审计 | 获得符合金融行业规范的专业报告 |

### 1.3 核心能力矩阵

| 能力 | 输入 | 输出 | 是否必须 |
|------|------|------|---------|
| `.lst` 文件解析 | Oracle Performance Compare Report (.lst) | 结构化 JSON + Markdown 分析报告 + Word | 是 |
| `AWR HTML` 解析 | Oracle AWR HTML 报告 | 结构化摘要 + 规则发现 + Markdown + Word + 图表 | 是 |
| 规则诊断引擎 | 结构化 AWR 摘要 | 12+ 条规则判定（含证据与建议） | 是 |
| LLM 报告生成 | 结构化摘要 + 规则发现 + 模板 | 10 节标准分析报告 | 是 |
| 图表可视化 | AWR 摘要数据 | 6 类 PNG 统计图 | 可选（需 matplotlib） |
| Word 报告 | Markdown 分析结果 + docx 模板 | 专业排版的 Word 文档 | 是 |
| 双模推理 | 本地 Ollama / 在线 DeepSeek | LLM 分析结果 | 是 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌────────────────────────────────────────────────────────────┐
│                    用户浏览器 (Web UI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ DeepSeek 设置 │  │ AWR 分析页面 │  │ TFA 分析页面     │  │
│  │ 双面板配置    │  │ 下拉选模型    │  │ (独立模块)       │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────┘  │
└─────────┼─────────────────┼────────────────────────────────┘
          │ HTTP POST       │ HTTP POST
          ▼                 ▼
┌────────────────────────────────────────────────────────────┐
│                 Python HTTP Server (8000)                   │
│  ┌────────────────────────────────────────────────────────┐│
│  │                    Handler (server.py)                  ││
│  │  /oracle/lst-files → 列出文件 + 加载配置                ││
│  │  /oracle/analyze → .lst 全链路分析                      ││
│  │  /oracle/analyze-awr → AWR HTML 全链路分析              ││
│  │  /oracle/awr-word-report → 已有报告转 Word              ││
│  │  /oracle/save-deepseek-config → 双面板配置持久化        ││
│  └──────────────────────┬─────────────────────────────────┘│
└─────────────────────────┼──────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────────┐ ┌──────────┐ ┌──────────────┐
│ oracle_analysis  │ │ config   │ │ awr_word_    │
│ .py              │ │ .py      │ │ report.py    │
│                  │ │          │ │              │
│ • .lst 解析引擎  │ │ 目录管理 │ │ python-docx  │
│ • AWR 解析引擎   │ │ 端口配置 │ │ 金融风格排版 │
│ • 规则引擎       │ │          │ │ 封面/页眉    │
│ • Prompt 构建    │ │          │ │ 页脚/表格    │
│ • LLM 调用适配   │ │          │ │ 图表嵌入     │
│ • Word 原生生成  │ │          │ │              │
└─────────────────┘ └──────────┘ └──────────────┘
                          ▲
                          │ 软依赖
                  ┌───────┴───────┐
                  │ chart_generator│
                  │ .py           │
                  │ (awr-auto-    │
                  │  analyzer/)   │
                  │ matplotlib    │
                  │ 6类性能图表    │
                  └───────────────┘
```

### 2.2 核心模块依赖关系

```
app/server.py
  ├── app/oracle_analysis.py     ← AWR 解析、规则引擎、LLM 调用、Word 生成
  ├── app/config.py              ← 全局配置
  ├── app/awr_word_report.py     ← python-docx 金融风格 Word 报告
  └── awr-auto-analyzer/         ← 软依赖
        └── chart_generator.py   ← matplotlib 图表生成
```

### 2.3 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 服务器 | Python `http.server.ThreadingHTTPServer` | 轻量级，无框架依赖 |
| 前端 | 原生 HTML5 + CSS3 + JavaScript (ES6) | 无前端框架依赖 |
| LLM 协议 | Ollama `/api/chat` + OpenAI `/v1/chat/completions` | 双协议自动适配 |
| 图表 (可选) | matplotlib (Agg 后端) | 服务器安全，无 GUI 依赖 |
| Word 报告 (原生) | OpenXML (zipfile) | 无 python-docx 依赖，纯 XML 拼装 |
| Word 报告 (模板) | python-docx + OpenXML | 使用金融风格模板 |

---

## 3. 用户界面说明

### 3.1 页面布局

AWR 分析页面位于导航栏"**AWR 性能分析**"标签页，包含以下区域：

#### 3.1.1 分析模型选择器

文件：[`templates/index.html`](../ProjectMgr/templates/index.html:294)

```
┌─────────────────────────────────────────────────────┐
│  分析模型  [DeepSeek 设置中的当前激活配置    ▼]      │
│            ├ DeepSeek 设置中的当前激活配置  (默认)   │
│            ├ 🖥️ 本地模型                          │
│            └ 🌐 联网模型                          │
└─────────────────────────────────────────────────────┘
```

- **默认值"":** 使用 DeepSeek 设置页面中当前激活的配置（本地或联网）
- **"local":** 强制使用本地面板的 URL 和模型
- **"online":** 强制使用联网面板的 URL、模型和 API Key

实现逻辑：[`static/app.js`](../ProjectMgr/static/app.js:220) `getSelectedDsEndpoint()`

#### 3.1.2 双 Tab 分析入口

**Tab 1 — `.lst` 性能对比分析：**

```
┌─────────────────────────────────────────────────────────┐
│ Oracle .lst 文件                            性能对比     │
│ 选择 .lst 文件  [oracle_perf_compare.lst ▼] [刷新] [分析] │
│ ☑ 自动使用 data 目录下最新的 .lst 文件                  │
└─────────────────────────────────────────────────────────┘
```

**Tab 2 — AWR HTML 报告分析：**

```
┌─────────────────────────────────────────────────────────┐
│ AWR HTML 报告                                AWR Report │
│ AWR 报告文件路径  [________________________] [上传] [分析]│
│ 从 data 目录选择 AWR 文件  [awr_orcl_1_100_101.html ▼]  │
│                              [填充路径] [生成 Word 报告]│
└─────────────────────────────────────────────────────────┘
```

#### 3.1.3 Word 报告模板选择

```
┌─────────────────────────────────────────────────────────┐
│ Word 报告模板                               可选         │
│ 选择模板文档  [OPT_金融行业_AWR分析报告.docx ▼]          │
│ 模板用于格式化 .lst 和 AWR 分析输出的 Word 报告样式。    │
└─────────────────────────────────────────────────────────┘
```

### 3.2 DeepSeek 设置页面（双面板）

文件：[`templates/index.html`](../ProjectMgr/templates/index.html:183)

```
┌────────────────────────────────────────────────────────┐
│  🔮 DeepSeek 配置                                      │
│  配置本地或联网模型服务参数，选择要使用的模型。          │
│                                                        │
│  ┌─────────────┐  ┌─────────────┐                     │
│  │ 🖥️ 本地地址 │  │ 🌐 联网地址 │  ← 选项卡切换       │
│  │ 默认选中    │  │             │                     │
│  └─────────────┘  └─────────────┘                     │
│                                                        │
│  ┌─────────────────────────────────────────────┐      │
│  │ 🖥️ 本地配置                                 │      │
│  │ 接口地址  [http://127.0.0.1:11434/api/chat] │      │
│  │ 选择模型  [DeepSeek-R1:14b              ▼]  │      │
│  │           系统自动发现本地可用模型           │      │
│  └─────────────────────────────────────────────┘      │
│                                                        │
│  ┌─────────────────────────────────────────────┐      │
│  │ 🌐 联网配置                                 │      │
│  │ 接口地址  [https://api.deepseek.com/...]    │      │
│  │ 选择模型  [deepseek-chat             ]     │      │
│  │ API Key   [sk-************************]     │      │
│  └─────────────────────────────────────────────┘      │
│                                                        │
│  ┌─────────────────────────────────────────────┐      │
│  │ ● 已连接 本地 Ollama 服务可正常访问         │      │
│  │              [💾 保存配置]                   │      │
│  └─────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

### 3.3 分析结果展示

分析完成后，结果显示区域展示：

```
┌────────────────────────────────────────────────────────┐
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────────┐     │
│  │ 行数 │ │ 章节 │ │ 表格 │ │ 生成时间          │     │
│  │ 856  │ │ 14   │ │ 22   │ │ 2026-06-05 12:00  │     │
│  └──────┘ └──────┘ └──────┘ └──────────────────┘     │
│                                                        │
│  源文件  awr_orcl_1_100_101.html                       │
│  报告模板  OPT_金融行业_AWR分析报告.docx                │
│  问题窗口  2026-06-04 10:00 - 11:00                    │
│  对比窗口  2026-06-03 10:00 - 11:00                    │
│                                                        │
│  [下载 Word 报告] [下载 Markdown] [下载 JSON]          │
│                                                        │
│  ┌─────────────────────────────────────────────┐      │
│  │ 模型生成报告预览                             │      │
│  │ # Oracle AWR 性能分析报告                    │      │
│  │ ## 1. 总体结论                              │      │
│  │ 1. AAS=3.2，CPU=8，AAS/CPU=0.40...          │      │
│  │ ...                                         │      │
│  └─────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

---

## 4. 核心功能详解

### 4.1 双输入格式支持

#### 4.1.1 `.lst` 文件（Oracle Performance Compare Report）

- **来源：** Oracle `awrddrpt.sql` 脚本生成的性能对比报告
- **特点：** 固定宽度文本格式，包含"问题时间窗口"和"对比时间窗口"
- **解析方式：** 正则提取章节、固定宽度表格、关键指标
- **输出：** 结构化 JSON 包含 sections、tables、metrics、windows

解析位置：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:282) `parse_lst()`

#### 4.1.2 AWR HTML 报告

- **来源：** Oracle `awrrpt.sql` 脚本生成的 HTML 报告
- **特点：** 复杂 HTML 结构，22+ 类性能章节
- **解析方式：** BeautifulSoup + pandas.read_html + 正则回退（三级递进策略）
- **输出：** 结构化 JSON 包含 basic_info、Load Profile、Wait Events、Top SQL、Advisory 等 19 类数据

解析位置：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:689) `parse_awr_summary()`

### 4.2 智能模型选择

- **默认模式：** 使用 DeepSeek 设置中当前激活的配置
- **强制模式：** 在 AWR 页面下拉菜单选择"本地模型"或"联网模型"覆盖默认配置
- **双协议适配：** 自动识别 Ollama `/api/chat` 和 OpenAI `/v1/chat/completions` 协议
  
协议判断位置：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:1188) `ask_llm()`

### 4.3 全链路分析流程

```
用户点击"分析 AWR" 或 "开始分析"
        │
        ▼
  ① 文件解析
  │  ├─ .lst:  parse_lst() → JSON
  │  └─ AWR:   parse_awr_summary() → 结构化摘要 + 输出 awr_summary.md/json
  │        └─ 同时 parse_awr() → 基础解析（供预览）
        │
        ▼
  ② 规则引擎
  │   build_awr_rule_findings() → 12+ 规则判定
  │   └─ 输出 awr_rule_findings.md/json
        │
        ▼
  ③ 图表生成（若 matplotlib 可用）
  │   generate_all_charts() → 6 类 PNG
  │   └─ 存入 output/charts/
        │
        ▼
  ④ Prompt 构建
  │   build_awr_prompt() → 融合摘要 + 规则发现 + 模板信息
  │   └─ 包含 10 节标准报告结构要求
        │
        ▼
  ⑤ LLM 调用
  │   ask_llm() → 自动适配 Ollama / OpenAI 协议
  │   └─ 超时 600s，temperature 0.2，max_tokens 8192
        │
        ▼
  ⑥ 报告产出
  │   ├─ Markdown: awr_analysis_report.md
  │   ├─ JSON: 完整结果持久化
  │   ├─ Word: create_oracle_docx() → .docx
  │   └─ 可选模板 + 图表嵌入
```

---

## 5. 数据解析引擎

### 5.1 `.lst` 解析逻辑

文件：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:228)

```python
parse_lst(path: Path) -> dict
```

**解析步骤：**

1. **行遍历：** 按行读取，识别 `[序号] 标题` 格式章节
2. **窗口提取：** 正则匹配"问题时间窗口"和"对比时间窗口"
3. **指标提取：** 正则匹配 `指标名: 值` 格式
4. **表格解析：** 检测 `----- -----` 分隔行 → 确定列跨度 → 提取表头和行数据
5. **关联章节：** 每个表格关联其所属的最近章节

**输出结构示例：**

```json
{
  "source_file": "/tmp/data/oracle_perf_compare.lst",
  "line_count": 856,
  "windows": {
    "问题时间窗口": "01-JUN-2024 10:00 - 11:00",
    "对比时间窗口": "31-MAY-2024 10:00 - 11:00"
  },
  "sections": [
    {"index": 1, "title": "Load Profile", "line": 12},
    {"index": 2, "title": "Instance Efficiency", "line": 45}
  ],
  "tables": [
    {"section": {...}, "line": 50, "columns": [...], "rows": [...]}
  ]
}
```

### 5.2 AWR HTML 解析逻辑

文件：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:689)

```python
parse_awr_summary(path: Path) -> dict
```

**三级递进解析策略：**

| 优先级 | 方法 | 依赖 |
|--------|------|------|
| 1 | `BeautifulSoup + pandas.read_html()` | bs4 + pandas |
| 2 | `fallback_read_html_tables()` (纯正则) | 无外部依赖 |
| 3 | `html_to_text()` + 行提取 | 无外部依赖 |

**识别章节（按 AWR 标准结构）：**

```
├── 基本信息 (DB Name, Instance, Host, Version, Snap 范围, AAS)
├── Load Profile (Per Second / Per Transaction)
├── Host CPU (%Busy, %User, %System, %Idle, %WIO)
├── Instance Efficiency (Buffer Hit %, Latch Hit %, Exec to Parse %)
├── Top Timed Events / Foreground Wait Events
├── SQL ordered by Elapsed Time / CPU Time / Gets / Reads / Executions / Parse Calls / Cluster Wait
├── Segments by Logical Reads / Physical Reads / Row Lock Waits / ITL Waits
├── Buffer Cache Advisory
├── PGA Advisory
├── Shared Pool Advisory
└── SGA Target Advisory
```

**每个 SQL 类别的智能压缩：**

```python
compact_sql_rows(records, limit=10) -> list[dict]
```

- 保留关键字段：SQL ID、Elapsed Time、CPU Time、Executions、Buffer Gets 等
- SQL Text 截断为 300 字符
- 排序保留消耗最高的条目

---

## 6. 规则诊断引擎

### 6.1 规则总览

文件：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:861)

规则引擎共包含 **12 条规则**，分为 4 组：

| 组别 | 规则名称 | 等级判定 | 核心指标 |
|------|---------|---------|---------|
| A 组 | AAS 负载 | 高 / 中 / 低 / 信息不足 | AAS/CPU 比值 |
| A 组 | CPU 型负载 | 高 / 低 / 信息不足 | DB CPU / DB Time |
| A 组 | Top 等待集中 | 高 / 低 / 信息不足 | Top 1 Wait % DB Time |
| B 组 | 提交延迟风险 | 中高 / 低 / 信息不足 | log file sync avg ms |
| B 组 | 日志写风险 | 中高 / 低 / 信息不足 | log file parallel write avg ms |
| B 组 | 单块读 I/O 风险 | 中高 / 低 / 信息不足 | db file sequential read avg ms |
| B 组 | 多块读 I/O 风险 | 中高 / 低 / 信息不足 | db file scattered read avg ms |
| C 组 | 直接路径读 I/O 风险 | 中高 / 低 / 信息不足 | direct path read avg ms |
| C 组 | Hard Parse | 中 / 低 / 信息不足 | Hard parses/s |
| C 组 | Execute to Parse | 中 / 低 / 信息不足 | Execute to Parse % |
| D 组 | Top SQL 负载集中 | 高 / 低 / 信息不足 | Top 1 SQL %Total |
| D 组 | RAC Global Cache | 中高 / 低 / 信息不足 | gc wait % DB Time |

### 6.2 详细规则定义

#### A 组 — IO 吞吐与负载

**规则 A1 - AAS 负载：**
```
条件：AAS/CPU >= 0.7 → 等级="高"
      0.3 <= AAS/CPU < 0.7 → 等级="中"
      AAS/CPU < 0.3 → 等级="低"
      数据不足 → 等级="信息不足"
建议：结合业务峰值和 OS CPU 使用率确认是否存在容量压力
```

**规则 A2 - CPU 型负载：**
```
条件：DB CPU / DB Time > 70% → 等级="高"
      否则 → 等级="低"
建议(高)：优先核查 CPU 消耗 Top SQL、执行计划和主机 CPU 饱和度
```

**规则 A3 - Top 等待集中：**
```
条件：Top 1 等待事件 % DB Time > 40% → 等级="高"
      否则 → 等级="低"
建议(高)：优先围绕该等待事件做 SQL、对象和系统层取证
```

#### B 组 — 等待事件分类

**规则 B1-B5 — 具体等待阈值：**
```
条件：avg_ms > threshold → 等级="中高"
      avg_ms <= threshold → 等级="低"
      未识别 → 等级="信息不足"

log file sync:          threshold=10ms
log file parallel write:threshold=10ms
db file sequential read:threshold=10ms
db file scattered read: threshold=20ms
direct path read:       threshold=20ms
```

#### C 组 — SQL 分类

**规则 C1 - Hard Parse：**
```
条件：Hard parses/s > 10 → 等级="中"
      否则 → 等级="低"
建议(中)：检查绑定变量、共享池压力、SQL 版本数和应用解析行为
```

**规则 C2 - Execute to Parse：**
```
条件：Execute to Parse % < 70 → 等级="中"
      否则 → 等级="低"
建议(中)：检查会话缓存游标、应用短连接和 SQL 解析模式
```

#### D 组 — Segment 热点

**规则 D1 - Top SQL 负载集中：**
```
条件：Top 1 SQL %Total > 20% → 等级="高"
      否则 → 等级="低"
建议(高)：优先获取执行计划、绑定变量、对象统计信息并评估 SQL 改写
```

**规则 D2 - RAC Global Cache：**
```
条件：最高 gc wait %DB Time > 10% → 等级="中高"
      gc 存在但 <=10% → 等级="低"
      无 gc 识别 → 等级="信息不足"
建议(中高)：检查跨实例访问、热点块、服务部署亲和性和对象分区策略
```

### 6.3 计算指标

规则引擎自动计算以下关键指标：

```json
{
  "Elapsed Time(mins)": "60.25",
  "DB Time(mins)": "180.50",
  "Average Active Sessions": "3.00",
  "CPUs": "8",
  "DB CPU / DB Time": "35.20%"
}
```

---

## 7. LLM 报告生成

### 7.1 Prompt 构建策略

文件：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:1005)

**Prompt 结构（AWR 路径）：**

```
┌────────────────────────────────────────────────────┐
│ System: "资深 Oracle 数据库性能诊断专家"            │
│                                                     │
│ 硬性要求（6条）：                                    │
│ 1. 中文、正式、金融行业风格                          │
│ 2. 总体结论 ≤ 5 条，引用具体 AWR 指标               │
│ 3. SQL 分析保留 SQL ID                               │
│ 4. 区分 CPU 型/IO 型/等待型/逻辑读型/等负载类型      │
│ 5. SQL Text 有特征要明确指出                        │
│ 6. 不输出代码块/寒暄                                 │
│                                                     │
│ 要求的 12 节报告结构：                               │
│ # Oracle AWR 性能分析报告                            │
│ ## 1. 总体结论                                      │
│ ## 2. 风险等级                                      │
│ ## 3. 数据库负载画像                                │
│ ## 4. Top Wait Events 分析                          │
│ ## 5. Top SQL 分析                                  │
│ ## 6. 主机资源分析                                  │
│ ## 7. 内存与参数建议                                │
│ ## 8. 问题点清单                                    │
│ ## 9. 整改建议（短/中/长期）                        │
│ ## 10. 后续取证清单                                 │
│ ## 11. 领导汇报摘要                                 │
│ ## 12. 专家交付结论                                 │
│                                                     │
│ 可选：模板章节信息和措辞风格指引                     │
│                                                     │
│ 数据：                                              │
│ ├── 结构化 AWR 摘要 (≤ 60000 字符)                  │
│ └── 规则引擎发现 (≤ 16000 字符)                     │
└────────────────────────────────────────────────────┘
```

**Prompt 结构（.lst 路径）：**

```
System: "资深 Oracle 性能诊断工程师"

要求的报告结构：
1. 分析结论（判断是否异常）
2. 分析背景
3. 关键证据链
4. 可能原因
5. 影响评估
6. 排查步骤
7. 优化建议
8. 风险与注意事项
9. 管理层摘要
```

### 7.2 LLM 调用参数

| 参数 | 值 | 说明 |
|------|-----|------|
| temperature | 0.2 | 低温度确保输出稳定、可重复 |
| top_p | 0.9 | 适度多样性 |
| max_tokens / num_predict | 8192 | 支持长报告输出 |
| timeout | 600s | 复杂 AWR 报告可能需要长时间推理 |
| stream | false | 非流式，一次性获取完整报告 |

### 7.3 双协议自动适配

```python
def ask_llm(url, model, prompt, api_key="", timeout=600):
    if "/api/chat" in url:
        return _ask_ollama(url, model, prompt, timeout)
    return _ask_openai(url, model, prompt, api_key, timeout)
```

- **Ollama 协议 (`/api/chat`)：** 本地部署，无 API Key，Ollama 格式 body
- **OpenAI 兼容协议 (`/v1/chat/completions`)：** DeepSeek 在线、OpenAI、Azure OpenAI 等，支持 Bearer Token 认证

---

## 8. 图表可视化

### 8.1 图表种类

文件：[`awr-auto-analyzer/awr_auto_analyzer/chart_generator.py`](../ProjectMgr/awr-auto-analyzer/awr_auto_analyzer/chart_generator.py)

| 序号 | 图表名 | 文件名 | 类型 | 数据来源 |
|------|--------|--------|------|---------|
| 1 | Load Profile Per Second | `awr_load_profile.png` | 柱状图 | Load Profile → Per Second |
| 2 | Top Wait Events | `top_wait_events.png` | 水平条形图 | Foreground Wait Events → %Total |
| 3 | Top SQL Elapsed Time | `top_sql.png` | 水平条形图 | SQL by Elapsed Time |
| 4 | Host CPU 利用率 | `host_cpu.png` | 柱状图 + 80% 警戒线 | Host CPU |
| 5 | Instance Efficiency | `instance_efficiency.png` | 柱状图 + 95% 优秀线 | Instance Efficiency |
| 6 | Top Segments | `top_segments.png` | 水平条形图 | Segments by Logical Reads |

### 8.2 设计规范

- **配色方案：** 深海蓝 (`#1B3A5C`) 为主色，香槟金 (`#C8A96E`) 为强调色
- **中文字体：** 自动探测 PingFang SC / Microsoft YaHei / WenQuanYi Micro Hei
- **输出：** 200 DPI PNG，白底，无边框
- **存储：** `output/charts/` 目录
- **依赖：** matplotlib (Agg 后端)，无头服务器安全

### 8.3 软依赖策略

```python
try:
    import matplotlib
    matplotlib.use("Agg")
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
```

- matplotlib 未安装时，图表生成静默跳过，不影响主流程
- 分析结果 `generate_all_charts()` 返回 `{}` 空字典

---

## 9. Word 报告交付

### 9.1 双路径 Word 生成

文件：[`oracle_analysis.py`](../ProjectMgr/app/oracle_analysis.py:1325)

#### 路径 A — 原生 OpenXML 生成（无依赖版）

```python
create_oracle_docx(output_path, title, report_text, parsed, model, template_path=None)
```

- 纯 XML 拼装，不依赖 python-docx
- 支持金融行业配色（深海蓝标题、香槟金强调）
- 支持模板章节注入（从 docx 模板提取 sectPr）
- 包含封面、页眉页脚（如模板中有）

#### 路径 B — python-docx 模板渲染（增强版）

文件：[`awr_word_report.py`](../ProjectMgr/app/awr_word_report.py)

- 使用 python-docx 操作模板（`templates/report_demo/` 下的 docx 文件）
- 金融行业专业排版配色方案
- 封面页、页眉页脚、表格样式、图表嵌入

### 9.2 Word 报告结构（原生版）

```
┌──────────────────────────────────────┐
│  Oracle AWR 性能分析报告              │ ← 深海蓝, 46pt
│  awr_orcl_1_100_101.html AWR 性能分析 │ ← 副标题, 30pt
│  生成时间：2026年06月05日 12:00       │
│  本地模型：DeepSeek-R1:14b            │
│  源文件：awr_orcl_1_100_101.html      │
│  问题窗口：2026-06-04 10:00 - 11:00   │
│  对比窗口：2026-06-03 10:00 - 11:00   │
├──────────────────────────────────────┤
│  # Oracle AWR 性能分析报告            │
│  ## 1. 总体结论                      │
│  1. ...                              │
│  ## 2. 风险等级                      │
│  | 风险项 | 等级 | 证据 | 影响 |     │
│  ## 3. 数据库负载画像                │
│  ...                                 │
│  ## 12. 专家交付结论                  │
└──────────────────────────────────────┘
```

### 9.3 模板系统

- **模板目录：** `templates/report_demo/`
- **支持格式：** `.docx`（OpenXML）
- **匹配策略：** 前缀 `OPT_` 的模板自动优先选择
- **章节感知：** `template_profile()` 自动提取模板目录结构和样式，传给 LLM 参考

---

## 10. DeepSeek 配置管理

### 10.1 配置数据结构

文件：[`server.py`](../ProjectMgr/app/server.py:37)

```json
{
  "active_mode": "local",
  "local": {
    "url": "http://127.0.0.1:11434/api/chat",
    "model": "DeepSeek-R1:14b"
  },
  "online": {
    "url": "https://api.deepseek.com/chat/completions",
    "model": "deepseek-chat",
    "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

### 10.2 持久化

- **存储位置：** `TMP_DIR / "deepseek_config.json"`
- **加载时机：** 页面加载、文件列表加载、分析请求
- **保存时机：** 用户点击"保存配置"按钮
- **向后兼容：** 自动检测旧版单面板格式并转换为新格式

### 10.3 配置优先级

```
请求传入配置 (url/model/api_key from frontend)
    ↓ 优先
已保存的双面板配置 (load_deepseek_config → resolve_active_deepseek_config)
    ↓ 回退
环境变量 / 默认值 (DEFAULT_DEEPSEEK_URL, DEFAULT_DEEPSEEK_MODEL)
```

### 10.4 模型自动发现

```python
discover_local_models(url) -> list[str]
```

- Ollama: `GET /api/tags` → 返回模型名称列表
- OpenAI 兼容: `GET /v1/models` → 返回模型 ID 列表
- 自动识别协议类型

---

## 11. API 接口规范

### 11.1 接口一览

| 方法 | 路径 | 功能 | 请求格式 | 响应格式 |
|------|------|------|---------|---------|
| GET | `/oracle/lst-files` | 文件列表 + 配置 + 模型 | — | JSON |
| GET | `/oracle/load-deepseek-config` | 加载双面板配置 | — | JSON |
| POST | `/oracle/save-deepseek-config` | 保存双面板配置 | JSON body | JSON |
| POST | `/oracle/analyze` | .lst 全链路分析 | JSON body | JSON |
| POST | `/oracle/analyze-awr` | AWR HTML 全链路分析 | JSON body | JSON |
| POST | `/oracle/awr-word-report` | 已有报告转 Word | — | JSON |
| POST | `/oracle/upload-awr` | 上传 AWR HTML 文件 | multipart | JSON |

### 11.2 详细接口说明

#### `POST /oracle/analyze`

**请求体：**
```json
{
  "use_latest": true,
  "lst_path": "/tmp/data/oracle_perf_compare.lst",
  "template_path": "/project/templates/report_demo/OPT_xxx.docx",
  "url": "http://127.0.0.1:11434/api/chat",
  "model": "DeepSeek-R1:14b",
  "api_key": ""
}
```

**响应体：**
```json
{
  "source_file": "/tmp/data/oracle_perf_compare.lst",
  "generated_at": "2026-06-05T12:00:00",
  "json_path": "/tmp/output/xxx_deepseek_analysis.json",
  "markdown_path": "/tmp/output/xxx_local_model_report.md",
  "word_path": "/tmp/output/xxx_local_model_report.docx",
  "parsed_summary": {
    "windows": {"问题时间窗口": "..."},
    "sections": 14,
    "tables": 22,
    "line_count": 856
  },
  "deepseek_answer": "# Oracle 性能分析报告\n...",
  "template": {"name": "OPT_xxx.docx", "headings": [...]}
}
```

#### `POST /oracle/analyze-awr`

**请求体：**
```json
{
  "awr_path": "/tmp/data/awr_orcl_1_100_101.html",
  "template_path": "/project/templates/report_demo/OPT_xxx.docx",
  "url": "https://api.deepseek.com/chat/completions",
  "model": "deepseek-chat",
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

**响应体：**
```json
{
  "source_file": "/tmp/data/awr_orcl_1_100_101.html",
  "summary_json_path": "/tmp/output/awr_summary.json",
  "summary_markdown_path": "/tmp/output/awr_summary.md",
  "rule_findings_json_path": "/tmp/output/awr_rule_findings.json",
  "rule_findings_markdown_path": "/tmp/output/awr_rule_findings.md",
  "markdown_path": "/tmp/output/awr_analysis_report.md",
  "json_path": "/tmp/output/xxx_awr_analysis.json",
  "word_path": "/tmp/output/xxx_awr_report.docx",
  "deepseek_answer": "# Oracle AWR 性能分析报告\n...",
  "model": "deepseek-chat",
  "message": "AWR 分析完成"
}
```

---

## 12. 数据流全景

### 12.1 AWR 分析数据流

```
用户选择 AWR HTML 文件
        │
        ▼
POST /oracle/analyze-awr
        │
        ▼
① parse_awr(path)
   ├── read_report_text() → 编码检测 (utf-8/gb18030/latin-1) + HTML 转文本
   ├── 提取 metrics (DB Name, Instance, Snap 等)
   └── extract_awr_sections() → 22 类章节聚类，每节 ≤45 行
        │
        ▼
② write_awr_summary(path)
   ├── parse_awr_summary(path)
   │   ├── BeautifulSoup + pandas.read_html (首选)
   │   │   └── fallback_read_html_tables() (回退)
   │   ├── extract_awr_basic_info() → DB 名称/版本/快照/CPUs/AAS
   │   ├── find_table_by_section() → 19 类模块数据提取
   │   ├── compact_sql_rows() → SQL 字段压缩
   │   └── find_first_table_by_sections() → 容错多别名匹配
   ├── render_awr_summary_markdown() → awr_summary.md
   └── JSON 持久化 → awr_summary.json
        │
        ▼
③ write_awr_rule_findings(summary)
   ├── build_awr_rule_findings() → 12 条规则 + 计算指标
   ├── render_rule_findings_markdown() → awr_rule_findings.md
   └── JSON 持久化 → awr_rule_findings.json
        │
        ▼
④ generate_all_charts(summary)  [可选]
   ├── generate_load_profile_chart()
   ├── generate_wait_events_chart()
   ├── generate_top_sql_chart()
   ├── generate_host_cpu_chart()
   ├── generate_efficiency_chart()
   └── generate_top_segments_chart()
        │
        ▼
⑤ build_awr_prompt(summary_md, rule_findings_md, profile)
   └── 融合数据 → 12 节标准报告结构的 prompt
        │
        ▼
⑥ ask_llm(url, model, prompt, api_key)
   ├── _ask_ollama() / _ask_openai()
   └── 600s 超时，8192 tokens
        │
        ▼
⑦ create_oracle_docx(word_path, title, answer, parsed, model, template_path)
   ├── OpenXML 组装 (纯 XML / 模板注入)
   ├── 深海蓝/香槟金配色
   └── 封面 + 元信息 + 正文 + 章节属性
        │
        ▼
⑧ 前端展示
   ├── renderAwrSummaryResult() → 摘要卡片 + 下载按钮
   └── 报告预览 (deepseek_answer)
```

### 12.2 `.lst` 分析数据流

```
用户选择 .lst 文件 / 勾选"自动使用最新"
        │
        ▼
POST /oracle/analyze
        │
        ▼
① parse_lst(path)
   ├── 章节提取 (正则 [Index] Title)
   ├── 窗口提取 (问题/对比时间窗口)
   ├── 指标提取 (Metric: Value)
   └── 表格解析 (固定宽度)
        │
        ▼
② build_deepseek_prompt(parsed, profile)
   └── compact_report_for_prompt() → 表格摘要 + 提示词
        │
        ▼
③ ask_llm(url, model, prompt, api_key)
        │
        ▼
④ create_oracle_docx() → Word
```

### 12.3 配置加载数据流

```
页面加载 / 导航到 AWR 标签
        │
        ▼
loadOracleLstFiles()  ← JS
        │
        ▼
GET /oracle/lst-files
        │
        ▼
server.py:
├── ① discover_local_models(url) → [本地模型列表]
├── ② load_deepseek_config() → {active_mode, local, online}
├── ③ list_lst_files() → [.lst 文件列表]
├── ④ list_awr_files() → [AWR 文件列表]
├── ⑤ list_report_templates() → [模板列表]
└── preferred_model() → 默认模型
        │
        ▼
前端填充:
├── dsLocalModel <select> → 模型列表
├── dsLocalUrl / dsOnlineUrl / dsOnlineApiKey
├── oracleLstPath / oracleAwrSelect / oracleReportTemplate
└── toggleDsMode() → 显示激活面板
```

---

## 13. 错误处理与边界情况

### 13.1 文件类错误

| 场景 | 处理方式 | 用户提示 |
|------|---------|---------|
| .lst 文件不存在 | 返回 400，错误信息 | "未找到 .lst 文件" |
| AWR 文件不存在 | 返回 400，错误信息 | "请选择有效的 AWR 报告文件" |
| 文件格式不支持 | 校验后缀 | "仅支持 .html、.htm、.txt、.lst" |
| AWR 上传路径安全 | `uploaded_awr_path()` 防路径穿越 | — |
| Word 模板路径校验 | `safe_template_path()` 检查 allowed_root | — |

### 13.2 LLM 调用错误

| 场景 | 处理方式 | 用户提示 |
|------|---------|---------|
| Ollama 返回 HTTP 错误 | 捕获 `HTTPError`，读取 error body | "Ollama 接口返回 {code}: {detail}" |
| 在线 API 返回错误 | 同上 | "在线 API 返回 {code}: {detail}" |
| 超时 (TimeoutError / socket.timeout) | 捕获并转义 | "模型分析超时，请换更小模型或减少输入内容" |
| 在线 API 超时 | 同上 | "在线 API 请求超时，请检查网络连接" |
| SSL 证书错误 | `_get_ssl_context()` 使用 certifi | 自动处理，用户无感知 |
| URL 格式不支持 | `ask_llm()` 按 `/api/chat` 区分协议 | — |

### 13.3 配置类错误

| 场景 | 处理方式 |
|------|---------|
| 未保存过配置 | 返回默认双面板结构 |
| 配置格式不完整 | `save_deepseek_config()` 补充缺失字段 |
| 旧版单面板配置 | `load_deepseek_config()` 自动转换 |
| API Key 缺失 | 仅 online 模式需要，local 模式忽略 |

### 13.4 边界情况

| 场景 | 处理方式 |
|------|---------|
| AWR 文件行数 < 220 | 截取全部已有行 |
| AWR 章节 > 18 | 仅保留前 18 个章节 |
| SQL 条目 > 15 条 | 每种 SQL 类别压缩到 10-15 条 |
| 规则数据不足 | 等级设为"信息不足"，不编造数据 |
| Prompt 过长 | 摘要截断 60000 字符，规则发现截断 16000 字符 |
| matplotlib 未安装 | 图表生成静默跳过 |
| 模板不包含 sectPr | 使用默认 A4 页面设置 |
| 多编码 AWR | 自动探测 utf-8 → utf-8-sig → gb18030 → latin-1 |

---

## 14. 附录：规则引擎说明

### 14.1 规则引擎设计原则

1. **证据优先**：每条规则必须引用具体 AWR 指标作为证据
2. **明确边界**：数据不足时明确写"证据不足，不做强判断"
3. **等级递进**：高/中/低/信息不足四级判定
4. **可追溯**：每条规则输出原始证据值和推荐阈值
5. **可扩展**：`add_rule_finding()` 统一接口，新增规则只需调用一次

### 14.2 规则引擎输出格式

```json
{
  "source_file": "/tmp/data/awr_orcl_1_100_101.html",
  "generated_at": "2026-06-05T12:00:00",
  "computed_metrics": {
    "Elapsed Time(mins)": "60.25",
    "DB Time(mins)": "180.50",
    "Average Active Sessions": "3.00",
    "CPUs": "8",
    "DB CPU / DB Time": "35.20%"
  },
  "findings": [
    {
      "rule": "AAS 负载",
      "level": "中",
      "finding": "AAS/CPU=0.38",
      "evidence": "DB Time=03:00:00，Elapsed=01:00:00，CPUs=8",
      "recommendation": "结合业务峰值和 OS CPU 使用率确认是否存在容量压力。"
    }
  ]
}
```

### 14.3 规则与报告章节对照

| 报告章节 | 对应规则 | 数据来源 |
|---------|---------|---------|
| 3. 数据库负载画像 | A1 AAS 负载, A2 CPU 型负载 | Load Profile, DB Time |
| 4. Top Wait Events | A3 等待集中, B1-B5 等待阈值 | Foreground Wait Events |
| 5. Top SQL | C1 Hard Parse, C2 Exec to Parse, D1 SQL 集中 | SQL ordered by Elapsed/CPU/Gets |
| 6. 主机资源 | A1 AAS 负载 | Host CPU, Load Profile |
| 7. 内存与参数 | — | Buffer Cache / PGA / SGA Advisory |
| 8. 问题点清单 | 综合所有规则 | 规则引擎 findings |
| 9. 整改建议 | 综合所有规则 | 规则引擎 recommendations |

---

> **文档版本记录**
> 
> | 版本 | 日期 | 变更内容 |
> |------|------|---------|
> | v1.0 | 2026-03 | 初始 .lst 解析 + 原生 Word 生成 |
> | v2.0 | 2026-04 | AWR HTML 解析 + 规则引擎 + LLM Prompt |
> | v2.1 | 2026-05 | 双面板 DeepSeek 配置 + 在线模型支持 |
> | v2.2 | 2026-05 | 图表可视化 (matplotlib) + 金融风格配色 |
> | v3.0 | 2026-06 | AWR 页面模型选择器 + SSL 修复 + 完整文档化 |
