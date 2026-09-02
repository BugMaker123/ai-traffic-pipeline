"""
P1 与 P2 新增核心功能单元测试
测试项目：
1. 视频链接提取 (VideoExtractor)
2. 音频转写降级 (AudioTranscriber)
3. 爆款仿写生成 (ScriptGenerator.generate_script_from_reference)
4. 词级高亮时间戳字幕 (SubtitleAligner)
5. AI生图增强与兜底 (AIImageGenerator)
6. 逐字卡拉OK字幕与多排版合成 (MoviePyRenderer)
7. 多轨道剪映工程生成 (JianYingDraftGenerator)
"""
import os
import json
import pytest
from pathlib import Path
from crawlers.video_extractor import VideoExtractor
from audio.transcriber import AudioTranscriber
from audio.srt_aligner import SubtitleAligner
from writers.script_generator import ScriptGenerator
from media.ai_image_gen import AIImageGenerator
from compositors.moviepy_renderer import MoviePyRenderer
from compositors.jianying_draft import JianYingDraftGenerator


def test_video_extractor_url_validation():
    assert VideoExtractor.is_valid_url("https://www.bilibili.com/video/BV1xx411c7mD")
    assert VideoExtractor.is_valid_url("http://v.douyin.com/abc1234/")
    assert not VideoExtractor.is_valid_url("not a url string")
    
    raw = "7.89 复制打开抖音，看看【程序员的小日子】 https://v.douyin.com/iJ8x123/ 精彩视频"
    cleaned = VideoExtractor.extract_clean_url(raw)
    assert cleaned.startswith("https://v.douyin.com/iJ8x123")


def test_audio_transcriber_fallback():
    # 测试文件不存在时的安全返回
    res = AudioTranscriber.transcribe("non_existent_audio.mp3")
    assert res == ""


def test_script_generator_from_reference():
    generator = ScriptGenerator()
    ref_title = "为什么很多程序员越努力越焦虑？"
    ref_text = "很多人以为焦虑是因为技术不够好，但其实是认知陷阱。今天拆解三个破局思维。"
    script = generator.generate_script_from_reference(ref_title, ref_text, project_id="test_ref_proj")
    assert script.project_id == "test_ref_proj"
    assert len(script.scenes) >= 4
    assert script.title != ""


def test_subtitle_aligner_word_level():
    mock_scene = {
        "voiceover_text": "很多人以为自律靠死撑，但其实都错了！",
        "duration": 3.0,
        "word_timestamps": [
            {"text": "很多人", "start": 0.0, "end": 0.6},
            {"text": "以为", "start": 0.6, "end": 1.0},
            {"text": "自律", "start": 1.0, "end": 1.4},
            {"text": "靠死撑，", "start": 1.4, "end": 2.0},
            {"text": "但其实", "start": 2.0, "end": 2.5},
            {"text": "都错了！", "start": 2.5, "end": 3.0},
        ]
    }
    chunks = SubtitleAligner.chunk_scene_subtitles(mock_scene, start_offset=0.0)
    assert len(chunks) >= 1
    first_chunk = chunks[0]
    assert "words" in first_chunk
    assert len(first_chunk["words"]) > 0
    assert first_chunk["words"][0]["text"] != ""


def test_ai_image_generator_prompt_and_fallback(tmp_path):
    gen = AIImageGenerator()
    enhanced = gen.enhance_prompt("futuristic cpu chip")
    assert "9:16 vertical" in enhanced
    assert "cinematic lighting" in enhanced

    # 测试本地高质量保底图生成
    out_file = tmp_path / "test_ai_img.jpg"
    res = gen._generate_styled_graphic("test concept", out_file, scene_index=1)
    assert Path(res).exists()
    assert os.path.getsize(res) > 1000


def test_moviepy_karaoke_image_generation():
    renderer = MoviePyRenderer()
    img = renderer.create_karaoke_subtitle_image("自律的底层逻辑在于微习惯", active_word="微习惯")
    assert img.size == (1080, 220)

    title_img = renderer.create_title_banner_image("爆款大标题测试", layout="card_quote")
    assert title_img.size == (1080, 280)


def test_jianying_draft_multi_track(tmp_path):
    scenes = [
        {"scene_index": 1, "duration": 3.0, "voiceover_text": "第一句台词"},
        {"scene_index": 2, "duration": 4.0, "voiceover_text": "第二句台词"},
    ]
    subtitles = [
        {"text": "第一句台词", "start": 0.0, "end": 3.0},
        {"text": "第二句台词", "start": 3.0, "end": 7.0},
    ]
    draft_path = JianYingDraftGenerator.generate_draft("test_proj_p2", "测试爆款视频", scenes, subtitles)
    assert Path(draft_path).exists()
    json_path = Path(draft_path) / "draft_content.json"
    assert json_path.exists()
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["draft_name"] == "测试爆款视频"
        assert len(data["tracks"]) >= 2
