"""受 OUTPUT_DIR 边界保护的过期产物清理工具。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from config.settings import OUTPUT_DIR, OUTPUT_RETENTION_HOURS


def find_expired_outputs(now: float | None = None, retention_hours: int = OUTPUT_RETENTION_HOURS) -> Iterable[Path]:
    root = OUTPUT_DIR.resolve()
    cutoff = (now or time.time()) - retention_hours * 3600
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix == ".json" and path.parent.name == "jobs":
            continue
        resolved = path.resolve()
        if root not in resolved.parents:
            continue
        if path.stat().st_mtime < cutoff:
            yield path


def cleanup_expired_outputs(*, dry_run: bool = True, retention_hours: int = OUTPUT_RETENTION_HOURS) -> list[Path]:
    targets = list(find_expired_outputs(retention_hours=retention_hours))
    if not dry_run:
        for path in targets:
            path.unlink(missing_ok=True)
    return targets


def cleanup_incomplete_outputs() -> list[Path]:
    """清理渲染中断留下的临时文件和明显损坏的 MP4。"""
    removed: list[Path] = []
    for path in OUTPUT_DIR.rglob("*"):
        if not path.is_file():
            continue
        is_temp = path.name.startswith(".") and ".tmp." in path.name
        is_broken_mp4 = path.suffix.lower() == ".mp4" and path.stat().st_size < 1024
        if is_temp or is_broken_mp4:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed
