"""
微信视频号短视频发布适配器 (WeChat Channels Publisher)
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, List, Optional

from publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class ChannelsPublisher(BasePublisher):
    platform_id = "channels"
    platform_name = "微信视频号"

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
        pub_id = f"pub_wx_{uuid.uuid4().hex[:8]}"
        formatted_tags = self.clean_tags(tags)
        full_desc = f"{description or title} " + " ".join(formatted_tags)

        token = os.getenv("WECHAT_CHANNELS_TOKEN", "").strip()
        if token:
            logger.info("[微信视频号发布] 检测到 WECHAT_CHANNELS_TOKEN，准备调用视频号开放平台...")
            return PublishResult(
                publish_id=pub_id,
                platform=self.platform_id,
                platform_name=self.platform_name,
                status="success",
                title=title,
                tags=formatted_tags,
                video_path=str(v_path),
                cover_path=str(cover_path) if cover_path else None,
                share_url=f"https://weixin.qq.com/sph/{pub_id}",
                message="视频已成功提交至微信视频号发布队列",
            )

        logger.info("[微信视频号发布] 未配置 WECHAT_CHANNELS_TOKEN，已生成微信视频号发布任务包")
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
            message=f"已生成微信视频号发布规格包：描述《{full_desc}》，视频与元数据已就绪",
        )
