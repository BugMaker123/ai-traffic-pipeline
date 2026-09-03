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
from media.pexels_client import PexelsMediaClient
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
    assert title_img.size == (1080, 220)

    long_img = renderer.create_karaoke_subtitle_image(
        "这是一句需要自动换行并始终留在竖屏安全区域内的较长字幕文案",
        active_word="自动换行",
    )
    assert long_img.getbbox() is not None


def test_scene_prompt_is_grounded_in_voiceover_and_shot_role():
    prompt = PexelsMediaClient._build_scene_prompt(
        "person checking a bill",
        ["restaurant receipt", "hands checking price"],
        "结账时他才发现套餐里多收了服务费。",
        "evidence",
    )
    assert "restaurant receipt" in prompt
    assert "服务费" in prompt
    assert "overhead detail shot" in prompt


def test_fallback_script_visuals_and_highlights_follow_the_topic():
    script = ScriptGenerator(api_key="")._generate_deep_fallback_script("外卖平台涨价", "商业认知", "proj_visual")
    assert all("外卖平台涨价" in scene.image_prompt for scene in script.scenes)
    assert all(scene.scene_type for scene in script.scenes)
    assert "双击收藏" not in {word for scene in script.scenes for word in scene.caption_highlight}


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
    meta_path = Path(draft_path) / "draft_meta_info.json"
    assert meta_path.exists()
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["draft_name"] == "测试爆款视频"
        assert len(data["tracks"]) >= 2

    with open(meta_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
        assert meta_data["draft_name"] == "测试爆款视频"
        assert meta_data["draft_id"] != ""
        assert meta_data["draft_type"] == "video"


def test_moviepy_bgm_ducking():
    import numpy as np
    from moviepy import AudioClip
    renderer = MoviePyRenderer()

    # 创建一个 4 秒的双声道恒定测试音轨
    test_clip = AudioClip(lambda t: np.stack([np.ones_like(t), np.ones_like(t)], axis=-1), duration=4.0)
    # 人声在 1.0s 到 2.5s
    voice_intervals = [(1.0, 2.5)]
    ducked_clip = renderer._apply_bgm_ducking(test_clip, voice_intervals, duck_vol=0.08, boost_vol=0.22)
    
    # 采样 0.2s (静音间歇) 和 1.8s (人声讲话中)
    sound_array = ducked_clip.to_soundarray(fps=100)
    quiet_sample = sound_array[20, 0]  # t = 0.2s
    voice_sample = sound_array[180, 0]  # t = 1.8s
    
    assert abs(quiet_sample - 0.22) < 0.03
    assert abs(voice_sample - 0.08) < 0.03


def test_moviepy_cover_clip_landscape():
    import numpy as np
    from moviepy import ImageClip
    renderer = MoviePyRenderer()

    # 创建横屏 1920x1080 图像
    img_np = np.zeros((1080, 1920, 3), dtype=np.uint8)
    img_np[:, :] = [120, 160, 210]
    clip = ImageClip(img_np).with_duration(2.0)

    covered = renderer._cover_clip(clip, target_w=1080, target_h=1920)
    assert covered.size == (1080, 1920)
    assert covered.duration == 2.0


def test_moviepy_scene_transitions():
    from moviepy import ColorClip
    renderer = MoviePyRenderer()

    c0 = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=2.0)
    c1 = ColorClip(size=(1080, 1920), color=(40, 40, 40), duration=2.0)

    t0 = renderer._apply_scene_transition(c0, "fade", idx=0, duration=2.0)
    assert t0.duration == 2.0

    t1 = renderer._apply_scene_transition(c1, "slide_left", idx=1, duration=2.0)
    assert t1.duration == 2.0

