"""
多平台发布器抽象基类与通用数据模型 (Base Publisher Protocol)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class PublishResult(BaseModel):
    publish_id: str
    platform: str
    platform_name: str
    status: str = "success"  # success | draft_ready | failed
    title: str
    tags: List[str] = Field(default_factory=list)
    video_path: str
    cover_path: Optional[str] = None
    share_url: Optional[str] = None
    message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BasePublisher(ABC):
    """自媒体平台发布适配器基类"""

    platform_id: str = "base"
    platform_name: str = "通用平台"

    @classmethod
    def clean_tags(cls, tags: List[str]) -> List[str]:
        """标准化标签，确保不含空格并带井号规范"""
        cleaned = []
        for t in tags:
            tag_clean = t.strip().lstrip("#").strip()
            if tag_clean and tag_clean not in cleaned:
                cleaned.append(f"#{tag_clean}")
        return cleaned

    @abstractmethod
    async def publish(
        self,
        video_path: str | Path,
        title: str,
        tags: List[str],
        description: str = "",
        cover_path: Optional[str | Path] = None,
        schedule_time: Optional[str] = None,
        **kwargs: Any,
    ) -> PublishResult:
        """执行发布或草稿生成"""
        raise NotImplementedError
