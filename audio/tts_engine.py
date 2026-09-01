"""
TTS 语音合成与时间戳对齐引擎
基于 Edge-TTS 异步流式生成，支持词级/句级时间戳与精确时长测量
"""
import os
import asyncio
import subprocess
import edge_tts
from pathlib import Path
from typing import Dict, List, Any, Optional
from config.settings import AUDIO_OUTPUT_DIR, DEFAULT_TTS_PITCH, DEFAULT_TTS_RATE, DEFAULT_TTS_VOICE, DEFAULT_TTS_VOLUME, TTS_CONCURRENCY

TTS_RETRY_ATTEMPTS = max(1, int(os.getenv("TTS_RETRY_ATTEMPTS", "3")))
TTS_RETRY_DELAY_SECONDS = max(0.1, float(os.getenv("TTS_RETRY_DELAY_SECONDS", "2")))
TTS_FALLBACK_SILENCE = os.getenv("TTS_FALLBACK_SILENCE", "1").lower() not in {"0", "false", "no", "off"}


# 尝试用 AudioFileClip 精确测量音频文件时长
def get_audio_file_duration(audio_file_path: str) -> float:
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
    """中文旁白按自然语速估算时长，用于 TTS 服务不可达时继续产出字幕时间轴。"""
    clean_text = "".join(text.split())
    return round(max(1.5, len(clean_text) / 4.5), 2)


def estimate_word_timestamps(text: str, duration: float) -> List[Dict[str, Any]]:
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
    """生成可被 MoviePy/FFmpeg 读取的静音 MP3 占位音轨。"""
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

class TTSEngine:
    def __init__(
        self,
        voice: str = DEFAULT_TTS_VOICE,
        rate: str = DEFAULT_TTS_RATE,
        volume: str = DEFAULT_TTS_VOLUME,
        pitch: str = DEFAULT_TTS_PITCH,
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch

    async def generate_speech_with_timestamps(
        self,
        text: str,
        output_filename: str,
        voice: Optional[str] = None,
        rate: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成语音音频并提取毫秒级时间戳
        :param text: 待朗读文本
        :param output_filename: 音频输出文件名（如 scene_1.mp3）
        :param voice: 可选覆盖默认音色
        :param rate: 可选覆盖默认语速
        :return: 字典包含 audio_path, duration, word_timestamps
        """
        target_voice = voice or self.voice
        target_rate = rate or self.rate
        
        audio_path = AUDIO_OUTPUT_DIR / output_filename
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
                volume=self.volume,
                pitch=self.pitch,
            )

            try:
                # 流式获取音频字节流与元数据事件
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.extend(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        # offset 和 duration 单位为 100ns (10^-7 秒), 转换为秒
                        offset_sec = chunk["offset"] / 10_000_000
                        duration_sec = chunk["duration"] / 10_000_000
                        word_timestamps.append({
                            "text": chunk.get("text", ""),
                            "start": round(offset_sec, 3),
                            "end": round(offset_sec + duration_sec, 3),
                            "duration": round(duration_sec, 3)
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
            write_silent_mp3(audio_path, total_duration)
            return {
                "audio_path": str(audio_path),
                "duration": total_duration,
                "word_timestamps": estimate_word_timestamps(text, total_duration),
                "text": text,
                "voice": target_voice,
                "rate": target_rate,
                "pitch": self.pitch,
                "tts_fallback": "silent",
                "tts_error": str(last_error) if last_error else "Edge-TTS 未返回音频数据",
            }

        # 写入音频文件
        with open(audio_path, "wb") as f:
            f.write(audio_chunks)
            
        # 精确测量真实音频总时长
        total_duration = get_audio_file_duration(str(audio_path))
        if total_duration <= 0.0 and word_timestamps:
            total_duration = word_timestamps[-1]["end"]
        if total_duration <= 0.0:
            # 兜底均速估算 (中文每秒 4.5 字)
            total_duration = max(1.5, len(text) / 4.5)
            
        return {
            "audio_path": str(audio_path),
            "duration": round(total_duration, 2),
            "word_timestamps": word_timestamps,
            "text": text,
            "voice": target_voice
            , "rate": target_rate
            , "pitch": self.pitch
        }

    async def generate_scenes_speech(
        self,
        scenes: List[Dict[str, Any]],
        project_id: str
    ) -> List[Dict[str, Any]]:
        """
        批量为每个分镜生成独立的语音文件与精确时间戳
        """
        semaphore = asyncio.Semaphore(TTS_CONCURRENCY)

        async def synthesize(idx: int, scene: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            voiceover = scene.get("voiceover_text", "")
            if not voiceover:
                return None
            filename = f"{project_id}_scene_{idx+1}.mp3"
            async with semaphore:
                res = await self.generate_speech_with_timestamps(text=voiceover, output_filename=filename)
            # 丰富分镜数据
            scene_res = dict(scene)
            scene_res["audio_file"] = res["audio_path"]
            scene_res["duration"] = res["duration"]
            scene_res["word_timestamps"] = res["word_timestamps"]
            if res.get("tts_fallback"):
                scene_res["tts_fallback"] = res["tts_fallback"]
                scene_res["tts_error"] = res.get("tts_error", "")
            return scene_res

        generated = await asyncio.gather(*(synthesize(idx, scene) for idx, scene in enumerate(scenes)))
        return [scene for scene in generated if scene is not None]

def synthesize_scene_speech_sync(scenes: List[Dict[str, Any]], project_id: str, voice: str = DEFAULT_TTS_VOICE) -> List[Dict[str, Any]]:
    engine = TTSEngine(voice=voice)
    return asyncio.run(engine.generate_scenes_speech(scenes, project_id))
