"""
awr_auto_analyzer.rules_guide — 规则引擎说明文档附录

提供全部 20 条预定义规则的详细说明，包括：
- 规则名称与分组
- 判断逻辑与阈值定义
- 数据来源（AWR 章节）
- 触发等级说明
- 优化建议解读

用于在 Word 报告末尾以附录形式呈现。
"""

RULES_GROUPS = [
    # ═══════════════════════════════════════════
    # 基础组 — 原有 8 条规则
    # ═══════════════════════════════════════════
    {
        "group": "一、基础负载分析",
        "icon": "📊",
        "description": "基于 AWR 报告头部和 Load Profile 中的关键指标，评估系统整体负载水平和 CPU 使用情况。",
        "rules": [
            {
                "id": 1,
                "name": "AAS 负载",
                "brief": "评估系统平均活跃会话数与 CPU 核心数的比值，判断是否存在容量压力。",
                "logic": "AAS ÷ CPUs",
                "thresholds": "🟥 高 ≥ 0.7 🟧 中 ≥ 0.3 🟩 低 < 0.3",
                "source": "AWR 基本信息（DB Time、Elapsed Time、CPUs、Average Active Sessions）",
                "action": "AAS/CPU > 0.7 表示系统接近饱和，需结合 OS CPU 使用率和业务峰值确认是否扩容。AAS/CPU 在 0.3~0.7 之间需关注趋势。",
            },
            {
                "id": 2,
                "name": "CPU 型负载",
                "brief": "判断 DB CPU 在 DB Time 中的占比，识别是否为 CPU 密集型负载。",
                "logic": "DB CPU(s) ÷ DB Time(s)",
                "thresholds": "🟥 高 > 70% 🟩 低 ≤ 70%",
                "source": "Load Profile → DB CPU(s)、DB Time(s)",
                "action": "DB CPU 占比 > 70% 时优先核查 Top SQL 执行计划和主机 CPU 饱和度。占比 ≤ 70% 时继续结合等待事件判断瓶颈类型。",
            },
            {
                "id": 3,
                "name": "Top 等待集中",
                "brief": "检查 Top 1 等待事件占 DB Time 的比例，判断等待是否高度集中。",
                "logic": "Top 1 等待事件 %DB Time",
                "thresholds": "🟥 高 > 40% 🟩 低 ≤ 40%",
                "source": "Top Timed Events / Foreground Wait Events → %DB Time",
                "action": "> 40% 表示等待高度集中，应围绕该等待事件做 SQL、对象和系统层取证。",
            },
            {
                "id": 4,
                "name": "关键等待事件阈值",
                "brief": "检查 5 个关键等待事件的平均等待时间是否超过健康阈值。",
                "logic": "Avg Wait Time（平均等待时间）",
                "thresholds": (
                    "🟥 超过阈值（具体阈值见下表）：\n"
                    "　• log file sync：10ms\n"
                    "　• log file parallel write：10ms\n"
                    "　• db file sequential read：10ms\n"
                    "　• db file scattered read：20ms\n"
                    "　• direct path read：20ms"
                ),
                "source": "Top Timed Events / Foreground Wait Events → Avg Wait",
                "action": "log file sync/parallel write 超标 => 检查 redo log 写入和存储延迟；db file sequential/scattered read 超标 => 检查 SQL 访问路径和存储 I/O；direct path read 超标 => 检查并行查询和直接路径读场景。",
            },
            {
                "id": 5,
                "name": "Hard Parse",
                "brief": "评估每秒硬解析次数，判断共享池是否面临过多硬解析压力。",
                "logic": "Hard parses/s",
                "thresholds": "🟧 中 > 10/s 🟩 低 ≤ 10/s",
                "source": "Load Profile → Hard parses",
                "action": "> 10/s 时重点检查绑定变量使用、共享池大小、SQL 版本数和游标共享情况。",
            },
            {
                "id": 6,
                "name": "Execute to Parse",
                "brief": "评估游标重用效率，判断应用是否有效利用游标缓存。",
                "logic": "Execute to Parse %",
                "thresholds": "🟧 中 < 70% 🟩 低 ≥ 70%",
                "source": "Instance Efficiency → Execute to Parse %",
                "action": "< 70% 表示游标复用不足，需检查会话缓存游标、应用短连接和 SQL 解析模式。",
            },
            {
                "id": 7,
                "name": "Top SQL 负载集中",
                "brief": "判断 Top 1 SQL 占 Elapsed Time / DB Time 的比例。",
                "logic": "Top 1 SQL %Total",
                "thresholds": "🟥 高 > 20% 🟩 低 ≤ 20%",
                "source": "SQL ordered by Elapsed Time → %Total 或 %DB Time",
                "action": "> 20% 时优先获取该 SQL 的执行计划和统计信息，评估 SQL 改写或索引优化方案。",
            },
            {
                "id": 8,
                "name": "RAC Global Cache",
                "brief": "检查 RAC 环境下 gc 等待事件占比。",
                "logic": "gc 类等待事件最大 %DB Time",
                "thresholds": "🟥 中高 > 10% 🟩 低 ≤ 10%",
                "source": "Top Timed Events → gc 等待事件（gc cr/current block、gc buffer busy 等）",
                "action": "> 10% 时检查跨实例访问、热点块、服务部署亲和性和对象分区策略。",
            },
        ],
    },
    # ═══════════════════════════════════════════
    # A 组 — IO 吞吐分析（新增 3 条）
    # ═══════════════════════════════════════════
    {
        "group": "二、IO 吞吐分析（A 组）",
        "icon": "💾",
        "description": "基于 Load Profile 中的 IO 吞吐指标，评估系统的逻辑读、物理读和 Redo 生成率是否在合理范围内。",
        "rules": [
            {
                "id": 9,
                "name": "逻辑读吞吐",
                "brief": "评估每秒逻辑读（Logical reads/s）是否过高，反映 Buffer Cache 访问密集度。",
                "logic": "Logical reads/s（从 Load Profile 获取）",
                "thresholds": "🟥 高 ≥ 500K/s 🟧 中 ≥ 100K/s 🟩 低 < 100K/s",
                "source": "Load Profile → Logical reads（Per Second）",
                "action": "≥ 500K/s 时需结合 Top SQL by Gets 确认逻辑读消耗来源，重点优化 SQL 访问路径、索引使用和执行计划。",
            },
            {
                "id": 10,
                "name": "物理读吞吐",
                "brief": "评估每秒物理读（Physical reads/s）是否过高，反映 I/O 子系统的负载压力。",
                "logic": "Physical reads/s（从 Load Profile 获取）",
                "thresholds": "🟥 高 ≥ 50K/s 🟧 中 ≥ 10K/s 🟩 低 < 10K/s",
                "source": "Load Profile → Physical reads（Per Second）",
                "action": "≥ 50K/s 时检查 I/O 子系统和 Top SQL by Reads，评估是否需要增大 Buffer Cache 或优化 SQL 减少物理 I/O。",
            },
            {
                "id": 11,
                "name": "Redo 生成率",
                "brief": "评估每秒 Redo 生成量（Redo size/s），判断数据库写入负载强度。",
                "logic": "Redo size/s（从 Load Profile 获取）",
                "thresholds": "🟥 高 ≥ 5MB/s 🟧 中 ≥ 1MB/s 🟩 低 < 1MB/s",
                "source": "Load Profile → Redo size（Per Second）",
                "action": "≥ 5MB/s 时检查大批量 DML 操作，评估归档日志空间和 Data Guard 带宽。1~5MB/s 时关注日志切换频率。",
            },
        ],
    },
    # ═══════════════════════════════════════════
    # B 组 — 命中率分析（新增 4 条）
    # ═══════════════════════════════════════════
    {
        "group": "三、命中率分析（B 组）",
        "icon": "🎯",
        "description": "基于 Instance Efficiency 指标评估各缓存的命中率，低命中率可能意味着内存配置不足或 SQL 效率问题。",
        "rules": [
            {
                "id": 12,
                "name": "Buffer Hit 命中率",
                "brief": "评估 Buffer Cache 的命中率，低命中率意味着过多的物理 I/O。",
                "logic": "Buffer Hit %（从 Instance Efficiency 获取）",
                "thresholds": "🟥 高 < 90% 🟧 中 90%~95% 🟩 低 ≥ 95%",
                "source": "Instance Efficiency → Buffer Hit %",
                "action": "< 90% 时检查 Buffer Cache 大小、Top SQL 逻辑读分布和 DB Cache Advisory。90~95% 时关注物理读趋势。",
            },
            {
                "id": 13,
                "name": "Library Cache 命中率",
                "brief": "评估 Library Cache 命中率，反映 SQL 解析和游标共享效率。",
                "logic": "Library Hit %（从 Instance Efficiency 获取）",
                "thresholds": "🟥 高 < 95% 🟧 中 95%~98% 🟩 低 ≥ 98%",
                "source": "Instance Efficiency → Library Hit %",
                "action": "< 95% 时检查共享池大小、解析压力和 SQL 版本数。95~98% 时关注解析行为和应用连接池复用。",
            },
            {
                "id": 14,
                "name": "Latch Hit 命中率",
                "brief": "评估 Latch 获取命中率，低命中率意味着严重的内部锁争用。",
                "logic": "Latch Hit %（从 Instance Efficiency 获取）",
                "thresholds": "🟥 高 < 98% 🟧 中 98%~99% 🟩 低 ≥ 99%",
                "source": "Instance Efficiency → Latch Hit %",
                "action": "< 98% 时需结合 Latch 子类（shared pool、library cache）和 Top SQL 热点排查争用根因。",
            },
            {
                "id": 15,
                "name": "Soft Parse 比例",
                "brief": "评估软解析占全部解析的比例，反映绑定变量和游标共享的使用情况。",
                "logic": "Soft Parse %（从 Instance Efficiency 获取）",
                "thresholds": "🟥 高 < 95% 🟧 中 95%~99% 🟩 低 ≥ 99%",
                "source": "Instance Efficiency → Soft Parse %",
                "action": "< 95% 时重点检查应用是否缺少绑定变量、SQL 是否大量拼接以及共享池参数配置。",
            },
        ],
    },
    # ═══════════════════════════════════════════
    # C 组 — SQL 分类分析（新增 3 条）
    # ═══════════════════════════════════════════
    {
        "group": "四、SQL 分类分析（C 组）",
        "icon": "🔍",
        "description": "对 Top SQL 按不同维度（Buffer Gets、Physical Reads、Executions）进行分类分析，识别不同维度的风险 SQL。",
        "rules": [
            {
                "id": 16,
                "name": "Top SQL by Gets",
                "brief": "检查 SQL ordered by Gets 中第一条 SQL 的 Buffer Gets 是否过高。",
                "logic": "Top SQL by Gets → Buffer Gets（或 Buffer Gets per Exec）",
                "thresholds": "🟥 高 > 5,000 🟩 低 ≤ 5,000",
                "source": "SQL ordered by Gets → Buffer Gets / Buffer Gets per Exec",
                "action": "> 5,000 时审查该 SQL 执行计划是否存在全表扫描或索引使用不当，优化索引或 SQL 改写。",
            },
            {
                "id": 17,
                "name": "Top SQL by Reads",
                "brief": "检查 SQL ordered by Reads 中第一条 SQL 的 Physical Reads 是否过高。",
                "logic": "Top SQL by Reads → Physical Reads（或 Physical Reads per Exec）",
                "thresholds": "🟥 高 > 1,000 🟩 低 ≤ 1,000",
                "source": "SQL ordered by Reads → Physical Reads / Physical Reads per Exec",
                "action": "> 1,000 时检查该 SQL 的访问路径和对象统计信息，评估 Hint 或物化视图等方式减少物理 I/O。",
            },
            {
                "id": 18,
                "name": "高频执行 SQL",
                "brief": "检查 SQL ordered by Executions 中第一条 SQL 的执行频率是否过高。",
                "logic": "Top SQL by Executions → Executions",
                "thresholds": "🟥 高 > 100K 🟧 中 > 50K 🟩 低 ≤ 50K",
                "source": "SQL ordered by Executions → Executions",
                "action": "> 100K 时评估该 SQL 每次执行效率（逻辑读/执行、I/O 等），确认是否需要批量处理或改进应用缓存。",
            },
        ],
    },
    # ═══════════════════════════════════════════
    # D 组 — Segment 热点分析（新增 2 条）
    # ═══════════════════════════════════════════
    {
        "group": "五、Segment 热点分析（D 组）",
        "icon": "🔥",
        "description": "基于段级等待统计（Segments by Row Lock Waits、Segments by ITL Waits），识别存在锁争用或 ITL 争用的热点对象。",
        "rules": [
            {
                "id": 19,
                "name": "热点段争用",
                "brief": "检查 Segments by Row Lock Waits 中是否存在行锁争用的热点对象。",
                "logic": "Segments by Row Lock Waits → Row Lock Waits",
                "thresholds": "🟥 高 > 0 等待数",
                "source": "Segments by Row Lock Waits → Object Name、Row Lock Waits",
                "action": "存在 > 0 的行锁等待时，检查该段上是否存在大量并发 DML 导致的锁争用，评估分区、并发控制或应用逻辑改造方案。",
            },
            {
                "id": 20,
                "name": "ITL 等待",
                "brief": "检查 Segments by ITL Waits 中是否存在 ITL 争用的对象（事务槽不足）。",
                "logic": "Segments by ITL Waits → ITL Waits",
                "thresholds": "🟥 中高 > 0 等待数",
                "source": "Segments by ITL Waits → Object Name、ITL Waits",
                "action": "存在 > 0 的 ITL 等待时检查该对象的 INITRANS、PCTFREE 设置，考虑增大 INITRANS 或减小数据块大小。",
            },
        ],
    },
]


def render_rules_guide_markdown() -> str:
    """生成规则说明 Markdown 文本，用于 Word 报告附录。"""
    lines = [
        "# 附录：AWR 规则引擎说明",
        "",
        "本文档对 AWR 自动分析器中全部 20 条预定义规则进行详细说明，包括判断逻辑、阈值定义、",
        "数据来源和优化建议解读。",
        "",
        "---",
        "",
    ]

    for group in RULES_GROUPS:
        lines.append(f"## {group['icon']} {group['group']}")
        lines.append("")
        lines.append(group["description"])
        lines.append("")
        lines.append("| 序号 | 规则名称 | 简要说明 | 判断逻辑 | 阈值定义 | 数据来源 | 优化建议 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for rule in group["rules"]:
            lines.append(
                "| "
                + str(rule["id"])
                + " | "
                + rule["name"]
                + " | "
                + rule["brief"]
                + " | "
                + rule["logic"]
                + " | "
                + rule["thresholds"].replace("\n", "<br>")
                + " | "
                + rule["source"]
                + " | "
                + rule["action"]
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "### 等级含义",
            "",
            "| 等级 | 含义 | 处理优先级 |",
            "| --- | --- | --- |",
            "| 🟥 高 / 中高 | 需立即关注，存在显著性能风险 | 🔴 高 |",
            "| 🟧 中 | 需持续观察，可能存在隐患 | 🟡 中 |",
            "| 🟩 低 | 当前表现正常 | 🟢 低 |",
            "| ℹ️ 信息不足 | 缺少必要数据，无法做出判断 | ⚪ 待补充 |",
            "",
            "---",
            "",
            "*本附录由 awr-auto-analyzer 规则引擎自动生成，用于辅助理解规则判断结果。*",
            "",
        ]
    )

    return "\n".join(lines)
