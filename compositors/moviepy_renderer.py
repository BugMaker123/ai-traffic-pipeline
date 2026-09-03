"""
工业级 9:16 竖屏短视频自动化渲染合成引擎 (MoviePy v2 + PIL 高性能分层混流)
特性：
1. 逐字高亮 / 卡拉OK式动态字幕渲染 (Karaoke Dynamic Word Highlighting)
2. 多视频排版模版 (Impact 全屏爆款 / Split Screen 上下分屏 / Card Quote 磨砂金句)
3. 静态图片电影感 Ken Burns 运镜动态渲染
4. 转场破风音效 (Whoosh) 与 黄金强调音效 (Ding) 智能挂载
5. BGM 动态智能让音 (Ducking)
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )
except ImportError:
    from moviepy.editor import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )

from config.settings import FINAL_OUTPUT_DIR, VIDEO_FPS, VIDEO_HEIGHT, VIDEO_WIDTH
from media.sfx_manager import SFXManager

logger = logging.getLogger(__name__)


class MoviePyRenderer:
    """工业级竖屏短视频高性能合成器"""

    def __init__(
        self,
        width: int = VIDEO_WIDTH,
        height: int = VIDEO_HEIGHT,
        fps: int = VIDEO_FPS,
        caption_template: str = "impact",
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.caption_template = caption_template
        self._font_path = self._find_system_font()

    def _find_system_font(self) -> Optional[str]:
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc",  # 微软雅黑粗体
            "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
            "C:/Windows/Fonts/Deng.ttf",  # 等线
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _cover_clip(self, clip, target_w: Optional[int] = None, target_h: Optional[int] = None):
        """
        等比缩放并居中裁剪。对于横屏素材 (宽高比 > 1.15)，采用专业毛玻璃模糊背景垫底 + 前景等比居中。
        """
        tw = target_w or self.width
        th = target_h or self.height
        source_w, source_h = clip.size
        clip_dur = getattr(clip, "duration", None) or 3.0

        # 如果是显著横屏素材且目标为竖屏画幅，使用毛玻璃模糊背景垫底
        if source_w > source_h * 1.15 and th > tw:
            try:
                scale_bg = max(tw / source_w, th / source_h)
                bg_target_size = (int(round(source_w * scale_bg)), int(round(source_h * scale_bg)))
                bg_resized = clip.resized(bg_target_size) if hasattr(clip, "resized") else clip.resize(bg_target_size)
                x_center, y_center = bg_target_size[0] / 2, bg_target_size[1] / 2
                if hasattr(bg_resized, "cropped"):
                    bg_cropped = bg_resized.cropped(x_center=x_center, y_center=y_center, width=tw, height=th)
                else:
                    bg_cropped = bg_resized.crop(x_center=x_center, y_center=y_center, width=tw, height=th)

                # 下采样 + 放大实现快速高质感高斯模糊
                small_w, small_h = max(16, tw // 16), max(16, th // 16)
                bg_blur = bg_cropped.resized((small_w, small_h)) if hasattr(bg_cropped, "resized") else bg_cropped.resize((small_w, small_h))
                bg_blur = bg_blur.resized((tw, th)) if hasattr(bg_blur, "resized") else bg_blur.resize((tw, th))

                # 暗色蒙版压暗背景
                dim_mask = ColorClip(size=(tw, th), color=(0, 0, 0))
                dim_mask = dim_mask.with_duration(clip_dur) if hasattr(dim_mask, "with_duration") else dim_mask.set_duration(clip_dur)
                if hasattr(dim_mask, "with_opacity"):
                    dim_mask = dim_mask.with_opacity(0.45)
                elif hasattr(dim_mask, "set_opacity"):
                    dim_mask = dim_mask.set_opacity(0.45)

                bg_layer = CompositeVideoClip([bg_blur, dim_mask], size=(tw, th))
                bg_layer = bg_layer.with_duration(clip_dur) if hasattr(bg_layer, "with_duration") else bg_layer.set_duration(clip_dur)

                # 前景层：等比缩放至宽度填满
                fg_scale = tw / source_w
                fg_size = (tw, int(round(source_h * fg_scale)))
                fg_clip = clip.resized(fg_size) if hasattr(clip, "resized") else clip.resize(fg_size)
                if hasattr(fg_clip, "with_position"):
                    fg_clip = fg_clip.with_position(("center", "center"))
                else:
                    fg_clip = fg_clip.set_position(("center", "center"))

                composite = CompositeVideoClip([bg_layer, fg_clip], size=(tw, th))
                return composite.with_duration(clip_dur) if hasattr(composite, "with_duration") else composite.set_duration(clip_dur)
            except Exception as e:
                logger.warning("横屏毛玻璃背景渲染异常，降级为常规居中裁剪: %s", e)

        scale = max(tw / source_w, th / source_h)
        target_size = (int(round(source_w * scale)), int(round(source_h * scale)))
        resized = clip.resized(target_size) if hasattr(clip, "resized") else clip.resize(target_size)
        x_center, y_center = target_size[0] / 2, target_size[1] / 2
        if hasattr(resized, "cropped"):
            return resized.cropped(
                x_center=x_center,
                y_center=y_center,
                width=tw,
                height=th,
            )
        return resized.crop(
            x_center=x_center,
            y_center=y_center,
            width=tw,
            height=th,
        )

    def create_title_banner_image(self, title: str, layout: str = "impact") -> Image.Image:
        """渲染克制的短标题卡，避免大面积常驻遮挡画面。"""
        banner_h = 220
        img = Image.new("RGBA", (self.width, banner_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        font_size = 46 if len(title) > 12 else 52
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

        padding_x = 32
        padding_y = 13
        pill_rect = [tx - padding_x, ty - padding_y, tx + tw + padding_x, ty + th + padding_y]

        if layout == "card_quote":
            draw.rounded_rectangle(pill_rect, radius=20, fill=(20, 24, 36, 235), outline=(99, 102, 241, 200), width=3)
            draw.text((tx, ty), clean_title, font=font, fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=4)
        else:
            draw.rounded_rectangle(pill_rect, radius=18, fill=(8, 12, 20, 192), outline=(255, 255, 255, 45), width=2)
            draw.text((tx, ty), clean_title, font=font, fill=(255, 238, 110), stroke_fill=(5, 8, 14), stroke_width=3)

        return img

    def create_karaoke_subtitle_image(
        self,
        full_text: str,
        active_word: str = "",
        font_size: int = 50,
        subtitle_style: str = "impact_yellow",
    ) -> Image.Image:
        """
        渲染高网感工业级字幕花字（支持 6 大爆款风格：爆款黄白、赛博霓虹、综艺花字、电影纪实、极简胶囊、烈焰金榜）
        """
        sub_h = 220
        img = Image.new("RGBA", (self.width, sub_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 样式配置定义
        style_config = {
            "impact_yellow": {
                "base_color": (255, 255, 255),
                "base_stroke": (0, 0, 0),
                "stroke_w": 5,
                "shadow_color": (0, 0, 0, 180),
                "shadow_offset": (3, 4),
                "active_color": (255, 235, 0),
                "active_stroke": (0, 0, 0),
                "active_stroke_w": 7,
                "bg_fill": (0, 0, 0, 190),
                "bg_outline": (255, 235, 0, 80),
                "bg_radius": 20,
                "has_bg": True,
            },
            "cyber_neon": {
                "base_color": (56, 189, 248),
                "base_stroke": (10, 15, 30),
                "stroke_w": 4,
                "shadow_color": (56, 189, 248, 120),
                "shadow_offset": (0, 0),
                "active_color": (232, 70, 255),
                "active_stroke": (10, 15, 30),
                "active_stroke_w": 6,
                "bg_fill": (10, 16, 32, 215),
                "bg_outline": (56, 189, 248, 160),
                "bg_radius": 16,
                "has_bg": True,
            },
            "variety_pop": {
                "base_color": (255, 245, 120),
                "base_stroke": (15, 10, 25),
                "stroke_w": 6,
                "shadow_color": (255, 70, 120, 180),
                "shadow_offset": (4, 4),
                "active_color": (255, 46, 147),
                "active_stroke": (0, 0, 0),
                "active_stroke_w": 7,
                "bg_fill": (25, 12, 35, 205),
                "bg_outline": (255, 46, 147, 180),
                "bg_radius": 22,
                "has_bg": True,
            },
            "cinema_white": {
                "base_color": (248, 250, 252),
                "base_stroke": (15, 23, 42),
                "stroke_w": 3,
                "shadow_color": (0, 0, 0, 200),
                "shadow_offset": (2, 3),
                "active_color": (251, 191, 36),
                "active_stroke": (15, 23, 42),
                "active_stroke_w": 4,
                "bg_fill": (0, 0, 0, 120),
                "bg_outline": (255, 255, 255, 20),
                "bg_radius": 12,
                "has_bg": True,
            },
            "minimal_capsule": {
                "base_color": (15, 23, 42),
                "base_stroke": (255, 255, 255),
                "stroke_w": 0,
                "shadow_color": (0, 0, 0, 60),
                "shadow_offset": (0, 3),
                "active_color": (79, 70, 229),
                "active_stroke": (255, 255, 255),
                "active_stroke_w": 1,
                "bg_fill": (255, 255, 255, 238),
                "bg_outline": (99, 102, 241, 120),
                "bg_radius": 24,
                "has_bg": True,
            },
            "flame_gold": {
                "base_color": (251, 191, 36),
                "base_stroke": (50, 8, 8),
                "stroke_w": 5,
                "shadow_color": (239, 68, 68, 160),
                "shadow_offset": (3, 3),
                "active_color": (255, 69, 0),
                "active_stroke": (255, 235, 59),
                "active_stroke_w": 6,
                "bg_fill": (18, 8, 8, 225),
                "bg_outline": (239, 68, 68, 160),
                "bg_radius": 18,
                "has_bg": True,
            },
        }

        cfg = style_config.get(subtitle_style, style_config["impact_yellow"])

        try:
            font = ImageFont.truetype(self._font_path, font_size) if self._font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        # 按实际像素宽度自动换成最多两行，避免长句冲出安全区。
        max_text_w = self.width - 150
        lines: List[str] = []
        current = ""
        for char in full_text.strip():
            candidate = current + char
            box = draw.textbbox((0, 0), candidate, font=font, stroke_width=cfg["stroke_w"])
            if current and box[2] - box[0] > max_text_w:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) > 2:
            lines = [lines[0], "".join(lines[1:])]
            while draw.textbbox((0, 0), lines[1] + "…", font=font)[2] > max_text_w and len(lines[1]) > 2:
                lines[1] = lines[1][:-1]
            lines[1] += "…"

        line_gap = 12
        line_metrics = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=cfg["stroke_w"])
            line_metrics.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
        total_w = max((m[0] for m in line_metrics), default=0)
        total_h = sum(m[1] for m in line_metrics) + line_gap * max(0, len(lines) - 1)
        start_x = (self.width - total_w) // 2
        start_y = (sub_h - total_h) // 2

        # 绘制背景装饰板
        if cfg["has_bg"]:
            pad_x, pad_y = 28, 14
            pill_box = [start_x - pad_x, start_y - pad_y, start_x + total_w + pad_x, start_y + total_h + pad_y]
            draw.rounded_rectangle(
                pill_box,
                radius=cfg["bg_radius"],
                fill=cfg["bg_fill"],
                outline=cfg["bg_outline"],
                width=2,
            )

        # 逐字分段渲染：每行独立居中，激活词只轻微提亮，不做廉价跳字。
        active_found = False
        global_offset = 0
        cur_y = start_y
        for line, (line_w, line_h) in zip(lines, line_metrics):
            cur_x = (self.width - line_w) // 2
            i = 0
            while i < len(line):
                is_active_part = bool(active_word and not active_found and full_text[global_offset + i:global_offset + i + len(active_word)] == active_word)
                match_len = len(active_word) if is_active_part else 1
                word_slice = line[i:i + match_len]
                ch_bbox = draw.textbbox((0, 0), word_slice, font=font, stroke_width=cfg["stroke_w"])
                ch_w = ch_bbox[2] - ch_bbox[0]

                if is_active_part:
                    active_found = True
                    so_x, so_y = cfg["shadow_offset"]
                    if so_x != 0 or so_y != 0:
                        draw.text(
                            (cur_x + so_x, cur_y + so_y - 1), word_slice,
                            font=font, fill=cfg["shadow_color"],
                        )
                    draw.text(
                        (cur_x, cur_y - 1), word_slice, font=font,
                        fill=cfg["active_color"], stroke_fill=cfg["active_stroke"],
                        stroke_width=cfg["active_stroke_w"],
                    )
                else:
                    so_x, so_y = cfg["shadow_offset"]
                    if so_x != 0 or so_y != 0:
                        draw.text(
                            (cur_x + so_x, cur_y + so_y), word_slice,
                            font=font, fill=cfg["shadow_color"],
                        )
                    draw.text(
                        (cur_x, cur_y), word_slice, font=font,
                        fill=cfg["base_color"], stroke_fill=cfg["base_stroke"],
                        stroke_width=cfg["stroke_w"],
                    )

                cur_x += ch_w
                i += match_len
            global_offset += len(line)
            cur_y += line_h + line_gap

        return img

    def create_dynamic_subtitle_image(
        self,
        text: str,
        subtitle_style: str = "impact_yellow",
    ) -> Image.Image:
        """渲染高对比度短视频静态字幕 (1080x240)"""
        return self.create_karaoke_subtitle_image(text, active_word="", subtitle_style=subtitle_style)

    @classmethod
    def detect_hwaccel_codec(cls) -> str:
        """检测当前系统可用的硬件加速视频编码器，优先使用 GPU 加速"""
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            res = subprocess.run([ffmpeg_exe, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            output = res.stdout or ""
            if "h264_nvenc" in output:
                logger.info("检测到 NVIDIA NVENC 硬件加速编码器，将启用 h264_nvenc")
                return "h264_nvenc"
            if "h264_qsv" in output:
                logger.info("检测到 Intel QSV 硬件加速编码器，将启用 h264_qsv")
                return "h264_qsv"
            if "h264_amf" in output:
                logger.info("检测到 AMD AMF 硬件加速编码器，将启用 h264_amf")
                return "h264_amf"
        except Exception as e:
            logger.debug("检测硬件编码器失败，回退至 libx264: %s", e)
        return "libx264"

    def _add_camera_motion(self, clip, duration: float, scene_index: int, enable_punch_in: bool = True):
        """为静帧加入克制且交替的推拉运动与开端卡点微弹跳 (Punch-in Bounce)"""
        zoom_in = scene_index % 3 != 1
        def scale_at(t: float) -> float:
            progress = min(1.0, max(0.0, t / max(duration, 0.1)))
            eased = progress * progress * (3.0 - 2.0 * progress)
            drift = (1.0 + 0.055 * eased) if zoom_in else (1.055 - 0.055 * eased)
            if enable_punch_in and t < 0.35:
                # 前 0.35s 内施加正弦微弹跳，增强卡点爽感
                bounce = 0.045 * math.sin(math.pi * (t / 0.35))
                return drift + bounce
            return drift
        moving = clip.resized(scale_at) if hasattr(clip, "resized") else clip.resize(scale_at)
        moving = moving.with_position(("center", "center")) if hasattr(moving, "with_position") else moving.set_position(("center", "center"))
        canvas = CompositeVideoClip([moving], size=(int(clip.size[0]), int(clip.size[1])))
        return canvas.with_duration(duration) if hasattr(canvas, "with_duration") else canvas.set_duration(duration)

    def _apply_scene_transition(self, clip, transition: str, idx: int, duration: float):
        """为分镜交界处挂载平滑转场动画（淡入、滑入等）"""
        try:
            import moviepy.video.fx as vfx
            t_dur = min(0.35, max(0.15, duration * 0.15))
            if idx == 0:
                if hasattr(clip, "with_effects") and hasattr(vfx, "FadeIn"):
                    return clip.with_effects([vfx.FadeIn(0.25)])
                return clip

            t_name = (transition or "").lower()
            if "slide" in t_name and hasattr(vfx, "SlideIn") and hasattr(clip, "with_effects"):
                side = "right" if "left" in t_name else "left"
                slided = clip.with_effects([vfx.SlideIn(t_dur, side)])
                canvas = CompositeVideoClip([slided], size=(self.width, self.height))
                return canvas.with_duration(duration) if hasattr(canvas, "with_duration") else canvas.set_duration(duration)
            elif ("fade" in t_name or "cross" in t_name or "zoom" in t_name) and hasattr(vfx, "FadeIn") and hasattr(clip, "with_effects"):
                return clip.with_effects([vfx.FadeIn(t_dur)])
        except Exception as e:
            logger.debug("应用分镜转场失败: %s", e)
        return clip

    @staticmethod
    def _apply_bgm_ducking(
        bgm_clip,
        voice_intervals: List[Tuple[float, float]],
        duck_vol: float = 0.08,
        boost_vol: float = 0.22,
        ramp_time: float = 0.25,
    ):
        """对背景音乐应用基于人声区间的平滑动态闪避 (Sidechain Ducking)"""
        if not voice_intervals:
            return bgm_clip.with_volume_scaled(boost_vol) if hasattr(bgm_clip, "with_volume_scaled") else bgm_clip.volumex(boost_vol)

        def factor_filter(get_frame, t):
            fr = get_frame(t)
            t_arr = np.asarray(t, dtype=float)
            is_scalar = t_arr.ndim == 0
            t_1d = np.atleast_1d(t_arr)
            factors = np.full_like(t_1d, boost_vol, dtype=float)

            for s, e in voice_intervals:
                # 1. 处于人声主体发音区间内
                inside = (t_1d >= s) & (t_1d <= e)
                factors[inside] = np.minimum(factors[inside], duck_vol)

                # 2. 前置平滑衰减区 [s - ramp_time, s)
                ramp_in = (t_1d >= s - ramp_time) & (t_1d < s)
                if np.any(ramp_in):
                    ratio = (s - t_1d[ramp_in]) / ramp_time
                    val = duck_vol + (boost_vol - duck_vol) * 0.5 * (1.0 + np.cos(np.pi * (1.0 - ratio)))
                    factors[ramp_in] = np.minimum(factors[ramp_in], val)

                # 3. 后置平滑恢复区 (e, e + ramp_time]
                ramp_out = (t_1d > e) & (t_1d <= e + ramp_time)
                if np.any(ramp_out):
                    ratio = (t_1d[ramp_out] - e) / ramp_time
                    val = duck_vol + (boost_vol - duck_vol) * 0.5 * (1.0 - np.cos(np.pi * ratio))
                    factors[ramp_out] = np.minimum(factors[ramp_out], val)

            applied = factors[0] if is_scalar else factors
            if fr.ndim == 2:
                return fr * applied[:, None]
            return fr * applied

        if hasattr(bgm_clip, "transform"):
            return bgm_clip.transform(factor_filter, keep_duration=True)
        return bgm_clip.with_volume_scaled(duck_vol) if hasattr(bgm_clip, "with_volume_scaled") else bgm_clip.volumex(duck_vol)

    def render_project(
        self,
        project_id: str,
        title: str,
        scenes: List[Dict[str, Any]],
        subtitles: List[Dict[str, Any]],
        bgm_path: Optional[str] = None,
        output_path: Optional[Path] = None,
        layout_template: str = "impact",
        enable_karaoke: bool = True,
        subtitle_style: str = "impact_yellow",
        enable_punch_in: bool = True,
        codec: Optional[str] = None,
    ) -> str:
        """高性能流式短视频渲染合成 (支持 6 大字幕花字预设、卡点微弹跳与 GPU 加速)"""
        output_path = output_path or (FINAL_OUTPUT_DIR / f"{project_id}_final.mp4")

        sfx_mgr = SFXManager()
        whoosh_sfx = sfx_mgr.get_whoosh()
        ding_sfx = sfx_mgr.get_ding()

        scene_video_clips = []
        voiceover_clips = []
        voice_intervals: List[Tuple[float, float]] = []
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
                    actual_voice_dur = min(dur, getattr(a_clip, "duration", dur))
                    voice_intervals.append((scene_start, scene_start + actual_voice_dur))
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
            v_clip = None

            # 根据版式决定素材渲染尺寸
            if layout_template == "split_screen":
                render_w, render_h = self.width, int(self.height * 0.58)
            else:
                render_w, render_h = self.width, self.height

            if asset_file and Path(asset_file).exists():
                try:
                    if asset_type == "video":
                        v_raw = VideoFileClip(asset_file)
                        if v_raw.duration < dur:
                            loops = int(math.ceil(dur / v_raw.duration))
                            v_raw = concatenate_videoclips([v_raw] * loops)
                        v_sub = v_raw.subclipped(0, dur) if hasattr(v_raw, "subclipped") else v_raw.subclip(0, dur)
                        v_clip = self._cover_clip(v_sub, target_w=render_w, target_h=render_h)
                    else:
                        img_raw = ImageClip(asset_file)
                        v_sub = img_raw.with_duration(dur) if hasattr(img_raw, "with_duration") else img_raw.set_duration(dur)
                        v_clip = self._cover_clip(v_sub, target_w=render_w, target_h=render_h)
                        v_clip = self._add_camera_motion(v_clip, dur, idx, enable_punch_in=enable_punch_in)
                except Exception as e:
                    logger.warning("处理素材失败 file=%s error=%s", asset_file, e)

            if v_clip is None:
                c_raw = ColorClip(size=(render_w, render_h), color=(15, 20, 32))
                v_clip = c_raw.with_duration(dur) if hasattr(c_raw, "with_duration") else c_raw.set_duration(dur)

            # 若为上下分屏版式，复合上下结构
            if layout_template == "split_screen":
                bg_clip = ColorClip(size=(self.width, self.height), color=(12, 16, 24))
                bg_clip = bg_clip.with_duration(dur) if hasattr(bg_clip, "with_duration") else bg_clip.set_duration(dur)
                if hasattr(v_clip, "with_position"):
                    v_positioned = v_clip.with_position(("center", 0))
                else:
                    v_positioned = v_clip.set_position(("center", 0))
                v_clip = CompositeVideoClip([bg_clip, v_positioned], size=(self.width, self.height))
                v_clip = v_clip.with_duration(dur) if hasattr(v_clip, "with_duration") else v_clip.set_duration(dur)

            # 字幕生成 (支持卡拉OK逐字高亮切分)
            scene_sub_clips = []
            sub_y_pos = int(self.height * 0.69) if layout_template != "split_screen" else int(self.height * 0.66)

            for sub in subtitles:
                s_start = sub.get("start", 0.0)
                s_end = sub.get("end", s_start + 1.5)
                sub_text = sub.get("text", "").strip()
                words_list = sub.get("words", [])

                if not sub_text:
                    continue

                if scene_start <= s_start < scene_end:
                    local_chunk_start = s_start - scene_start
                    local_chunk_dur = max(0.2, min(s_end, scene_end) - s_start)

                    if enable_karaoke and words_list:
                        # 生成卡拉OK词级动效
                        for w in words_list:
                            w_start = w.get("start", s_start)
                            w_end = w.get("end", w_start + 0.3)
                            w_text = w.get("text", "")
                            if not w_text:
                                continue

                            w_local_start = max(0.0, w_start - scene_start)
                            w_local_dur = max(0.12, min(w_end, scene_end) - max(w_start, scene_start))

                            sub_img = self.create_karaoke_subtitle_image(sub_text, active_word=w_text, subtitle_style=subtitle_style)
                            sub_np = np.array(sub_img)
                            sub_clip = ImageClip(sub_np)

                            if hasattr(sub_clip, "with_start"):
                                sub_clip = sub_clip.with_start(w_local_start).with_duration(w_local_dur).with_position(("center", sub_y_pos))
                            else:
                                sub_clip = sub_clip.set_start(w_local_start).set_duration(w_local_dur).set_position(("center", sub_y_pos))
                            scene_sub_clips.append(sub_clip)
                    else:
                        # 默认静态整句字幕
                        sub_img = self.create_dynamic_subtitle_image(sub_text, subtitle_style=subtitle_style)
                        sub_np = np.array(sub_img)
                        sub_clip = ImageClip(sub_np)

                        if hasattr(sub_clip, "with_start"):
                            sub_clip = sub_clip.with_start(local_chunk_start).with_duration(local_chunk_dur).with_position(("center", sub_y_pos))
                        else:
                            sub_clip = sub_clip.set_start(local_chunk_start).set_duration(local_chunk_dur).set_position(("center", sub_y_pos))
                        scene_sub_clips.append(sub_clip)

            # 局部复合单分镜
            if scene_sub_clips:
                scene_composite = CompositeVideoClip([v_clip] + scene_sub_clips, size=(self.width, self.height))
                scene_composite = scene_composite.with_duration(dur) if hasattr(scene_composite, "with_duration") else scene_composite.set_duration(dur)
            else:
                scene_composite = v_clip

            transition = scene.get("transition", "fade")
            scene_composite = self._apply_scene_transition(scene_composite, transition, idx, dur)
            scene_video_clips.append(scene_composite)

            current_time_offset += dur

        # 2. 串联所有分镜
        base_video = concatenate_videoclips(scene_video_clips, method="compose")
        total_duration = base_video.duration

        # 3. 顶部爆款大标题 (覆盖全片顶端 10%)
        title_img = self.create_title_banner_image(title[:18], layout=layout_template)
        title_np = np.array(title_img)
        title_clip = ImageClip(title_np)
        title_clip = title_clip.with_duration(total_duration) if hasattr(title_clip, "with_duration") else title_clip.set_duration(total_duration)
        title_y = int(self.height * 0.055) if layout_template != "split_screen" else int(self.height * 0.035)
        if hasattr(title_clip, "with_position"):
            title_clip = title_clip.with_position(("center", title_y))
        else:
            title_clip = title_clip.set_position(("center", title_y))

        final_video_composite = CompositeVideoClip([base_video, title_clip], size=(self.width, self.height))
        final_video_composite = final_video_composite.with_duration(total_duration) if hasattr(final_video_composite, "with_duration") else final_video_composite.set_duration(total_duration)

        # 4. 音轨全流程混音
        audio_tracks = []
        if voiceover_clips:
            audio_tracks.extend(voiceover_clips)
        audio_tracks.extend(sfx_clips)

        if bgm_path and Path(bgm_path).exists():
            try:
                bgm_clip = AudioFileClip(bgm_path)
                if bgm_clip.duration < total_duration:
                    loops = int(math.ceil(total_duration / bgm_clip.duration))
                    bgm_clip = concatenate_audioclips([bgm_clip] * loops)
                bgm_clip = bgm_clip.subclipped(0, total_duration) if hasattr(bgm_clip, "subclipped") else bgm_clip.subclip(0, total_duration)
                bgm_clip = self._apply_bgm_ducking(bgm_clip, voice_intervals)
                audio_tracks.append(bgm_clip)
            except Exception as e:
                logger.warning("BGM 混音失败，跳过背景音乐: %s", e)

        if audio_tracks:
            mixed_audio = CompositeAudioClip(audio_tracks)
            final_video_composite = final_video_composite.with_audio(mixed_audio) if hasattr(final_video_composite, "with_audio") else final_video_composite.set_audio(mixed_audio)

        logger.info("开始渲染短视频 output=%s duration=%.1f (版式: %s, 卡拉OK: %s)", output_path, total_duration, layout_template, enable_karaoke)
        sys.stdout.flush()

        try:
            chosen_codec = codec or self.detect_hwaccel_codec()
            write_kwargs = {
                "fps": self.fps,
                "codec": chosen_codec,
                "audio_codec": "aac",
                "threads": 4,
            }
            if chosen_codec == "libx264":
                write_kwargs["preset"] = "ultrafast"
            final_video_composite.write_videofile(
                str(output_path),
                **write_kwargs,
            )
        finally:
            try:
                final_video_composite.close()
                for c in scene_video_clips:
                    c.close()
                for a in voiceover_clips + sfx_clips:
                    a.close()
            except Exception:
                pass

        return str(output_path)
