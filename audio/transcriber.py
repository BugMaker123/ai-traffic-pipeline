"""
语音转写模块 (Audio Speech-To-Text Transcriber)
支持将提取的视频口播音频转为带标点的文本台词。
优先尝试 OpenAI/第三方 Whisper API，本地环境无 GPU 或无 API 时优雅降级。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import requests
from config.settings import OPENAI_API_KEY, OPENAI_BASE_URL

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """语音转写服务"""

    @classmethod
    def transcribe(cls, audio_path: str | Path, prompt: str = "") -> str:
        """
        转写音频文件为文本。
        """
        path = Path(audio_path)
        if not path.is_file():
            logger.warning("音频文件不存在: %s", audio_path)
            return ""

        # 1. 尝试 OpenAI / 兼容 Whisper API
        if OPENAI_API_KEY:
            try:
                base_url = OPENAI_BASE_URL.rstrip("/")
                # 如果是 deepseek 官方 API，通常不提供 whisper 转写，检查是否为 openai/兼容接口
                whisper_endpoint = f"{base_url}/audio/transcriptions"
                if "deepseek" not in base_url.lower():
                    logger.info("尝试调用 Whisper API 进行语音转写...")
                    with open(path, "rb") as f:
                        resp = requests.post(
                            whisper_endpoint,
                            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                            files={"file": (path.name, f, "audio/mpeg")},
                            data={"model": "whisper-1", "language": "zh", "prompt": prompt},
                            timeout=60,
                        )
                    if resp.status_code == 200:
                        text = resp.json().get("text", "").strip()
                        if text:
                            logger.info("Whisper API 转写成功 (字数: %d)", len(text))
                            return text
            except Exception as e:
                logger.debug("Whisper API 调用跳过或失败: %s", e)

        # 2. 尝试本地 faster-whisper / whisper
        try:
            from faster_whisper import WhisperModel
            logger.info("正在调用本地 faster-whisper 模型进行离线转写...")
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(path), language="zh")
            full_text = "".join(seg.text for seg in segments).strip()
            if full_text:
                return full_text
        except ImportError:
            pass
        except Exception as e:
            logger.warning("本地 faster-whisper 转写失败: %s", e)

        # 3. 若无转写模型，返回提示
        logger.info("未配置在线 Whisper API 且未安装 faster-whisper，转写降级完成")
        return ""
