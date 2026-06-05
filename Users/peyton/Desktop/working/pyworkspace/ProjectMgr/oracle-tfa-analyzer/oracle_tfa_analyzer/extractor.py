"""TFA zip 解压与文件发现模块。"""

import zipfile
import shutil
import logging
from pathlib import Path
from .config import TEMP_DIR, FILE_PATTERNS

logger = logging.getLogger(__name__)


def extract_tfa_zip(zip_path: str | Path, target_dir: str | Path | None = None) -> Path:
    """将 TFA zip 包解压到目标目录。返回目标目录 Path。"""
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

    logger.info("解压完成，共 %d 个文件", sum(1 for _ in target.rglob("*") if _.is_file()))
    return target


def discover_files(extract_dir: Path) -> dict[str, list[Path]]:
    """根据 FILE_PATTERNS 在解压目录中发现各类文件。"""
    result: dict[str, list[Path]] = {}
    for category, patterns in FILE_PATTERNS.items():
        files = []
        for pat in patterns:
            files.extend(sorted(extract_dir.glob(pat)))
        result[category] = files
    return result


def cleanup_temp(extract_dir: Path):
    """清理临时解压目录。"""
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
        logger.info("已清理临时目录 %s", extract_dir)
