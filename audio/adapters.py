"""
TTS 语音合成适配器体系 (TTS Adapter System)
定义统合的 TTS 协议与不同引擎实现：
1. BaseTTSAdapter: 统一抽象基类
2. EdgeTTSAdapter: 高拟真微软 Edge-TTS 引擎，支持字级时间戳
3. CosyVoiceAdapter: 本地/远程 CosyVoice 声音克隆适配器，支持 3~5 秒参考音频快速克隆与离线自动平滑降级
"""
import os
import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional

import edge_tts
import requests

from config.settings import (
    DEFAULT_TTS_PITCH,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOICE,
    DEFAULT_TTS_VOLUME,
)

logger = logging.getLogger(__name__)

TTS_RETRY_ATTEMPTS = max(1, int(os.getenv("TTS_RETRY_ATTEMPTS", "3")))
TTS_RETRY_DELAY_SECONDS = max(0.1, float(os.getenv("TTS_RETRY_DELAY_SECONDS", "2")))
TTS_FALLBACK_SILENCE = os.getenv("TTS_FALLBACK_SILENCE", "1").lower() not in {"0", "false", "no", "off"}
COSYVOICE_API_URL = os.getenv("COSYVOICE_API_URL", "http://127.0.0.1:50000/api/tts")
COSYVOICE_TIMEOUT = float(os.getenv("COSYVOICE_TIMEOUT", "4.0"))


def get_audio_file_duration(audio_file_path: str) -> float:
    """测量音频文件实际时长"""
    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(audio_file_path)
        d = float(clip.duration)
        clip.close()
        return d
    except Exception:
        pass
    try:
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(audio_file_path)
        d = float(clip.duration)
        clip.close()
        return d
    except Exception:
        pass
    return 0.0


def estimate_voiceover_duration(text: str) -> float:
    """按中文语速估算时长（约 4.5 字/秒）"""
    clean_text = "".join(text.split())
    return round(max(1.5, len(clean_text) / 4.5), 2)


def estimate_word_timestamps(text: str, duration: float) -> List[Dict[str, Any]]:
    """生成均分的时间戳序列"""
    clean_chars = [ch for ch in text if not ch.isspace()]
    if not clean_chars:
        return []

    step = duration / len(clean_chars)
    timestamps = []
    for idx, ch in enumerate(clean_chars):
        start = idx * step
        end = (idx + 1) * step
        timestamps.append({
            "text": ch,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(step, 3),
        })
    return timestamps


def write_silent_mp3(audio_path: Path, duration: float) -> None:
    """生成静音 MP3 兜底文件"""
    import subprocess
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("未找到可用的 FFmpeg，无法生成静音 TTS 兜底音频") from exc

    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        f"{duration:.3f}",
        "-q:a",
        "9",
        "-acodec",
        "libmp3lame",
        str(audio_path),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


class BaseTTSAdapter(ABC):
    """TTS 适配器抽象基类"""

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        volume: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        生成单段语音，返回元数据字典：
        {
            "audio_path": str,
            "duration": float,
            "word_timestamps": list[dict],
            "text": str,
            "voice": str,
            "tts_engine": str,
            ...
        }
        """
        raise NotImplementedError


class EdgeTTSAdapter(BaseTTSAdapter):
    """Edge-TTS 异步流式语音合成适配器"""

    def __init__(
        self,
        default_voice: str = DEFAULT_TTS_VOICE,
        default_rate: str = DEFAULT_TTS_RATE,
        default_pitch: str = DEFAULT_TTS_PITCH,
        default_volume: str = DEFAULT_TTS_VOLUME,
    ):
        self.default_voice = default_voice
        self.default_rate = default_rate
        self.default_pitch = default_pitch
        self.default_volume = default_volume

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        volume: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target_voice = voice or self.default_voice
        target_rate = rate or self.default_rate
        target_pitch = pitch or self.default_pitch
        target_volume = volume or self.default_volume

        word_timestamps: List[Dict[str, Any]] = []
        audio_chunks = bytearray()
        last_error: Optional[BaseException] = None

        for attempt in range(1, TTS_RETRY_ATTEMPTS + 1):
            word_timestamps = []
            audio_chunks = bytearray()
            communicate = edge_tts.Communicate(
                text=text,
                voice=target_voice,
                rate=target_rate,
                volume=target_volume,
                pitch=target_pitch,
            )

            try:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.extend(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        offset_sec = chunk["offset"] / 10_000_000
                        duration_sec = chunk["duration"] / 10_000_000
                        word_timestamps.append({
                            "text": chunk.get("text", ""),
                            "start": round(offset_sec, 3),
                            "end": round(offset_sec + duration_sec, 3),
                            "duration": round(duration_sec, 3),
                        })
                if audio_chunks:
                    break
                last_error = RuntimeError("Edge-TTS 未返回音频数据")
            except Exception as exc:
                last_error = exc

            if attempt < TTS_RETRY_ATTEMPTS:
                await asyncio.sleep(TTS_RETRY_DELAY_SECONDS * attempt)

        if not audio_chunks:
            if not TTS_FALLBACK_SILENCE:
                raise RuntimeError(f"Edge-TTS 合成失败，且未启用静音兜底: {last_error}") from last_error

            total_duration = estimate_voiceover_duration(text)
            write_silent_mp3(output_path, total_duration)
            return {
                "audio_path": str(output_path),
                "duration": total_duration,
                "word_timestamps": estimate_word_timestamps(text, total_duration),
                "text": text,
                "voice": target_voice,
                "rate": target_rate,
                "pitch": target_pitch,
                "tts_engine": "edge_tts",
                "tts_fallback": "silent",
                "tts_error": str(last_error) if last_error else "Edge-TTS 未返回音频数据",
            }

        with open(output_path, "wb") as f:
            f.write(audio_chunks)

        total_duration = get_audio_file_duration(str(output_path))
        if total_duration <= 0.0 and word_timestamps:
            total_duration = word_timestamps[-1]["end"]
        if total_duration <= 0.0:
            total_duration = estimate_voiceover_duration(text)

        return {
            "audio_path": str(output_path),
            "duration": round(total_duration, 2),
            "word_timestamps": word_timestamps,
            "text": text,
            "voice": target_voice,
            "rate": target_rate,
            "pitch": target_pitch,
            "tts_engine": "edge_tts",
        }


class CosyVoiceAdapter(BaseTTSAdapter):
    """
    CosyVoice 声音克隆适配器
    支持传入参考音频 (prompt_wav) 和参考文本 (prompt_text) 实现零样本快速声音克隆。
    当 CosyVoice 远程/本地服务不在线时，自动平滑降级至 Edge-TTS 备用音色。
    """

    def __init__(
        self,
        api_url: str = COSYVOICE_API_URL,
        fallback_adapter: Optional[BaseTTSAdapter] = None,
        timeout: float = COSYVOICE_TIMEOUT,
        reference_audio: Optional[str] = None,
        reference_text: Optional[str] = None,
        fallback_voice: str = DEFAULT_TTS_VOICE,
    ):
        self.api_url = api_url
        self.fallback_adapter = fallback_adapter or EdgeTTSAdapter()
        self.timeout = timeout
        self.reference_audio = reference_audio
        self.reference_text = reference_text
        self.fallback_voice = fallback_voice

    def _call_cosyvoice_sync(
        self,
        text: str,
        output_path: Path,
        voice: str,
        prompt_wav: Optional[str],
        prompt_text: Optional[str],
    ) -> bytes:
        payload = {
            "text": text,
            "speaker": voice,
            "prompt_text": prompt_text or "",
        }
        files = None
        if prompt_wav and os.path.isfile(prompt_wav):
            files = {"prompt_wav": open(prompt_wav, "rb")}

        resp = requests.post(
            self.api_url,
            data=payload,
            files=files,
            timeout=self.timeout,
        )
        if files:
            for f in files.values():
                f.close()

        resp.raise_for_status()
        return resp.content

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        pitch: Optional[str] = None,
        volume: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target_voice = voice or "cosyvoice_default"
        prompt_wav = kwargs.get("prompt_wav") or self.reference_audio
        prompt_text = kwargs.get("prompt_text") or self.reference_text

        # 尝试调用 CosyVoice
        try:
            audio_bytes = await asyncio.to_thread(
                self._call_cosyvoice_sync,
                text=text,
                output_path=output_path,
                voice=target_voice,
                prompt_wav=prompt_wav,
                prompt_text=prompt_text,
            )
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            duration = get_audio_file_duration(str(output_path))
            if duration <= 0:
                duration = estimate_voiceover_duration(text)

            return {
                "audio_path": str(output_path),
                "duration": round(duration, 2),
                "word_timestamps": estimate_word_timestamps(text, duration),
                "text": text,
                "voice": target_voice,
                "rate": rate or DEFAULT_TTS_RATE,
                "pitch": pitch or DEFAULT_TTS_PITCH,
                "tts_engine": "cosyvoice",
            }
        except Exception as exc:
            logger.warning(
                "CosyVoice 服务不可用或超时 (%s)，自动触发平滑降级至 Edge-TTS (%s)...",
                exc,
                self.fallback_voice,
            )
            res = await self.fallback_adapter.synthesize(
                text=text,
                output_path=output_path,
                voice=self.fallback_voice,
                rate=rate,
                pitch=pitch,
                volume=volume,
            )
            res["tts_fallback"] = "cosyvoice_to_edge"
            res["original_voice"] = target_voice
            res["tts_error"] = str(exc)
            return res
