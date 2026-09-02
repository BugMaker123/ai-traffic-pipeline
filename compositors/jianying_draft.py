"""
剪映 / CapCut 自动化工程草稿生成器 (Advanced JianYing Draft Generator)
生成剪映可识别的 draft_content.json 与工程结构，支持一键在剪映中打开微调。
支持：主视频轨、人声解说轨、BGM背景音乐轨、SFX音效轨（Whoosh/Ding）、爆款大标题轨与花字字幕轨。
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import DRAFTS_OUTPUT_DIR, VIDEO_HEIGHT, VIDEO_WIDTH
from media.sfx_manager import SFXManager

logger = logging.getLogger(__name__)


class JianYingDraftGenerator:
    """剪映草稿工程生成器"""

    @staticmethod
    def generate_draft(
        project_id: str,
        title: str,
        scenes: List[Dict[str, Any]],
        subtitles: List[Dict[str, Any]],
        bgm_path: Optional[str] = None,
    ) -> str:
        """
        根据分镜与音频资产生成剪映 Draft 目录与 JSON 工程配置
        """
        draft_dir = DRAFTS_OUTPUT_DIR / f"{project_id}_jianying_draft"
        draft_dir.mkdir(parents=True, exist_ok=True)

        draft_id = str(uuid.uuid4()).upper()
        canvas_width = VIDEO_WIDTH
        canvas_height = VIDEO_HEIGHT

        sfx_mgr = SFXManager()
        whoosh_sfx = sfx_mgr.get_whoosh()
        ding_sfx = sfx_mgr.get_ding()

        # 轨道片段与素材池
        video_segments = []
        voice_segments = []
        sfx_segments = []
        bgm_segments = []
        subtitle_segments = []
        title_segments = []

        materials: Dict[str, List[Dict[str, Any]]] = {
            "videos": [],
            "audios": [],
            "texts": [],
            "speeds": [],
        }

        current_time_us = 0  # 微秒单位 (1s = 1,000,000us)

        # 1. 构建主视频、旁白与音效片段
        for idx, scene in enumerate(scenes):
            dur_sec = float(scene.get("duration", 3.5))
            dur_us = int(dur_sec * 1_000_000)

            # 视频/图片素材
            asset_file = scene.get("asset_file")
            if asset_file and Path(asset_file).exists():
                mat_id = str(uuid.uuid4())
                materials["videos"].append({
                    "id": mat_id,
                    "path": str(Path(asset_file).resolve()),
                    "type": scene.get("asset_type", "photo"),
                    "duration": dur_us,
                    "width": canvas_width,
                    "height": canvas_height,
                })

                video_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": mat_id,
                    "target_timerange": {
                        "duration": dur_us,
                        "start": current_time_us,
                    },
                    "source_timerange": {
                        "duration": dur_us,
                        "start": 0,
                    },
                })

            # 人声音频素材
            audio_file = scene.get("audio_file")
            if audio_file and Path(audio_file).exists():
                audio_mat_id = str(uuid.uuid4())
                materials["audios"].append({
                    "id": audio_mat_id,
                    "path": str(Path(audio_file).resolve()),
                    "duration": dur_us,
                })
                voice_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": audio_mat_id,
                    "target_timerange": {
                        "duration": dur_us,
                        "start": current_time_us,
                    },
                    "source_timerange": {
                        "duration": dur_us,
                        "start": 0,
                    },
                })

            # 转场破风音效 (分镜开头)
            if idx > 0 and Path(whoosh_sfx).exists():
                sfx_mat_id = str(uuid.uuid4())
                materials["audios"].append({
                    "id": sfx_mat_id,
                    "path": str(Path(whoosh_sfx).resolve()),
                    "duration": 400_000,
                })
                sfx_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": sfx_mat_id,
                    "target_timerange": {
                        "duration": 400_000,
                        "start": current_time_us,
                    },
                    "source_timerange": {
                        "duration": 400_000,
                        "start": 0,
                    },
                })

            # 强调音效 (尾部分镜)
            if idx == len(scenes) - 1 and Path(ding_sfx).exists():
                sfx_mat_id = str(uuid.uuid4())
                materials["audios"].append({
                    "id": sfx_mat_id,
                    "path": str(Path(ding_sfx).resolve()),
                    "duration": 600_000,
                })
                sfx_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": sfx_mat_id,
                    "target_timerange": {
                        "duration": 600_000,
                        "start": current_time_us,
                    },
                    "source_timerange": {
                        "duration": 600_000,
                        "start": 0,
                    },
                })

            current_time_us += dur_us

        # 2. BGM 背景音乐轨
        if bgm_path and Path(bgm_path).exists() and current_time_us > 0:
            bgm_mat_id = str(uuid.uuid4())
            materials["audios"].append({
                "id": bgm_mat_id,
                "path": str(Path(bgm_path).resolve()),
                "duration": current_time_us,
            })
            bgm_segments.append({
                "id": str(uuid.uuid4()),
                "material_id": bgm_mat_id,
                "target_timerange": {
                    "duration": current_time_us,
                    "start": 0,
                },
                "source_timerange": {
                    "duration": current_time_us,
                    "start": 0,
                },
            })

        # 3. 顶部大标题轨
        if title and current_time_us > 0:
            t_mat_id = str(uuid.uuid4())
            materials["texts"].append({
                "id": t_mat_id,
                "content": json.dumps({
                    "text": title[:20],
                    "styles": [{
                        "fill": {"color": [1.0, 0.9, 0.1]},
                        "border": {"color": [0, 0, 0], "width": 4},
                    }],
                }),
                "font_size": 22.0,
                "type": "title",
            })
            title_segments.append({
                "id": str(uuid.uuid4()),
                "material_id": t_mat_id,
                "target_timerange": {
                    "duration": current_time_us,
                    "start": 0,
                },
            })

        # 4. 构建花字字幕片段 (Texts)
        for sub in subtitles:
            text_str = sub.get("text", "")
            s_start_us = int(sub.get("start", 0.0) * 1_000_000)
            s_end_us = int(sub.get("end", 1.0) * 1_000_000)
            s_dur_us = max(200_000, s_end_us - s_start_us)

            sub_mat_id = str(uuid.uuid4())
            materials["texts"].append({
                "id": sub_mat_id,
                "content": json.dumps({
                    "text": text_str,
                    "styles": [
                        {
                            "fill": {"color": [1, 1, 1]},
                            "border": {"color": [0, 0, 0], "width": 3},
                        }
                    ],
                }),
                "font_size": 16.0,
                "type": "subtitle",
            })
            subtitle_segments.append({
                "id": str(uuid.uuid4()),
                "material_id": sub_mat_id,
                "target_timerange": {
                    "duration": s_dur_us,
                    "start": s_start_us,
                },
            })

        # 5. 组装剪映 draft_content.json 多轨道结构
        tracks = [
            {"id": str(uuid.uuid4()), "type": "video", "name": "视频画面", "segments": video_segments},
            {"id": str(uuid.uuid4()), "type": "audio", "name": "人声旁白", "segments": voice_segments},
        ]
        if sfx_segments:
            tracks.append({"id": str(uuid.uuid4()), "type": "audio", "name": "音效轨", "segments": sfx_segments})
        if bgm_segments:
            tracks.append({"id": str(uuid.uuid4()), "type": "audio", "name": "BGM背景音乐", "segments": bgm_segments})
        if title_segments:
            tracks.append({"id": str(uuid.uuid4()), "type": "text", "name": "爆款大标题", "segments": title_segments})
        tracks.append({"id": str(uuid.uuid4()), "type": "text", "name": "花字字幕", "segments": subtitle_segments})

        draft_content = {
            "id": draft_id,
            "draft_name": title[:20],
            "fps": 30.0,
            "duration": current_time_us,
            "canvas_config": {
                "width": canvas_width,
                "height": canvas_height,
                "ratio": "9:16",
            },
            "materials": materials,
            "tracks": tracks,
        }

        content_path = draft_dir / "draft_content.json"
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(draft_content, f, ensure_ascii=False, indent=2)

        logger.info("剪映草稿工程已生成 path=%s (包含 %d 条独立轨道)", draft_dir, len(tracks))
        return str(draft_dir)
