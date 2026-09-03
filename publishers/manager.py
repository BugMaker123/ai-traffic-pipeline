"""
自媒体多平台发布与矩阵分发调度中心 (Publish Manager)
统一并发调度抖音、B站、小红书、微信视频号发布任务，支持一键抗查重混淆处理与历史追踪。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from compositors.anti_duplicate import anti_duplicate_processor
from config.settings import OUTPUT_DIR
from publishers.base import BasePublisher, PublishResult
from publishers.bilibili_publisher import BilibiliPublisher
from publishers.channels_publisher import ChannelsPublisher
from publishers.douyin_publisher import DouyinPublisher
from publishers.xiaohongshu_publisher import XiaohongshuPublisher

logger = logging.getLogger(__name__)


class PublishManager:
    """自媒体矩阵多平台统一调度与日志归档中心"""

    def __init__(self, logs_dir: Optional[Path] = None):
        self.logs_dir = logs_dir or (OUTPUT_DIR / "publish_logs")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.logs_dir / "history.json"
        self._publishers: Dict[str, BasePublisher] = {
            "douyin": DouyinPublisher(),
            "bilibili": BilibiliPublisher(),
            "xiaohongshu": XiaohongshuPublisher(),
            "channels": ChannelsPublisher(),
        }

    def register_publisher(self, publisher: BasePublisher) -> None:
        self._publishers[publisher.platform_id] = publisher

    def list_supported_platforms(self) -> List[Dict[str, str]]:
        meta = {
            "douyin": {"icon": "🎵", "desc": "抖音短视频 / 创作者服务"},
            "bilibili": {"icon": "📺", "desc": "哔哩哔哩 / 视频投稿与多标签"},
            "xiaohongshu": {"icon": "📕", "desc": "小红书 / 图文视频笔记"},
            "channels": {"icon": "🟢", "desc": "微信视频号 / 社交裂变分发"},
        }
        return [
            {
                "id": pid,
                "name": pub.platform_name,
                "icon": meta.get(pid, {}).get("icon", "📱"),
                "desc": meta.get(pid, {}).get("desc", ""),
            }
            for pid, pub in self._publishers.items()
        ]

    def _read_history(self) -> List[Dict[str, Any]]:
        if not self.history_file.is_file():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("读取发布历史失败: %s", e)
            return []

    def _append_history(self, record: Dict[str, Any]) -> None:
        history = self._read_history()
        history.insert(0, record)
        # 最多保留 200 条历史记录
        history = history[:200]
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存发布历史失败: %s", e)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._read_history()[:limit]

    async def publish_to_platforms(
        self,
        video_path: str | Path,
        platforms: List[str],
        title: str,
        tags: Optional[List[str]] = None,
        description: str = "",
        enable_anti_duplicate: bool = True,
        cover_path: Optional[str | Path] = None,
        schedule_time: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        统一并发调度多平台发布任务
        """
        v_path = Path(video_path).resolve()
        if not v_path.is_file():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        tags = tags or ["#深度思考", "#爆款短视频", "#商业认知", "#干货分享"]
        batch_pub_id = f"matrix_{uuid.uuid4().hex[:8]}"

        # 1. 执行抗查重微混淆处理（若开启）
        target_video_path = v_path
        anti_dup_meta: Optional[Dict[str, Any]] = None
        if enable_anti_duplicate:
            try:
                anti_dup_meta = anti_duplicate_processor.process_video(v_path)
                target_video_path = Path(anti_dup_meta["processed_path"])
                logger.info("抗查重处理完成，MD5 由 %s 变为 %s", anti_dup_meta["original_md5"], anti_dup_meta["processed_md5"])
            except Exception as e:
                logger.warning("抗查重处理失败，降级使用原视频: %s", e)

        # 2. 并发向各个平台发布
        tasks = []
        valid_platforms = []
        for pid in platforms:
            pub = self._publishers.get(pid.lower())
            if pub:
                valid_platforms.append(pid)
                tasks.append(
                    pub.publish(
                        video_path=target_video_path,
                        title=title,
                        tags=tags,
                        description=description,
                        cover_path=cover_path,
                        schedule_time=schedule_time,
                        **kwargs,
                    )
                )
            else:
                logger.warning("未知或未注册的平台: %s", pid)

        results: List[PublishResult] = await asyncio.gather(*tasks, return_exceptions=False)

        # 3. 组织结果并归档
        record = {
            "batch_id": batch_pub_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "tags": tags,
            "original_video": str(v_path),
            "final_video": str(target_video_path),
            "anti_duplicate_enabled": enable_anti_duplicate,
            "anti_duplicate_meta": anti_dup_meta,
            "platforms_count": len(results),
            "results": [r.model_dump() for r in results],
        }

        self._append_history(record)
        return record


publish_manager = PublishManager()
