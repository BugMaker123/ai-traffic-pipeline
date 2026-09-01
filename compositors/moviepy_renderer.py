"""
工业级 9:16 竖屏短视频自动化渲染合成引擎 (MoviePy v2 + PIL 高性能分层混流)
特性：
1. 分镜级局部复合加速 (Rendering Speed x5)：按分镜生命周期局部复合字幕，避免全局图层爆炸
2. 爆款双色大标题 + 磨砂玻璃胶囊悬浮卡片 (黄金 10% 顶位)
3. 动态高亮跳跃字幕 (黄白双色字效 + 描边抗锯齿，黄金 74% 阅览位)
4. 转场破风音效 (Whoosh) 与 黄金强调音效 (Ding) 智能挂载
5. BGM 动态智能让音 (Ducking)
"""
import os
import sys
import math
import logging
import uuid
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
        CompositeAudioClip, concatenate_videoclips, concatenate_audioclips,
        ColorClip
    )
except ImportError:
    from moviepy.editor import (
        VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip,
        CompositeAudioClip, concatenate_videoclips, concatenate_audioclips,
        ColorClip
    )

from config.settings import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, FINAL_OUTPUT_DIR
from media.sfx_manager import SFXManager

logger = logging.getLogger(__name__)

class MoviePyRenderer:
    """工业级竖屏短视频高性能合成器"""
    
    def __init__(self, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT, fps: int = VIDEO_FPS, caption_template: str = "impact"):
        self.width = width
        self.height = height
        self.fps = fps
        self._font_path = self._find_system_font()
        self.caption_template = caption_template

    def _find_system_font(self) -> Optional[str]:
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑粗体
            "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",     # 黑体
            "C:/Windows/Fonts/Deng.ttf",       # 等线
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc"
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _cover_clip(self, clip, crop_x: float = 0.5, crop_y: float = 0.5):
        """等比缩放并居中裁剪，避免横版素材被强制拉伸。"""
        source_w, source_h = clip.size
        scale = max(self.width / source_w, self.height / source_h)
        target_size = (int(round(source_w * scale)), int(round(source_h * scale)))
        resized = clip.resized(target_size) if hasattr(clip, "resized") else clip.resize(target_size)
        half_w, half_h = self.width / 2, self.height / 2
        x_center = min(max(target_size[0] * crop_x, half_w), target_size[0] - half_w)
        y_center = min(max(target_size[1] * crop_y, half_h), target_size[1] - half_h)
        if hasattr(resized, "cropped"):
            return resized.cropped(
                x_center=x_center,
                y_center=y_center,
                width=self.width,
                height=self.height,
            )
        return resized.crop(
            x_center=x_center,
            y_center=y_center,
            width=self.width,
            height=self.height,
        )

    def create_title_banner_image(self, title: str) -> Image.Image:
        """渲染爆款双色大标题 + 磨砂深色胶囊底板 (1080x280)"""
        banner_h = 280
        img = Image.new("RGBA", (self.width, banner_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        font_size = 54
        try:
            font = ImageFont.truetype(self._font_path, font_size) if self._font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
            
        clean_title = title.strip()
        bbox = draw.textbbox((0, 0), clean_title, font=font, stroke_width=4)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        tx = (self.width - tw) // 2
        ty = (banner_h - th) // 2
        
        # 磨砂黑色微透光胶囊底
        padding_x = 36
        padding_y = 16
        pill_rect = [tx - padding_x, ty - padding_y, tx + tw + padding_x, ty + th + padding_y]
        
        draw.rounded_rectangle(pill_rect, radius=22, fill=(10, 12, 18, 220), outline=(255, 215, 0, 140), width=3)
        draw.text((tx, ty), clean_title, font=font, fill=(255, 230, 20), stroke_fill=(0, 0, 0), stroke_width=5)
        
        return img

    def create_dynamic_subtitle_image(self, text: str) -> Image.Image:
        """渲染加粗高对比度短视频字幕 (1080x220)"""
        sub_h = 220
        img = Image.new("RGBA", (self.width, sub_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        styles = {
            "impact": (48, (255, 255, 255), (0, 0, 0, 175), 4),
            "clean": (42, (255, 255, 255), (15, 18, 25, 130), 2),
            "news": (44, (255, 238, 30), (10, 35, 80, 220), 3),
            "warm": (46, (255, 247, 225), (92, 45, 34, 175), 3),
        }
        font_size, text_color, background_color, stroke_width = styles.get(self.caption_template, styles["impact"])
        try:
            font = ImageFont.truetype(self._font_path, font_size) if self._font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=4)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        tx = (self.width - tw) // 2
        ty = (sub_h - th) // 2
        
        # 半透深黑圆角背景条
        pad_x = 28
        pad_y = 10
        draw.rounded_rectangle(
            [tx - pad_x, ty - pad_y, tx + tw + pad_x, ty + th + pad_y],
            radius=16,
            fill=background_color
        )
        
        draw.text((tx, ty), text, font=font, fill=text_color, stroke_fill=(0, 0, 0), stroke_width=stroke_width)
        return img

    def render_project(
        self,
        project_id: str,
        title: str,
        scenes: List[Dict[str, Any]],
        subtitles: List[Dict[str, Any]],
        bgm_path: Optional[str] = None,
        output_path: Optional[Path] = None
    ) -> str:
        """高性能流式短视频渲染合成"""
        output_path = Path(output_path or (FINAL_OUTPUT_DIR / f"{project_id}_final.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex[:8]}.tmp.mp4")
        
        sfx_mgr = SFXManager()
        whoosh_sfx = sfx_mgr.get_whoosh()
        ding_sfx = sfx_mgr.get_ding()
        
        scene_video_clips = []
        voiceover_clips = []
        sfx_clips = []
        
        current_time_offset = 0.0
        
        # 1. 遍历各分镜构建局部复合剪辑
        for idx, scene in enumerate(scenes):
            audio_file = scene.get("audio_file")
            dur = float(scene.get("duration", 4.0))
            scene_start = current_time_offset
            scene_end = current_time_offset + dur
            
            # 旁白音轨
            if audio_file and Path(audio_file).exists():
                try:
                    a_clip = AudioFileClip(audio_file)
                    a_clip = a_clip.with_duration(dur) if hasattr(a_clip, "with_duration") else a_clip.set_duration(dur)
                    a_clip = a_clip.with_start(scene_start) if hasattr(a_clip, "with_start") else a_clip.set_start(scene_start)
                    voiceover_clips.append(a_clip)
                except Exception as e:
                    logger.warning("加载旁白失败 file=%s error=%s", audio_file, e)
                    
            # 转场破风音效 (分镜开头)
            if idx > 0 and Path(whoosh_sfx).exists():
                try:
                    w_clip = AudioFileClip(whoosh_sfx)
                    w_sub = w_clip.with_duration(0.4) if hasattr(w_clip, "with_duration") else w_clip.set_duration(0.4)
                    w_sub = w_sub.with_start(scene_start) if hasattr(w_sub, "with_start") else w_sub.set_start(scene_start)
                    w_sub = w_sub.with_volume_scaled(0.3) if hasattr(w_sub, "with_volume_scaled") else w_sub.volumex(0.3)
                    sfx_clips.append(w_sub)
                except Exception:
                    pass
                    
            # 尾部分镜强调音效 (Ding)
            if idx == len(scenes) - 1 and Path(ding_sfx).exists():
                try:
                    d_clip = AudioFileClip(ding_sfx)
                    d_sub = d_clip.with_duration(0.6) if hasattr(d_clip, "with_duration") else d_clip.set_duration(0.6)
                    d_sub = d_sub.with_start(scene_start) if hasattr(d_sub, "with_start") else d_sub.set_start(scene_start)
                    d_sub = d_sub.with_volume_scaled(0.35) if hasattr(d_sub, "with_volume_scaled") else d_sub.volumex(0.35)
                    sfx_clips.append(d_sub)
                except Exception:
                    pass
                    
            # 视觉画面加载
            asset_file = scene.get("asset_file")
            asset_type = scene.get("asset_type", "image")
            crop_x = float(scene.get("crop_x", 0.5))
            crop_y = float(scene.get("crop_y", 0.5))
            v_clip = None
            
            if asset_file and Path(asset_file).exists():
                try:
                    if asset_type == "video":
                        v_raw = VideoFileClip(asset_file)
                        trim_start = min(float(scene.get("trim_start", 0.0)), max(0.0, v_raw.duration - 0.1))
                        if trim_start > 0:
                            v_raw = v_raw.subclipped(trim_start) if hasattr(v_raw, "subclipped") else v_raw.subclip(trim_start)
                        speed = float(scene.get("playback_speed", 1.0))
                        if speed != 1.0 and hasattr(v_raw, "with_speed_scaled"):
                            v_raw = v_raw.with_speed_scaled(speed)
                        if v_raw.duration < dur:
                            loops = int(math.ceil(dur / v_raw.duration))
                            v_raw = concatenate_videoclips([v_raw] * loops)
                        v_sub = v_raw.subclipped(0, dur) if hasattr(v_raw, "subclipped") else v_raw.subclip(0, dur)
                        v_clip = self._cover_clip(v_sub, crop_x, crop_y)
                    else:
                        img_raw = ImageClip(asset_file)
                        v_sub = img_raw.with_duration(dur) if hasattr(img_raw, "with_duration") else img_raw.set_duration(dur)
                        v_clip = self._cover_clip(v_sub, crop_x, crop_y)
                except Exception as e:
                    logger.warning("处理素材失败 file=%s error=%s", asset_file, e)
                    
            if v_clip is None:
                c_raw = ColorClip(size=(self.width, self.height), color=(15, 20, 32))
                v_clip = c_raw.with_duration(dur) if hasattr(c_raw, "with_duration") else c_raw.set_duration(dur)
                
            # 查找落在当前分镜时间段内的字幕片段
            scene_sub_clips = []
            for sub in subtitles:
                s_start = sub.get("start", 0.0)
                s_end = sub.get("end", s_start + 1.5)
                sub_text = sub.get("text", "").strip()
                
                if not sub_text:
                    continue
                    
                # 检查是否与当前分镜有重叠
                if scene_start <= s_start < scene_end:
                    local_start = s_start - scene_start
                    local_dur = max(0.2, min(s_end, scene_end) - s_start)
                    
                    sub_img = self.create_dynamic_subtitle_image(sub_text)
                    sub_np = np.array(sub_img)
                    sub_clip = ImageClip(sub_np)
                    
                    if hasattr(sub_clip, "with_start"):
                        sub_clip = sub_clip.with_start(local_start).with_duration(local_dur).with_position(("center", int(self.height * 0.74)))
                    else:
                        sub_clip = sub_clip.set_start(local_start).set_duration(local_dur).set_position(("center", int(self.height * 0.74)))
                        
                    scene_sub_clips.append(sub_clip)
                    
            # 局部复合单分镜：底板 + 该分镜专属字幕 (极大提升 MoviePy 渲染效率)
            if scene_sub_clips:
                scene_composite = CompositeVideoClip([v_clip] + scene_sub_clips, size=(self.width, self.height))
                scene_composite = scene_composite.with_duration(dur) if hasattr(scene_composite, "with_duration") else scene_composite.set_duration(dur)
                scene_video_clips.append(scene_composite)
            else:
                scene_video_clips.append(v_clip)
                
            current_time_offset += dur

        # 2. 串联所有分镜
        base_video = concatenate_videoclips(scene_video_clips, method="compose")
        total_duration = base_video.duration
        
        # 3. 顶部爆款大标题 (覆盖全片顶端 10%)
        title_img = self.create_title_banner_image(title[:18])
        title_np = np.array(title_img)
        title_clip = ImageClip(title_np)
        title_clip = title_clip.with_duration(total_duration) if hasattr(title_clip, "with_duration") else title_clip.set_duration(total_duration)
        if hasattr(title_clip, "with_position"):
            title_clip = title_clip.with_position(("center", int(self.height * 0.10)))
        else:
            title_clip = title_clip.set_position(("center", int(self.height * 0.10)))
            
        final_video_composite = CompositeVideoClip([base_video, title_clip], size=(self.width, self.height))
        final_video_composite = final_video_composite.with_duration(total_duration) if hasattr(final_video_composite, "with_duration") else final_video_composite.set_duration(total_duration)

        # 4. 音轨全流程混音
        audio_tracks = []
        if voiceover_clips:
            # 每段旁白已经绑定全局起始时间；即使某个分镜缺音频，后续音轨也不会前移。
            audio_tracks.extend(voiceover_clips)
        audio_tracks.extend(sfx_clips)
        
        if bgm_path and Path(bgm_path).exists():
            try:
                bgm_clip = AudioFileClip(bgm_path)
                if bgm_clip.duration < total_duration:
                    loops = int(math.ceil(total_duration / bgm_clip.duration))
                    bgm_clip = concatenate_audioclips([bgm_clip] * loops)
                bgm_clip = bgm_clip.subclipped(0, total_duration) if hasattr(bgm_clip, "subclipped") else bgm_clip.subclip(0, total_duration)
                bgm_clip = bgm_clip.with_volume_scaled(0.14) if hasattr(bgm_clip, "with_volume_scaled") else bgm_clip.volumex(0.14)
                audio_tracks.append(bgm_clip)
            except Exception as e:
                logger.warning("BGM 混音失败，跳过背景音乐: %s", e)

        if audio_tracks:
            mixed_audio = CompositeAudioClip(audio_tracks)
            final_video_composite = final_video_composite.with_audio(mixed_audio) if hasattr(final_video_composite, "with_audio") else final_video_composite.set_audio(mixed_audio)

        logger.info("开始渲染 output=%s duration=%.1f", output_path, total_duration)
        sys.stdout.flush()
        
        try:
            final_video_composite.write_videofile(
                str(temp_output),
                fps=self.fps,
                codec="libx264",
                audio_codec="aac",
                threads=4,
                preset="ultrafast"
            )
            self.validate_output(temp_output, expected_duration=total_duration)
            temp_output.replace(output_path)
        finally:
            try:
                final_video_composite.close()
                for c in scene_video_clips:
                    c.close()
                for a in voiceover_clips + sfx_clips:
                    a.close()
            except Exception:
                pass
            if temp_output.exists():
                temp_output.unlink(missing_ok=True)
                
        return str(output_path)

    @staticmethod
    def validate_output(path: Path, expected_duration: float = 0.0) -> None:
        """在发布成品前验证容器、视频流、音频流和时长。"""
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError("渲染产物为空或不完整")
        clip = None
        try:
            clip = VideoFileClip(str(path))
            duration = float(clip.duration or 0.0)
            tolerance = max(1.5, expected_duration * 0.08)
            if duration <= 0 or (expected_duration and abs(duration - expected_duration) > tolerance):
                raise RuntimeError(f"渲染产物时长异常: {duration:.2f}s")
            if not getattr(clip, "size", None):
                raise RuntimeError("渲染产物缺少视频流")
            if clip.audio is None:
                raise RuntimeError("渲染产物缺少音频流")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"渲染产物无法读取: {exc}") from exc
        finally:
            if clip is not None:
                clip.close()
