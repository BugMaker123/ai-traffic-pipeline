"""
视频链接解析与音频提取模块 (Video URL Ingestion & Audio Extractor)
支持抖音、B站、小红书、YouTube 及通用音视频链接的元数据提取与音轨分离。
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yt_dlp

from config.settings import AUDIO_OUTPUT_DIR

logger = logging.getLogger(__name__)


class VideoExtractor:
    """提取网络视频的标题、文案简介及伴奏/口播音轨"""

    @staticmethod
    def is_valid_url(url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        url_regex = re.compile(
            r"^(?:http|ftp)s?://"  # http:// or https://
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
            r"localhost|"  # localhost...
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
            r"(?::\d+)?"  # optional port
            r"(?:/?|[/?]\S+)$",
            re.IGNORECASE,
        )
        return re.match(url_regex, url.strip()) is not None

    @classmethod
    def extract_clean_url(cls, raw_text: str) -> str:
        """从用户粘贴的分享文案中提取纯 URL (例如小红书/抖音分享文案通常夹带文字)"""
        match = re.search(r"https?://[^\s\u4e00-\u9fa5]+", raw_text)
        if match:
            return match.group(0).strip()
        return raw_text.strip()

    @classmethod
    def extract_video_info_and_audio(
        cls,
        raw_url_or_text: str,
        output_dir: Optional[Path] = None,
        extract_audio: bool = True
    ) -> Dict[str, Any]:
        """
        解析视频链接并下载音频
        返回: {
            "title": str,
            "description": str,
            "duration": float,
            "author": str,
            "thumbnail": str,
            "platform": str,
            "audio_path": Optional[str],
            "raw_url": str
        }
        """
        target_url = cls.extract_clean_url(raw_url_or_text)
        if not cls.is_valid_url(target_url):
            raise ValueError(f"无效的视频链接: {raw_url_or_text}")

        output_dir = output_dir or AUDIO_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        file_prefix = f"extract_{uuid.uuid4().hex[:8]}"
        out_template = str(output_dir / f"{file_prefix}.%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "socket_timeout": 15,
        }

        if extract_audio:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("正在解析视频元数据: %s", target_url)
                info = ydl.extract_info(target_url, download=extract_audio)
                
                title = info.get("title", "未命名视频")
                description = info.get("description") or info.get("title", "")
                duration = float(info.get("duration") or 0.0)
                author = info.get("uploader") or info.get("channel", "未知作者")
                thumbnail = info.get("thumbnail", "")
                extractor_key = info.get("extractor_key", "generic")

                audio_file_path: Optional[str] = None
                if extract_audio:
                    mp3_path = output_dir / f"{file_prefix}.mp3"
                    if mp3_path.exists():
                        audio_file_path = str(mp3_path)
                    else:
                        # 检查可能的其他扩展名
                        for ext in ["m4a", "wav", "webm", "mp4"]:
                            alt_path = output_dir / f"{file_prefix}.{ext}"
                            if alt_path.exists():
                                audio_file_path = str(alt_path)
                                break

                return {
                    "title": title,
                    "description": description,
                    "duration": duration,
                    "author": author,
                    "thumbnail": thumbnail,
                    "platform": extractor_key,
                    "audio_path": audio_file_path,
                    "raw_url": target_url,
                }
        except Exception as e:
            logger.warning("yt-dlp 解析失败: %s，尝试降级为社媒通用元数据提取", e)
            try:
                from extractors.video_extractor import SocialVideoExtractor
                extracted = SocialVideoExtractor.extract(raw_url_or_text)
                return {
                    "title": extracted["title"],
                    "description": extracted["transcript"],
                    "duration": 0.0,
                    "author": "社媒博主",
                    "thumbnail": "",
                    "platform": extracted["platform"],
                    "audio_path": None,
                    "raw_url": target_url,
                }
            except Exception as fallback_err:
                raise RuntimeError(f"解析视频链接失败: {e}; 备用请求失败: {fallback_err}") from e
