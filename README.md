# ProjectMgr

## 目录结构

```text
ProjectMgr/
  app/                    # 现有 Web 应用代码
  data/                   # 输入数据，例如 Oracle .lst 报告
    oracle_perf_compare.lst
  scripts/                # 离线分析脚本
    parse_oracle_lst.py   # 解析 .lst 并生成 JSON
    ask_local_deepseek.py # 调用本地 DeepSeek/Ollama 风格接口分析 JSON
  output/                 # 脚本输出目录
    result.json
```

## Oracle 性能报告分析

解析 `.lst`：

```bash
python scripts/parse_oracle_lst.py \
  --input data/oracle_perf_compare.lst \
  --output output/result.json
```

调用本地 DeepSeek：

```bash
python scripts/ask_local_deepseek.py --input output/result.json
```

也可以启动 Web 工作台，在左侧菜单进入 `AI 分析 -> 本地 DeepSeek`，选择 `data/` 目录下的 `.lst` 文件或手动输入 AWR 报告路径，并选择 `templates/report_demo/` 下的 Word 模板后，调用当前本地模型生成模板风格的 Word 分析报告，结果会写入 `output/` 并可直接下载。AWR 支持 `.html`、`.htm`、`.txt`、`.lst`。

## 单文件脱敏

启动 Web 工作台后，在 `工作台 -> 扫描与脱敏` 中使用 `单文件脱敏`。输入本机文件路径后，系统会按金融行业敏感信息规则在同目录生成 `*_desensitized` 新文件，并提供处理报告下载。源文件不会被修改。

默认模型接口为 `http://127.0.0.1:11434/api/chat`，默认模型名为 `deepseek-r1`。可以通过环境变量调整：

```bash
export LOCAL_DEEPSEEK_URL="http://127.0.0.1:11434/api/chat"
export LOCAL_DEEPSEEK_MODEL="deepseek-r1"
```
