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
