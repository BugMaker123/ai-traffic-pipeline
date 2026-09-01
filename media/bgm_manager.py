"""
背景音乐 (BGM) 管理与音量平衡引擎
"""
import os
import wave
import math
import struct
from pathlib import Path
from typing import Optional
from config.settings import BGM_DIR

class BGMManager:
    """背景音乐管理与智能配乐"""
    
    @staticmethod
    def get_bgm(mood: str = "energetic", bgm_type: Optional[str] = None, custom_bgm_path: Optional[str] = None) -> Optional[str]:
        """
        获取指定情绪类型的背景音乐
        :param mood: energetic / suspense / emotional / chill / tech
        :param bgm_type: 别名兼容 mood
        :param custom_bgm_path: 用户自定义音频路径
        """
        mood_key = bgm_type or mood or "energetic"
        if custom_bgm_path and Path(custom_bgm_path).exists():
            return str(custom_bgm_path)
            
        # 扫描 static/bgm 目录
        matched_files = list(BGM_DIR.glob(f"*{mood_key}*")) or list(BGM_DIR.glob("*.mp3")) or list(BGM_DIR.glob("*.wav"))
        if matched_files:
            return str(matched_files[0])
            
        # 若没有任何外部 BGM 文件，生成一段柔和且极具氛围感的低频合成 Lo-Fi 律动背景音 (WAV)
        fallback_bgm = BGM_DIR / f"ambient_{mood}.wav"
        if not fallback_bgm.exists():
            BGMManager._create_synthetic_ambient_bgm(fallback_bgm, duration=60.0)
            
        return str(fallback_bgm) if fallback_bgm.exists() else None

    @staticmethod
    def _create_synthetic_ambient_bgm(output_path: Path, duration: float = 60.0, sample_rate: int = 44100):
        """生成一段极简轻快的现代 Lo-Fi 环境音作为无 BGM 时的伴奏"""
        num_samples = int(duration * sample_rate)
        # 和弦基频序列 (Am7 - F - C - G)
        chords = [220.0, 174.61, 261.63, 196.0]
        
        with wave.open(str(output_path), "w") as wav_file:
            wav_file.setnchannels(1)  # 单声道
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            
            raw_data = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                chord_idx = int(t / 4.0) % len(chords)
                freq = chords[chord_idx]
                
                # 叠加柔和正弦波与泛音
                val1 = math.sin(2 * math.pi * freq * t) * 0.15
                val2 = math.sin(2 * math.pi * (freq * 1.5) * t) * 0.08
                val3 = math.sin(2 * math.pi * (freq * 0.5) * t) * 0.20  # 低音根音
                
                # 脉冲节拍 (每秒 2 拍)
                beat = (math.sin(2 * math.pi * 2.0 * t) ** 4) * 0.05
                
                combined = (val1 + val2 + val3 + beat) * 0.35
                clamped = max(-1.0, min(1.0, combined))
                sample_int = int(clamped * 32767)
                raw_data.extend(struct.pack("<h", sample_int))
                
            wav_file.writeframes(raw_data)
