"""oracle-tfa-analyzer: 本地 Oracle TFA 日志自动分析工具。

核心流程:
  1. 接收已脱敏的 TFA zip 包路径
  2. 解压到临时目录
  3. 按八大方向扫描日志文件，匹配规则库
  4. 生成 evidence.json（所有发现的证据）
  5. 基于 evidence.json 生成领导汇报版 + 技术专家版 Word 报告
"""
