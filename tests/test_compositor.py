import sys
import os
import pytest
from pathlib import Path

# 设置 UTF-8 输出
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 添加工程根目录到 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from media.pexels_client import PexelsMediaClient
from media.bgm_manager import BGMManager
from compositors.moviepy_renderer import MoviePyRenderer
from compositors.jianying_draft import JianYingDraftGenerator

@pytest.mark.integration
def test_video_render_and_draft():
    project_id = "test_render_01"
    title = "90%的人都不知道的真相"
    
    print("▶ 1. 准备多分镜素材...")
    media_client = PexelsMediaClient()
    
    # 模拟两个分镜
    scenes = [
        {
            "scene_index": 1,
            "voiceover_text": "很多人以为自律靠硬撑，其实用对微习惯，坚持比放弃还容易！",
            "audio_file": str(BASE_DIR / "output" / "audio" / "test_tts.mp3"),
            "duration": 5.78,
            "visual_keywords": ["meditation morning", "focus work"]
        },
        {
            "scene_index": 2,
            "voiceover_text": "记住，启动比完美重要一百倍，今天就开始！",
            "audio_file": str(BASE_DIR / "output" / "audio" / "test_tts.mp3"),
            "duration": 5.78,
            "visual_keywords": ["sunrise success", "running"]
        }
    ]
    
    for idx, sc in enumerate(scenes, 1):
        asset = media_client.fetch_scene_asset(sc["visual_keywords"], idx, project_id)
        sc["asset_file"] = asset["asset_file"]
        sc["asset_type"] = asset["asset_type"]
        print(f"  分镜 {idx} 素材: {sc['asset_file']} ({sc['asset_type']})")
        
    subtitles = [
        {"text": "很多人以为自律靠硬撑", "start": 0.2, "end": 2.8},
        {"text": "其实用对微习惯，坚持比放弃还容易", "start": 2.8, "end": 5.7},
        {"text": "记住，启动比完美重要一百倍", "start": 6.0, "end": 8.8},
        {"text": "今天就开始，点赞收藏！", "start": 8.8, "end": 11.5}
    ]
    
    bgm_path = BGMManager.get_bgm(mood="energetic")
    print(f"▶ 2. 配乐文件: {bgm_path}")
    
    print("▶ 3. 正在调用 MoviePy 进行 1080x1920 渲染...")
    renderer = MoviePyRenderer()
    output_mp4 = renderer.render_project(
        project_id=project_id,
        title=title,
        scenes=scenes,
        subtitles=subtitles,
        bgm_path=bgm_path
    )
    
    print(f"视频输出文件: {output_mp4}, 存在: {os.path.exists(output_mp4)}")
    assert os.path.exists(output_mp4), "视频渲染失败，输出文件不存在"
    print(f"视频文件大小: {os.path.getsize(output_mp4) / 1024 / 1024:.2f} MB")
    
    print("▶ 4. 正在生成剪映草稿工程...")
    draft_path = JianYingDraftGenerator.generate_draft(
        project_id=project_id,
        title=title,
        scenes=scenes,
        subtitles=subtitles,
        bgm_path=bgm_path
    )
    print(f"剪映工程目录: {draft_path}")
    assert os.path.exists(draft_path), "剪映工程生成失败"
    
    print("\n🎉 视频渲染与剪映草稿全流程测试全部成功！")

if __name__ == "__main__":
    test_video_render_and_draft()
