"""
awr_auto_analyzer.chart_generator — AWR 性能分析图表生成器

从已解析的 AWR summary dict 中提取关键性能指标，使用 matplotlib
生成专业风格图表（PNG），供 Word 报告嵌入使用。

使用软依赖策略：若 matplotlib 未安装，所有函数静默返回 None。
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import CHART_DIR, COLOR_PRIMARY, COLOR_ACCENT

# ── matplotlib 软导入 ──

HAS_MPL = False
try:
    import matplotlib
    matplotlib.use("Agg")  # 强制非交互后端（服务器安全）
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    HAS_MPL = True
except ImportError:
    plt = None  # type: ignore[assignment]
    fm = None

# ── 中文字体探测 ──

_CN_FONT: str | None = None


def _resolve_cn_font() -> str | None:
    """探测系统可用的中文字体名，返回 matplotlib 可用 fontname。"""
    global _CN_FONT
    if _CN_FONT is not None:
        return _CN_FONT
    if fm is None:
        _CN_FONT = None
        return None
    candidates = [
        "PingFang SC",
        "PingFang HK",
        "Microsoft YaHei",
        "WenQuanYi Micro Hei",
        "Noto Sans CJK SC",
        "SimHei",
        "STHeiti",
        "Arial Unicode MS",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            _CN_FONT = name
            return name
    # Fallback — 尝试通过文件路径查找
    import platform
    if platform.system() == "Darwin":
        for p in Path("/System/Library/Fonts").glob("PingFang*"):
            try:
                fp = fm.FontProperties(fname=str(p))
                _CN_FONT = fp.get_name()
                return _CN_FONT
            except Exception:
                continue
    _CN_FONT = None  # 无中文字体
    return None


# ── 全局样式 ──

def _style_axis(ax, title: str = "", xlabel: str = "", ylabel: str = ""):
    """统一的坐标轴样式。"""
    cn = _resolve_cn_font()
    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", color=f"#{COLOR_PRIMARY}", fontname=cn or "sans-serif")
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=9, color="#2C3E50", fontname=cn or "sans-serif")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=9, color="#2C3E50", fontname=cn or "sans-serif")
    ax.tick_params(axis="both", labelsize=8, colors="#2C3E50")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D5DDE5")
    ax.spines["bottom"].set_color("#D5DDE5")
    if cn:
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_fontname(cn)


def _save_chart(fig, filename: str) -> Path | None:
    """保存图表到 CHART_DIR。"""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / filename
    fig.tight_layout(pad=1.2)
    fig.savefig(str(path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path if path.exists() else None


# ── 数值提取工具 ──

def _safe_float(val) -> float:
    """安全转为 float，失败返回 0.0。"""
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _try_get(records, key: str, default="0") -> float:
    """从 records[0] dict 取值（忽略大小写）。"""
    if not isinstance(records, list) or not records:
        return _safe_float(default)
    row = records[0] if isinstance(records[0], dict) else {}
    for k, v in row.items():
        if k.strip().lower() == key.strip().lower():
            return _safe_float(v)
    return _safe_float(default)


def _try_get_row_by_label(records, label: str) -> dict:
    """查找 records 中第一个 _section 匹配 label 的行。"""
    if not isinstance(records, list):
        return {}
    for row in records:
        if isinstance(row, dict) and row.get("_section", "").strip() == label:
            return row
    return {}


# ══════════════════════════════════════════════
# 1. Load Profile — Per Second 指标柱状图
# ══════════════════════════════════════════════

LOAD_PROFILE_METRICS = [
    ("Redo size", "KB/s"),
    ("Logical reads", "块/s"),
    ("Block changes", "块/s"),
    ("Physical reads", "块/s"),
    ("Physical writes", "块/s"),
    ("User calls", "次/s"),
    ("Parses", "次/s"),
    ("Hard parses", "次/s"),
    ("Sorts", "次/s"),
    ("Logons", "次/s"),
    ("Executes", "次/s"),
    ("Transactions", "次/s"),
]


def generate_load_profile_chart(summary: dict) -> Path | None:
    """Load Profile Per Second 分组柱状图。"""
    if not HAS_MPL:
        return None
    records = summary.get("Load Profile")
    if not isinstance(records, list):
        return None

    # 提取 Per Second 行
    per_sec = None
    for row in records:
        if isinstance(row, dict):
            key = row.get("", "")
            if "Per Second" in str(key):
                per_sec = row
                break
    if not per_sec:
        # Fallback: 使用第一条记录
        per_sec = records[0] if records else None
    if not per_sec:
        return None

    labels: list[str] = []
    values: list[float] = []
    for metric_key, unit in LOAD_PROFILE_METRICS:
        val = _safe_float(per_sec.get(metric_key))
        if val > 0 or metric_key in str(per_sec.keys()):
            labels.append(f"{metric_key}\n({unit})")
            values.append(val)

    if not values:
        return None

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    bars = ax.bar(range(len(values)), values, color=f"#{COLOR_PRIMARY}", width=0.6, edgecolor="white", linewidth=0.5)
    # 金色强调最大值
    if bars:
        max_idx = max(range(len(values)), key=lambda i: values[i])
        bars[max_idx].set_color(f"#{COLOR_ACCENT}")

    _style_axis(ax, title="Load Profile — Per Second 指标")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7, rotation=25, ha="right")

    # 值标注
    for i, (bar, v) in enumerate(zip(bars, values)):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v:.1f}" if v < 10000 else f"{v:.0f}",
                    ha="center", va="bottom", fontsize=6, color="#2C3E50")

    return _save_chart(fig, "awr_load_profile.png")


# ══════════════════════════════════════════════
# 2. Top Wait Events — 水平条形图
# ══════════════════════════════════════════════

def generate_wait_events_chart(summary: dict) -> Path | None:
    """Top Timed Events 等待事件水平条形图。"""
    if not HAS_MPL:
        return None
    records = summary.get("Top Timed Events / Foreground Wait Events")
    if not isinstance(records, list) or not records:
        return None

    events: list[tuple[str, float]] = []
    for row in records[:10]:
        if not isinstance(row, dict):
            continue
        event = str(row.get("Event", row.get("", ""))).strip()
        if not event or event == "0" or "background" in event.lower():
            continue
        # 尝试多种列名
        pct = _safe_float(row.get("%Total", row.get("%Time", row.get("Waits", "0"))))
        if pct > 0:
            events.append((event, pct))

    if not events:
        return None
    # 按值升序排列（水平条形图底部最大）
    events.sort(key=lambda x: x[1])

    names, vals = zip(*events)
    fig, ax = plt.subplots(figsize=(6.5, max(3.0, len(events) * 0.45)))
    bars = ax.barh(range(len(names)), vals, color=f"#{COLOR_PRIMARY}", height=0.55, edgecolor="white", linewidth=0.5)
    if bars:
        max_idx = max(range(len(vals)), key=lambda i: vals[i])
        bars[max_idx].set_color(f"#{COLOR_ACCENT}")

    _style_axis(ax, title="Top Wait Events — % 占比")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("% Total", fontsize=9, color="#2C3E50")

    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%", va="center", fontsize=7, color=f"#{COLOR_PRIMARY}")

    return _save_chart(fig, "top_wait_events.png")


# ══════════════════════════════════════════════
# 3. Top SQL — Elapsed Time 水平条形图
# ══════════════════════════════════════════════

def generate_top_sql_chart(summary: dict) -> Path | None:
    """Top SQL by Elapsed Time 水平条形图。"""
    if not HAS_MPL:
        return None
    records = summary.get("SQL ordered by Elapsed Time")
    if not isinstance(records, list) or not records:
        return None

    sqls: list[tuple[str, float]] = []
    for row in records[:10]:
        if not isinstance(row, dict):
            continue
        sql_id = str(row.get("SQL Id", row.get("SQL ID", ""))).strip()
        elapsed = _safe_float(row.get("Elapsed Time (s)", "0"))
        if not sql_id or elapsed <= 0:
            continue
        # 截取 SQL Text 前 40 字符作为标签
        sql_text = str(row.get("SQL Text", ""))[:40].strip().replace("\n", " ")
        label = f"{sql_id} | {sql_text}" if sql_text else sql_id
        sqls.append((label, elapsed))

    if not sqls:
        return None
    sqls.sort(key=lambda x: x[1])

    names, vals = zip(*sqls)
    fig, ax = plt.subplots(figsize=(6.5, max(3.0, len(sqls) * 0.45)))
    bars = ax.barh(range(len(names)), vals, color=f"#{COLOR_PRIMARY}", height=0.55, edgecolor="white", linewidth=0.5)
    if bars:
        max_idx = max(range(len(vals)), key=lambda i: vals[i])
        bars[max_idx].set_color(f"#{COLOR_ACCENT}")

    _style_axis(ax, title="Top SQL — Elapsed Time (s)")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=6)
    ax.set_xlabel("Elapsed Time (s)", fontsize=9, color="#2C3E50")

    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}s", va="center", fontsize=7, color=f"#{COLOR_PRIMARY}")

    return _save_chart(fig, "top_sql.png")


# ══════════════════════════════════════════════
# 4. Host CPU — 利用率柱状图
# ══════════════════════════════════════════════

def generate_host_cpu_chart(summary: dict) -> Path | None:
    """Host CPU 使用率柱状图。"""
    if not HAS_MPL:
        return None
    records = summary.get("Host CPU")
    if not isinstance(records, list) or not records:
        return None

    # 查找包含 CPU 数据的记录行
    cpu_row = None
    for row in records:
        if isinstance(row, dict):
            for key in row:
                if "cpu" in key.lower() and "cores" not in key.lower():
                    cpu_row = row
                    break
        if cpu_row:
            break
    if not cpu_row:
        cpu_row = records[0]

    # 尝试提取 %Busy / %User / %System / %Idle / %WIO
    metrics = [
        ("% Busy", "%Busy"),
        ("% User", "%User"),
        ("% System", "%System"),
        ("% WIO", "%WIO"),
        ("% Idle", "%Idle"),
    ]
    values: list[tuple[str, float]] = []
    for display, key in metrics:
        val = _try_get([cpu_row], key)
        if val > 0 or display == "% Busy":
            values.append((display, val))

    if not values:
        return None

    labels = [v[0] for v in values]
    vals = [v[1] for v in values]
    colors = []
    for lbl in labels:
        if "Idle" in lbl:
            colors.append("#27AE60")
        elif "Busy" in lbl or "User" in lbl or "System" in lbl:
            colors.append(f"#{COLOR_PRIMARY}")
        elif "WIO" in lbl:
            colors.append("#E67E22")
        else:
            colors.append(f"#{COLOR_PRIMARY}")

    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bars = ax.bar(range(len(labels)), vals, color=colors, width=0.5, edgecolor="white", linewidth=0.5)

    _style_axis(ax, title="Host CPU 利用率 (%)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, max(100, max(vals) * 1.2))
    ax.axhline(y=80, color="#E74C3C", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.text(len(labels) - 0.5, 82, "警戒线 80%", fontsize=7, color="#E74C3C", ha="right")

    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{v:.1f}%", ha="center", va="bottom", fontsize=8, color="#2C3E50")

    return _save_chart(fig, "host_cpu.png")


# ══════════════════════════════════════════════
# 5. Instance Efficiency — 命中率柱状图
# ══════════════════════════════════════════════

def generate_efficiency_chart(summary: dict) -> Path | None:
    """Instance Efficiency 指标柱状图。"""
    if not HAS_MPL:
        return None
    records = summary.get("Instance Efficiency")
    if not isinstance(records, list) or not records:
        return None

    row = records[0] if isinstance(records[0], dict) else {}
    targets = [
        ("Buffer Hit %", "Buffer Hit %"),
        ("Latch Hit %", "Latch Hit %"),
        ("Library Hit %", "Library Hit %"),
        ("CPU % Total", "CPU % Total"),
        ("Exec to Parse %", "Exec to Parse %"),
        ("Soft Parse %", "Soft Parse %"),
        ("In-memory Sort %", "In-memory Sort %"),
    ]
    values: list[tuple[str, float]] = []
    for display, key in targets:
        val = _safe_float(row.get(key, "0"))
        if val > 0:
            values.append((display, val))

    if not values:
        return None

    labels = [v[0] for v in values]
    vals = [v[1] for v in values]
    # 颜色：>95% 绿色，>80% 蓝色，<80% 橙色
    colors = []
    for v in vals:
        if v >= 95:
            colors.append("#27AE60")
        elif v >= 80:
            colors.append(f"#{COLOR_PRIMARY}")
        else:
            colors.append("#E67E22")

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    bars = ax.bar(range(len(labels)), vals, color=colors, width=0.55, edgecolor="white", linewidth=0.5)

    _style_axis(ax, title="Instance Efficiency 命中率 (%)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.axhline(y=95, color="#27AE60", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.text(len(labels) - 0.5, 96, "优秀线 95%", fontsize=7, color="#27AE60", ha="right")

    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{v:.1f}%", ha="center", va="bottom", fontsize=7, color="#2C3E50")

    return _save_chart(fig, "instance_efficiency.png")


# ══════════════════════════════════════════════
# 6. Top Segments — 段访问热点水平条形图
# ══════════════════════════════════════════════

def generate_top_segments_chart(summary: dict) -> Path | None:
    """Segments by Logical Reads 水平条形图。"""
    if not HAS_MPL:
        return None
    records = summary.get("Segments by Logical Reads")
    if not isinstance(records, list) or not records:
        return None

    segments: list[tuple[str, float]] = []
    for row in records[:10]:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("Owner", "")).strip()
        obj = str(row.get("Object Name", row.get("Tablespace", ""))).strip()
        reads_val = _safe_float(row.get("Logical Reads", row.get("Buffer Gets", "0")))
        if not obj or reads_val <= 0:
            continue
        label = f"{owner}.{obj}" if owner else obj
        segments.append((label, reads_val))

    if not segments:
        # Fallback: 尝试 Physical Reads
        records = summary.get("Segments by Physical Reads")
        if isinstance(records, list):
            for row in records[:10]:
                if not isinstance(row, dict):
                    continue
                owner = str(row.get("Owner", "")).strip()
                obj = str(row.get("Object Name", row.get("Tablespace", ""))).strip()
                reads_val = _safe_float(row.get("Physical Reads", "0"))
                if not obj or reads_val <= 0:
                    continue
                label = f"{owner}.{obj}" if owner else obj
                segments.append((label, reads_val))

    if not segments:
        return None
    segments.sort(key=lambda x: x[1])

    names, vals = zip(*segments)
    fig, ax = plt.subplots(figsize=(6.5, max(3.0, len(segments) * 0.45)))
    bars = ax.barh(range(len(names)), vals, color=f"#{COLOR_PRIMARY}", height=0.55, edgecolor="white", linewidth=0.5)
    if bars:
        max_idx = max(range(len(vals)), key=lambda i: vals[i])
        bars[max_idx].set_color(f"#{COLOR_ACCENT}")

    _style_axis(ax, title="Top Segments — 访问热点")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel("Logical Reads", fontsize=9, color="#2C3E50")

    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{v:,.0f}", va="center", fontsize=7, color=f"#{COLOR_PRIMARY}")

    return _save_chart(fig, "top_segments.png")


# ══════════════════════════════════════════════
# 统一入口
# ══════════════════════════════════════════════

CHART_GENERATORS = [
    ("awr_load_profile.png", generate_load_profile_chart),
    ("top_wait_events.png", generate_wait_events_chart),
    ("top_sql.png", generate_top_sql_chart),
    ("host_cpu.png", generate_host_cpu_chart),
    ("instance_efficiency.png", generate_efficiency_chart),
    ("top_segments.png", generate_top_segments_chart),
]


def generate_all_charts(summary: dict) -> dict[str, Path]:
    """生成所有图表，返回 {文件名: Path} 字典。

    如果 matplotlib 未安装或数据不足，对应条目不存在。
    """
    if not HAS_MPL:
        print("⚠️  matplotlib 未安装，跳过图表生成")
        return {}

    results: dict[str, Path] = {}
    for filename, generator in CHART_GENERATORS:
        try:
            path = generator(summary)
            if path:
                results[filename] = path
                print(f"   ✅ 生成图表：{filename}")
            else:
                print(f"   ⏭️  跳过图表（数据不足）：{filename}")
        except Exception as exc:
            print(f"   ⚠️  图表生成异常（{filename}）：{exc}")
    print(f"📊 图表生成完成：{len(results)}/{len(CHART_GENERATORS)} 张")
    return results
