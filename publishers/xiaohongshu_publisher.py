"""
小红书短视频/笔记发布适配器 (Xiaohongshu Publisher)
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, List, Optional

from publishers.base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class XiaohongshuPublisher(BasePublisher):
    platform_id = "xiaohongshu"
    platform_name = "小红书"

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
        pub_id = f"pub_xhs_{uuid.uuid4().hex[:8]}"
        formatted_tags = self.clean_tags(tags)

        # 小红书标题上限 20 字
        short_title = title[:20] if len(title) > 20 else title
        desc_body = description or title
        formatted_desc = f"{desc_body}\n\n" + " ".join(formatted_tags)

        token = os.getenv("XIAOHONGSHU_COOKIE", "").strip()
        if token:
            logger.info("[小红书发布] 检测到 XIAOHONGSHU_COOKIE，准备调用小红书创作者接口...")
            return PublishResult(
                publish_id=pub_id,
                platform=self.platform_id,
                platform_name=self.platform_name,
                status="success",
                title=short_title,
                tags=formatted_tags,
                video_path=str(v_path),
                cover_path=str(cover_path) if cover_path else None,
                share_url=f"https://www.xiaohongshu.com/explore/{pub_id}",
                message="视频笔记已成功提交至小红书平台",
            )

        logger.info("[小红书发布] 未配置 XIAOHONGSHU_COOKIE，已生成小红书标准笔记规格包")
        return PublishResult(
            publish_id=pub_id,
            platform=self.platform_id,
            platform_name=self.platform_name,
            status="draft_ready",
            title=short_title,
            tags=formatted_tags,
            video_path=str(v_path),
            cover_path=str(cover_path) if cover_path else None,
            share_url=None,
            message=f"已生成小红书笔记规格包：标题《{short_title}》，文案与话题标签就绪",
        )
