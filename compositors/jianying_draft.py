"""
剪映 / CapCut 自动化工程草稿生成器
生成剪映可识别的 draft_content.json 与工程结构，支持一键在剪映中打开微调
"""
import os
import json
import logging
import uuid
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from config.settings import DRAFTS_OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

logger = logging.getLogger(__name__)

class JianYingDraftGenerator:
    """剪映草稿工程生成器"""

    @staticmethod
    def generate_draft(
        project_id: str,
        title: str,
        scenes: List[Dict[str, Any]],
        subtitles: List[Dict[str, Any]],
        bgm_path: Optional[str] = None
    ) -> str:
        """
        根据分镜与音频资产生成剪映 Draft 目录与 JSON 工程配置
        """
        draft_dir = DRAFTS_OUTPUT_DIR / f"{project_id}_jianying_draft"
        draft_dir.mkdir(parents=True, exist_ok=True)
        
        draft_id = str(uuid.uuid4()).upper()
        canvas_width = VIDEO_WIDTH
        canvas_height = VIDEO_HEIGHT
        
        # 1. 构建音视频轨道与素材片段 (Segments)
        video_segments = []
        audio_segments = []
        text_segments = []
        
        materials = {
            "videos": [],
            "audios": [],
            "texts": [],
            "speeds": []
        }
        
        current_time_us = 0  # 微秒单位 (1s = 1,000,000us)
        
        for idx, scene in enumerate(scenes):
            dur_sec = scene.get("duration", 3.5)
            dur_us = int(dur_sec * 1_000_000)
            
            # 视频/图片素材
            asset_file = scene.get("asset_file")
            if asset_file:
                mat_id = str(uuid.uuid4())
                materials["videos"].append({
                    "id": mat_id,
                    "path": str(Path(asset_file).resolve()),
                    "type": scene.get("asset_type", "photo"),
                    "duration": dur_us,
                    "width": canvas_width,
                    "height": canvas_height
                })
                
                video_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": mat_id,
                    "target_timerange": {
                        "duration": dur_us,
                        "start": current_time_us
                    },
                    "source_timerange": {
                        "duration": dur_us,
                        "start": 0
                    }
                })
                
            # 人声音频素材
            audio_file = scene.get("audio_file")
            if audio_file:
                audio_mat_id = str(uuid.uuid4())
                materials["audios"].append({
                    "id": audio_mat_id,
                    "path": str(Path(audio_file).resolve()),
                    "duration": dur_us
                })
                audio_segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": audio_mat_id,
                    "target_timerange": {
                        "duration": dur_us,
                        "start": current_time_us
                    },
                    "source_timerange": {
                        "duration": dur_us,
                        "start": 0
                    }
                })
                
            current_time_us += dur_us

        # 2. 构建字幕片段 (Texts)
        for sub in subtitles:
            text_str = sub.get("text", "")
            s_start_us = int(sub.get("start", 0.0) * 1_000_000)
            s_end_us = int(sub.get("end", 1.0) * 1_000_000)
            s_dur_us = max(200_000, s_end_us - s_start_us)
            
            t_mat_id = str(uuid.uuid4())
            materials["texts"].append({
                "id": t_mat_id,
                "content": json.dumps({"text": text_str, "styles": [{"fill": {"color": [1, 1, 1]}}]}),
                "font_size": 15.0,
                "type": "subtitle"
            })
            text_segments.append({
                "id": str(uuid.uuid4()),
                "material_id": t_mat_id,
                "target_timerange": {
                    "duration": s_dur_us,
                    "start": s_start_us
                }
            })

        # 3. 组装剪映 draft_content.json
        draft_content = {
            "id": draft_id,
            "draft_name": title[:20],
            "fps": 30.0,
            "duration": current_time_us,
            "canvas_config": {
                "width": canvas_width,
                "height": canvas_height,
                "ratio": "9:16"
            },
            "materials": materials,
            "tracks": [
                {"id": str(uuid.uuid4()), "type": "video", "segments": video_segments},
                {"id": str(uuid.uuid4()), "type": "audio", "segments": audio_segments},
                {"id": str(uuid.uuid4()), "type": "text", "segments": text_segments}
            ]
        }

        content_path = draft_dir / "draft_content.json"
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(draft_content, f, ensure_ascii=False, indent=2)
            
        logger.info("剪映草稿工程已生成 path=%s", draft_dir)
        return str(draft_dir)
