"""
端到端真实渲染与抽帧视觉质量审查脚本
验证：
1. 司法/严肃分镜素材匹配与高级事实卡片（彻底杜绝日出打坐瑜伽女）
2. 16:9 构图自适应三明治底板（防断头）
3. 微切镜蒙太奇（长镜头跳切推进）
4. 画中画视觉锚点卡片浮入
5. 现代通透加重阴影大花字字幕
6. 顶部吸睛标题 4.5s 淡出
"""
import os
import sys
from pathlib import Path
import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from compositors.moviepy_renderer import MoviePyRenderer
from media.pexels_client import PexelsMediaClient
from media.ai_image_gen import AIImageGenerator
from config.settings import FINAL_OUTPUT_DIR

def run_visual_audit():
    project_id = "test_visual_audit_p1"
    print("=== 开始运行视觉质量审查流程 ===")

    # 1. 验证素材获取：司法严肃主题分镜
    pexels = PexelsMediaClient()
    scene1_kw = ["courtroom", "trial", "judge gavel"]
    scene1_prompt = "cinematic close-up of a wooden judge's gavel in courtroom, dramatic lighting, 9:16 vertical"
    scene1_voice = "当庭认罪！这场审判彻底终结了所有心存侥幸者的幻想。"
    
    asset1 = pexels.fetch_scene_asset(
        keywords=scene1_kw,
        scene_idx=1,
        project_id=project_id,
        duration=5.5,
        image_prompt=scene1_prompt,
        voiceover_text=scene1_voice,
        scene_type="hook"
    )
    print(f"分镜 1 素材抓取结果: {asset1['source']} -> {asset1['asset_file']}")
    assert "photo-1506126613408-eca07ce68773" not in str(asset1.get("asset_file", ""))

    # 2. 验证事实引文排版卡片生成
    ai_gen = AIImageGenerator()
    fact_card_path = FINAL_OUTPUT_DIR / f"{project_id}_fact_card_test.jpg"
    card_res = ai_gen._generate_documentary_typography_card(
        prompt=scene1_prompt,
        output_path=fact_card_path,
        scene_index=1,
        voiceover_text=scene1_voice,
        scene_type="hook"
    )
    print(f"纪录片级事实引文卡生成成功: {card_res}")

    # 3. 构造 3 个完整分镜进行快速渲染测试 (总时长约 12 秒)
    scenes = [
        {
            "scene_index": 1,
            "scene_type": "hook",
            "voiceover_text": scene1_voice,
            "visual_keywords": ["courtroom", "gavel"],
            "image_prompt": scene1_prompt,
            "caption_highlight": ["当庭认罪"],
            "transition": "none",
            "duration": 4.8,
            "asset_file": asset1["asset_file"],
            "asset_type": asset1["asset_type"],
        },
        {
            "scene_index": 2,
            "scene_type": "evidence",
            "voiceover_text": "在翔实的卷宗与铁证面前，任何诡辩都显得苍白无力。",
            "visual_keywords": ["investigation documents", "evidence archive"],
            "image_prompt": "close-up of legal documents with red stamp and files on desk, cinematic, 9:16",
            "caption_highlight": ["铁证如山"],
            "transition": "none",
            "duration": 4.5,
            "asset_file": str(fact_card_path),
            "asset_type": "image",
        },
    ]

    subtitles = [
        {"start": 0.2, "end": 2.4, "text": "当庭认罪！这场审判", "words": [{"text": "当庭认罪", "start": 0.2, "end": 1.2}]},
        {"start": 2.5, "end": 4.6, "text": "彻底终结了所有心存侥幸者的幻想", "words": [{"text": "幻想", "start": 3.8, "end": 4.5}]},
        {"start": 5.0, "end": 7.2, "text": "在翔实的卷宗与铁证面前", "words": [{"text": "铁证面前", "start": 6.0, "end": 7.1}]},
        {"start": 7.3, "end": 9.2, "text": "任何诡辩都显得苍白无力", "words": [{"text": "苍白无力", "start": 8.0, "end": 9.1}]},
    ]

    out_mp4 = FINAL_OUTPUT_DIR / f"{project_id}_render.mp4"
    renderer = MoviePyRenderer()
    final_video = renderer.render_project(
        project_id=project_id,
        title="当庭认罪！乱港分子的终局审判",
        scenes=scenes,
        subtitles=subtitles,
        output_path=out_mp4,
        enable_karaoke=True,
        subtitle_style="impact_yellow",
    )
    print(f"测试视频渲染成功: {final_video}")

    # 4. 提取首秒帧与第 2 秒画中画帧、第 5 秒微切镜帧进行视觉审计
    try:
        from moviepy import VideoFileClip
    except ImportError:
        from moviepy.editor import VideoFileClip

    clip = VideoFileClip(final_video)
    print(f"视频时长: {clip.duration:.2f}s, 分辨率: {clip.size}")
    
    frame1 = clip.get_frame(1.2)  # 含顶部标题、画中画浮窗、花字字幕
    frame2 = clip.get_frame(3.6)  # 微切镜跳切帧
    frame3 = clip.get_frame(6.0)  # 第 2 镜事实引文卡帧 (此时顶部大标题已淡出消失)

    p1 = FINAL_OUTPUT_DIR / f"{project_id}_frame_1_2s.jpg"
    p2 = FINAL_OUTPUT_DIR / f"{project_id}_frame_3_6s.jpg"
    p3 = FINAL_OUTPUT_DIR / f"{project_id}_frame_6_0s.jpg"

    Image.fromarray(frame1).save(str(p1), quality=95)
    Image.fromarray(frame2).save(str(p2), quality=95)
    Image.fromarray(frame3).save(str(p3), quality=95)

    clip.close()
    print(f"视觉审计帧已提取:\n  1. {p1}\n  2. {p2}\n  3. {p3}")

if __name__ == "__main__":
    run_visual_audit()
