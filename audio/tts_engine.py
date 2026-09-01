"""
TTS 语音合成与时间戳对齐引擎
基于 Edge-TTS 异步流式生成，支持词级/句级时间戳与精确时长测量
"""
import os
import asyncio
import edge_tts
from pathlib import Path
from typing import Dict, List, Any, Optional
from config.settings import AUDIO_OUTPUT_DIR, DEFAULT_TTS_PITCH, DEFAULT_TTS_RATE, DEFAULT_TTS_VOICE, DEFAULT_TTS_VOLUME

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
        communicate = edge_tts.Communicate(
            text=text,
            voice=target_voice,
            rate=target_rate,
            volume=self.volume
            , pitch=self.pitch
        )
        
        word_timestamps: List[Dict[str, Any]] = []
        audio_chunks = bytearray()
        
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
        results = []
        for idx, scene in enumerate(scenes):
            voiceover = scene.get("voiceover_text", "")
            if not voiceover:
                continue
            filename = f"{project_id}_scene_{idx+1}.mp3"
            res = await self.generate_speech_with_timestamps(
                text=voiceover,
                output_filename=filename
            )
            # 丰富分镜数据
            scene_res = dict(scene)
            scene_res["audio_file"] = res["audio_path"]
            scene_res["duration"] = res["duration"]
            scene_res["word_timestamps"] = res["word_timestamps"]
            results.append(scene_res)
            
        return results

def synthesize_scene_speech_sync(scenes: List[Dict[str, Any]], project_id: str, voice: str = DEFAULT_TTS_VOICE) -> List[Dict[str, Any]]:
    engine = TTSEngine(voice=voice)
    return asyncio.run(engine.generate_scenes_speech(scenes, project_id))
