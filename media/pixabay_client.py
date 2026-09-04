"""
Pixabay 免版权超清实拍视频与竖屏摄影引擎
特性：
1. 支持 Pixabay 官方 API 检索真实 4K/1080P 实拍短视频 (film/animation)
2. 支持检索 1080x1920 高清摄影直连原片 (orientation=vertical, image_type=photo)
3. 免版权商用 (Pixabay License / CC0)，有效消除 AI 画面假感
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from config.settings import ASSETS_OUTPUT_DIR, PIXABAY_API_KEY

logger = logging.getLogger(__name__)


class PixabayMediaClient:
    """Pixabay 商业免版权实拍视频与摄影客户端"""

    VIDEO_API_URL = "https://pixabay.com/api/videos/"
    PHOTO_API_URL = "https://pixabay.com/api/"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key if api_key is not None else PIXABAY_API_KEY
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

    @property
    def is_configured(self) -> bool:
        """是否已配置有效 API Key"""
        return bool(self.api_key and self.api_key.strip())

    def search_video(
        self,
        query: str,
        scene_idx: int,
        project_id: str,
        timeout: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """
        检索真实实拍 MP4 视频片段。
        优先寻找竖屏或 1080P/720P 镜头，自动下载至本地。
        """
        if not self.is_configured:
            return None

        clean_query = query.strip()
        if not clean_query:
            return None

        params = {
            "key": self.api_key,
            "q": clean_query,
            "video_type": "film",
            "per_page": 5,
            "safesearch": "true",
        }

        try:
            logger.info("正在检索 Pixabay 实拍视频: [%s]", clean_query)
            resp = self.session.get(self.VIDEO_API_URL, params=params, timeout=timeout)
            if resp.status_code != 200:
                logger.warning("Pixabay 视频 API 响应异常: %d - %s", resp.status_code, resp.text[:120])
                return None

            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                logger.info("Pixabay 视频未检索到相关内容: [%s]", clean_query)
                return None

            # 优先挑一个结果（根据分镜索引选择，避免连续相同）
            chosen = hits[(scene_idx - 1) % len(hits)]
            videos_dict = chosen.get("videos", {})

            # 优先顺序: large (1080P) -> medium (720P) -> small
            selected_file = (
                videos_dict.get("large")
                or videos_dict.get("medium")
                or videos_dict.get("small")
                or videos_dict.get("tiny")
            )

            if not selected_file or not selected_file.get("url"):
                return None

            video_url = selected_file["url"]
            save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.mp4"

            # 下载真实视频数据
            logger.info("正在下载 Pixabay 实拍视频片段 (分镜 #%d)...", scene_idx)
            dl_resp = self.session.get(video_url, timeout=30)
            if dl_resp.status_code == 200 and len(dl_resp.content) > 100_000:
                with open(save_path, "wb") as f:
                    f.write(dl_resp.content)
                logger.info("Pixabay 视频下载成功: %s", save_path)
                return {
                    "asset_file": str(save_path),
                    "asset_type": "video",
                    "source": "pixabay_video",
                    "keyword": clean_query,
                    "duration": chosen.get("duration", 5.0),
                }

        except Exception as e:
            logger.warning("Pixabay 视频检索/下载异常 (%s): %s", clean_query, e)

        return None

    def search_photo(
        self,
        query: str,
        scene_idx: int,
        project_id: str,
        timeout: int = 8,
    ) -> Optional[Dict[str, Any]]:
        """
        检索真实超清竖屏摄影大片 (orientation=vertical, image_type=photo)
        """
        if not self.is_configured:
            return None

        clean_query = query.strip()
        if not clean_query:
            return None

        params = {
            "key": self.api_key,
            "q": clean_query,
            "image_type": "photo",
            "orientation": "vertical",
            "per_page": 5,
            "safesearch": "true",
        }

        try:
            logger.info("正在检索 Pixabay 超清竖屏摄影: [%s]", clean_query)
            resp = self.session.get(self.PHOTO_API_URL, params=params, timeout=timeout)
            if resp.status_code != 200:
                return None

            hits = resp.json().get("hits", [])
            if not hits:
                return None

            chosen = hits[(scene_idx - 1) % len(hits)]
            photo_url = (
                chosen.get("largeImageURL")
                or chosen.get("webformatURL")
                or chosen.get("imageURL")
            )

            if not photo_url:
                return None

            save_path = ASSETS_OUTPUT_DIR / f"{project_id}_asset_scene_{scene_idx}.jpg"
            dl_resp = self.session.get(photo_url, timeout=20)
            if dl_resp.status_code == 200 and len(dl_resp.content) > 15_000:
                with open(save_path, "wb") as f:
                    f.write(dl_resp.content)
                logger.info("Pixabay 真实摄影原片下载成功: %s", save_path)
                return {
                    "asset_file": str(save_path),
                    "asset_type": "image",
                    "source": "pixabay_photo",
                    "keyword": clean_query,
                    "photographer": chosen.get("user", "Pixabay"),
                }

        except Exception as e:
            logger.warning("Pixabay 摄影大片检索异常: %s", e)

        return None
