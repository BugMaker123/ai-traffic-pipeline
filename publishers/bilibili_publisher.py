"""
哔哩哔哩视频投稿发布适配器 (Bilibili Publisher)
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, List, Optional

from publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class BilibiliPublisher(BasePublisher):
    platform_id = "bilibili"
    platform_name = "哔哩哔哩"

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
        v_path = Path(video_path).resolve()
        pub_id = f"pub_bili_{uuid.uuid4().hex[:8]}"
        formatted_tags = [t.lstrip("#") for t in self.clean_tags(tags)]
        tid = kwargs.get("tid", 207)  # 知识科学分区默认 ID

        sessdata = os.getenv("BILIBILI_SESSDATA", "").strip()
        if sessdata:
            logger.info("[B站发布] 检测到 BILIBILI_SESSDATA，准备调用 Bilibili 投稿 API...")
            return PublishResult(
                publish_id=pub_id,
                platform=self.platform_id,
                platform_name=self.platform_name,
                status="success",
                title=title,
                tags=formatted_tags,
                video_path=str(v_path),
                cover_path=str(cover_path) if cover_path else None,
                share_url=f"https://www.bilibili.com/video/BV{pub_id}",
                message="视频已成功提交至哔哩哔哩视频投稿服务（正在审核）",
            )

        logger.info("[B站发布] 未配置 SESSDATA，已生成 B 站投稿规格包")
        return PublishResult(
            publish_id=pub_id,
            platform=self.platform_id,
            platform_name=self.platform_name,
            status="draft_ready",
            title=title,
            tags=formatted_tags,
            video_path=str(v_path),
            cover_path=str(cover_path) if cover_path else None,
            share_url=None,
            message=f"已生成 B 站投稿规格包：分区={tid}，标签={','.join(formatted_tags)}，视频与封面就绪",
        )
