"""TFA zip 解压与文件发现模块。

支持两类文件来源：
  A. 标准路径下的日志（alert_log, listener_log, crs_log …）— 通过 FILE_PATTERNS glob 匹配
  B. TFA 根目录下的 {hostname}_{SUFFIX} 快照文件 — 通过 ROOT_SNAPSHOT_CLASSIFIER 自动分类
"""

import zipfile
import shutil
import logging
import re
from pathlib import Path
from typing import Optional
from .config import TEMP_DIR, FILE_PATTERNS, ROOT_SNAPSHOT_CLASSIFIER, CATEGORY_MAP

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# TFA zip 文件名解析
# ──────────────────────────────────────────────

# 常见格式（自动解压后）：
#   pa00db12.tfa_Sat_Apr_25_10_51_31_CST_2026.zip
#   hxdb01.tfa_Mon_May_26_17_30_11_GMT+08_00_2025.zip
_TFA_ZIP_RE = re.compile(
    r"^(.+?)\.tfa(_[A-Z][a-z]{2}_[A-Z][a-z]{2}_\d{2}_\d{2}_\d{2}_\d{2}_(?:\w+[+-]\d{2}_\d{2}|\w+)_\d{4})?\.zip$"
)


def parse_tfa_filename(filename: str) -> dict:
    """从 TFA zip 文件名提取主机名和时间元数据。

    Returns:
        {"hostname": str, "collection_ts": str | None, "raw": str}
    """
    result: dict = {"hostname": filename, "collection_ts": None, "raw": filename}
    m = _TFA_ZIP_RE.match(filename)
    if m:
        result["hostname"] = m.group(1)
        result["collection_ts"] = m.group(2).lstrip("_") if m.group(2) else None
    return result


# ──────────────────────────────────────────────
# 主机名前缀检测
# ──────────────────────────────────────────────


def _detect_hostname(extract_dir: Path) -> Optional[str]:
    """通过扫描 TFA 解压目录下的快照文件推测主机名前缀。

    TFA zip 解压后结构：
        extract_dir/
        ├── {hostname}/              ← 快照文件在此目录中
        │   ├── {hostname}_{SUFFIX}  ← 80+ 个命令快照
        │   └── diag/...
        ├── TFA.txt
        └── {hostname}.diagcollect.log

    策略：先查找一级子目录（排除已知元数据文件），如果子目录名
    与 ROOT_SNAPSHOT_CLASSIFIER 后缀有交集则投票选出 hostname。
    也可从 zip 元数据文件名推断。
    """
    suffix_set = set(ROOT_SNAPSHOT_CLASSIFIER.keys())
    suffix_lower = {s.lower() for s in suffix_set}

    candidates: dict[str, int] = {}

    # 策略 1：扫描可能的一级子目录下的快照文件
    for child in extract_dir.iterdir():
        if child.is_dir():
            # 非隐藏目录作为候选主机名目录
            dir_name = child.name
            if dir_name.startswith("."):
                continue
            for sub in child.iterdir():
                if sub.is_file():
                    stem = sub.stem
                    parts = stem.split("_", 1)
                    if len(parts) == 2:
                        potential_host, potential_suffix = parts
                        if (potential_suffix.lower() in suffix_lower
                                and potential_host == dir_name):
                            candidates[dir_name] = candidates.get(dir_name, 0) + 1

    # 策略 2：从根级 {hostname}.diagcollect.log / {hostname}.tfa_main.trc 推断
    for child in extract_dir.iterdir():
        if child.is_file():
            name = child.name
            for suffix in (".diagcollect.log", ".tfa_main.trc", ".zip_inventory.csv"):
                if name.endswith(suffix):
                    potential_host = name[: -len(suffix)]
                    if potential_host:
                        candidates[potential_host] = candidates.get(potential_host, 0) + 3  # 高权重

    if not candidates:
        logger.warning("无法自动检测 TFA 主机名（未找到快照文件或元数据文件）")
        return None

    best = max(candidates, key=lambda k: candidates[k])
    logger.debug("检测到 TFA 主机名前缀: %s (共 %d 个候选文件)", best, candidates[best])
    return best

    #     # 也检查带扩展名的变体：{suffix}.out / {suffix}.log 等
    #     for ext in ("", ".out", ".log", ".txt", ".dat"):
    #         check = (stem if not ext else stem) + ext
    #         ... (上述逻辑已覆盖)


# ──────────────────────────────────────────────
# 根目录快照发现
# ──────────────────────────────────────────────


def discover_root_snapshots(extract_dir: Path, hostname: str) -> dict[str, list[Path]]:
    """发现 TFA 根目录下的 {hostname}_{SUFFIX} 快照文件。

    返回分类字典，key 为 ROOT_SNAPSHOT_CLASSIFIER 中的细粒度类别名。
    """
    result: dict[str, list[Path]] = {}

    # 构建后缀 → 细粒度类别 映射（大小写不敏感）
    suffix_to_category: dict[str, str] = {
        k.lower(): v for k, v in ROOT_SNAPSHOT_CLASSIFIER.items()
    }

    host_prefix = hostname + "_"
    for child in extract_dir.iterdir():
        if not child.is_file():
            continue
        name = child.name
        if not name.startswith(host_prefix):
            continue

        # 去掉前缀后剩下的部分
        remainder = name[len(host_prefix) :]
        # 尝试 FULL 匹配（处理 "SRCFG.json" → remainder="SRCFG.json"）
        full_key = remainder.lower()
        cat = suffix_to_category.get(full_key)

        if cat is None:
            # 尝试 stem 匹配（去掉扩展名，如 "CHECKCRS.out" → stem="CHECKCRS"）
            stem_only = Path(remainder).stem
            stem_key = stem_only.lower()
            cat = suffix_to_category.get(stem_key)

        if cat is not None:
            result.setdefault(cat, []).append(child)
        else:
            # 收集未知快照以便调试
            result.setdefault("_unknown_snapshots", []).append(child)

    # 排序使输出稳定
    for k in result:
        result[k] = sorted(result[k])

    logger.debug(
        "根目录快照发现: %s 个分类，共 %d 文件",
        len([k for k in result if not k.startswith("_")]),
        sum(len(v) for k, v in result.items() if not k.startswith("_")),
    )
    return result


# ──────────────────────────────────────────────
# 统一文件发现入口
# ──────────────────────────────────────────────


def discover_files(extract_dir: Path) -> dict[str, list[Path]]:
    """发现 TFA 解压目录下所有可分析文件。

    返回分类字典，包含：
      - 来自 FILE_PATTERNS 的标准日志类别（在 {hostname}/ 子树下匹配）
      - 来自 ROOT_SNAPSHOT_CLASSIFIER 的快照类别

    TFA zip 解压结构：
        extract_dir/
        ├── {hostname}/        ← snapshot + diag 在此目录中
        │   ├── {hostname}_*   ← 80+ 个命令快照
        │   └── diag/...
        ├── TFA.txt
        └── *.diagcollect.log
    """
    # 先检测主机名，获取主机名子目录
    hostname = _detect_hostname(extract_dir)
    base_dir = extract_dir

    # 如果存在 {hostname}/ 子目录，以其为扫描根目录
    if hostname:
        hostname_dir = extract_dir / hostname
        if hostname_dir.is_dir():
            base_dir = hostname_dir
            logger.debug("使用主机名子目录为扫描根: %s", base_dir)

    result: dict[str, list[Path]] = {}

    # ---- A. 标准路径 glob 匹配（基于 base_dir） ----
    for category, patterns in FILE_PATTERNS.items():
        files = []
        for pat in patterns:
            files.extend(sorted(base_dir.glob(pat)))
        if files:
            result[category] = sorted(set(files))

    # ---- B. 根目录快照匹配（基于 base_dir） ----
    if hostname:
        snapshots = discover_root_snapshots(base_dir, hostname)
        for cat, files in snapshots.items():
            if cat.startswith("_"):
                continue  # 忽略未知后缀分组
            # 并入 result
            result.setdefault(cat, []).extend(files)
            result[cat] = sorted(set(result[cat]))

    # ---- C. 空分类从结果移除（除非希望保留空键） ----
    empty_keys = [k for k, v in result.items() if not v]
    for k in empty_keys:
        del result[k]

    return result


def get_snapshot_category_mapping(snapshot_category: str) -> str:
    """将快照细粒度类别映射回顶层分析大类。

    如果映射不存在则回退到 "OS 资源"。
    """
    return CATEGORY_MAP.get(snapshot_category, "OS 资源")


# ──────────────────────────────────────────────
# 解压与清理
# ──────────────────────────────────────────────


def extract_tfa_zip(zip_path: str | Path, target_dir: str | Path | None = None) -> Path:
    zip_path = Path(zip_path).expanduser().resolve()
    if not zip_path.exists() or not zip_path.is_file():
        raise FileNotFoundError(f"TFA zip 包不存在或不是文件: {zip_path}")
    if zip_path.suffix.lower() not in (".zip",):
        raise ValueError(f"不支持的文件类型，仅接受 .zip: {zip_path.suffix}")

    target = Path(target_dir) if target_dir else (TEMP_DIR / zip_path.stem)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=False)

    logger.info("正在解压 %s 到 %s ...", zip_path.name, target)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)

    total_files = sum(1 for _ in target.rglob("*") if _.is_file())
    logger.info("解压完成，共 %d 个文件", total_files)
    return target


def cleanup_temp(extract_dir: Path):
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
        logger.info("已清理临时目录 %s", extract_dir)
