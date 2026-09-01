import sys
import os
from pathlib import Path

# 设置 UTF-8 输出
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 添加工程根目录到 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import asyncio
import pytest
from audio.tts_engine import TTSEngine
from audio.srt_aligner import SubtitleAligner
from config.settings import AUDIO_OUTPUT_DIR

@pytest.mark.integration
def test_tts_and_subtitles():
    engine = TTSEngine()
    test_text = "很多人以为自律靠硬撑，其实用对微习惯，坚持比放弃还容易！"
    
    print("▶ 测试 1: 生成 TTS 音频与时间戳...")
    res = asyncio.run(engine.generate_speech_with_timestamps(
        text=test_text,
        output_filename="test_tts.mp3"
    ))
    
    audio_path = Path(res["audio_path"])
    print(f"音频文件已生成: {audio_path.exists()} ({audio_path})")
    print(f"音频时长: {res['duration']}s, 提取词时间戳数量: {len(res['word_timestamps'])}")
    assert audio_path.exists(), "音频文件生成失败"
    assert res["duration"] > 0, "音频时长应大于0"
    
    print("\n▶ 测试 2: 生成字幕分块与 SRT 文件...")
    scene_mock = {
        "voiceover_text": test_text,
        "word_timestamps": res["word_timestamps"],
        "duration": res["duration"]
    }
    chunks = SubtitleAligner.chunk_scene_subtitles(scene_mock, start_offset=0.0)
    print(f"切分字幕条数: {len(chunks)}")
    for c in chunks:
        print(f"  [{c['start']}s -> {c['end']}s] {c['text']}")
        
    srt_file = AUDIO_OUTPUT_DIR / "test_subtitles.srt"
    SubtitleAligner.export_srt(chunks, srt_file)
    print(f"SRT 文件已生成: {srt_file.exists()}")
    assert srt_file.exists(), "SRT 字幕生成失败"
    print("\n✅ TTS 与字幕测试全部通过！")

if __name__ == "__main__":
    test_tts_and_subtitles()
