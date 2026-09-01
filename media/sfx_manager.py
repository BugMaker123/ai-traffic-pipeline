"""
短视频黄金音效引擎 (SFX Engine)
包含：Whoosh (转场破风/呼啸)、Ding (重点强调/金句)、Pop (气泡弹跳/标题弹出)、Hit (重音顿挫)
若无外部音频文件，自动通过高采样率正弦调频与白噪声包络程序化合成高质感音效
"""
import math
import struct
import wave
from pathlib import Path
from typing import Optional, Dict
from config.settings import STATIC_DIR

SFX_DIR = STATIC_DIR / "sfx"
SFX_DIR.mkdir(parents=True, exist_ok=True)

class SFXManager:
    """音效管理与程序化合成器"""

    @classmethod
    def get_sfx(cls, effect_name: str = "whoosh") -> str:
        """
        获取指定音效文件路径，若不存在则即时合成
        :param effect_name: 'whoosh' | 'ding' | 'pop' | 'hit'
        """
        target_path = SFX_DIR / f"{effect_name}.wav"
        if not target_path.exists():
            cls._synthesize_sfx(effect_name, target_path)
        return str(target_path)

    @classmethod
    def get_whoosh(cls) -> str:
        return cls.get_sfx("whoosh")

    @classmethod
    def get_ding(cls) -> str:
        return cls.get_sfx("ding")

    @classmethod
    def get_pop(cls) -> str:
        return cls.get_sfx("pop")

    @classmethod
    def get_hit(cls) -> str:
        return cls.get_sfx("hit")

    @classmethod
    def _synthesize_sfx(cls, effect_type: str, output_path: Path, sample_rate: int = 44100):
        """高质量程序化音效合成算法"""
        if effect_type == "whoosh":
            duration = 0.45
            num_samples = int(duration * sample_rate)
            raw_data = bytearray()
            import random
            # 带通滤波白噪声模拟气流快速划过
            for i in range(num_samples):
                t = i / sample_rate
                # 振幅包络 (Bell curve)
                env = math.sin(math.pi * (t / duration)) ** 2
                # 动态频率扫描 (200Hz -> 1800Hz -> 300Hz)
                freq = 200 + 1600 * math.sin(math.pi * (t / duration))
                noise = random.uniform(-0.6, 0.6)
                tone = math.sin(2 * math.pi * freq * t) * 0.4
                val = (noise * 0.6 + tone * 0.4) * env * 0.7
                sample_int = int(max(-1.0, min(1.0, val)) * 32767)
                raw_data.extend(struct.pack("<h", sample_int))

        elif effect_type == "ding":
            duration = 0.8
            num_samples = int(duration * sample_rate)
            raw_data = bytearray()
            # 晶莹的高音和弦 (1318.5Hz E6 + 2637Hz E7) + 指数级平滑衰减
            for i in range(num_samples):
                t = i / sample_rate
                env = math.exp(-t * 4.5)
                val = (math.sin(2 * math.pi * 1318.51 * t) * 0.6 +
                       math.sin(2 * math.pi * 2637.02 * t) * 0.3 +
                       math.sin(2 * math.pi * 3951.07 * t) * 0.1) * env * 0.65
                sample_int = int(max(-1.0, min(1.0, val)) * 32767)
                raw_data.extend(struct.pack("<h", sample_int))

        elif effect_type == "pop":
            duration = 0.18
            num_samples = int(duration * sample_rate)
            raw_data = bytearray()
            # 极速上行扫频气泡音 (300Hz -> 950Hz)
            for i in range(num_samples):
                t = i / sample_rate
                env = (1 - (t / duration)) ** 1.5
                freq = 300 + (650 * (t / duration))
                val = math.sin(2 * math.pi * freq * t) * env * 0.8
                sample_int = int(max(-1.0, min(1.0, val)) * 32767)
                raw_data.extend(struct.pack("<h", sample_int))

        else:  # hit / thud
            duration = 0.35
            num_samples = int(duration * sample_rate)
            raw_data = bytearray()
            # 低沉重低音顿挫 (120Hz -> 45Hz)
            for i in range(num_samples):
                t = i / sample_rate
                env = math.exp(-t * 9.0)
                freq = 120 - 75 * (t / duration)
                val = math.sin(2 * math.pi * freq * t) * env * 0.85
                sample_int = int(max(-1.0, min(1.0, val)) * 32767)
                raw_data.extend(struct.pack("<h", sample_int))

        with wave.open(str(output_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(raw_data)
