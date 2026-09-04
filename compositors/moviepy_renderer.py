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

    def _cover_clip(self, clip, target_w: Optional[int] = None, target_h: Optional[int] = None, crop_x: float = 0.5, crop_y: float = 0.5):
        """
        等比缩放并居中裁剪 (对齐 main 分支高性能零嵌套实现，杜绝多层 CompositeVideoClip 导致的内存暴涨与 OOM)。
        """
        tw = target_w or self.width
        th = target_h or self.height
        source_w, source_h = clip.size

        scale = max(tw / source_w, th / source_h)
        target_size = (int(round(source_w * scale)), int(round(source_h * scale)))
        resized = clip.resized(target_size) if hasattr(clip, "resized") else clip.resize(target_size)
        half_w, half_h = tw / 2, th / 2
        x_center = min(max(target_size[0] * crop_x, half_w), target_size[0] - half_w)
        y_center = min(max(target_size[1] * crop_y, half_h), target_size[1] - half_h)

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

        # 样式配置定义 (现代顶流短视频通透花字体系，默认不遮挡画面)
        style_config = {
            "impact_yellow": {
                "base_color": (255, 255, 255),
                "base_stroke": (0, 0, 0),
                "stroke_w": 6,
                "shadow_color": (0, 0, 0, 230),
                "shadow_offset": (3, 5),
                "active_color": (255, 238, 0),
                "active_stroke": (0, 0, 0),
                "active_stroke_w": 8,
                "bg_fill": (0, 0, 0, 0),
                "bg_outline": (0, 0, 0, 0),
                "bg_radius": 0,
                "has_bg": False,
            },
            "cyber_neon": {
                "base_color": (240, 249, 255),
                "base_stroke": (10, 15, 30),
                "stroke_w": 5,
                "shadow_color": (56, 189, 248, 180),
                "shadow_offset": (2, 3),
                "active_color": (232, 70, 255),
                "active_stroke": (10, 15, 30),
                "active_stroke_w": 7,
                "bg_fill": (0, 0, 0, 0),
                "bg_outline": (0, 0, 0, 0),
                "bg_radius": 0,
                "has_bg": False,
            },
            "variety_pop": {
                "base_color": (255, 245, 120),
                "base_stroke": (15, 10, 25),
                "stroke_w": 6,
                "shadow_color": (255, 46, 147, 180),
                "shadow_offset": (3, 4),
                "active_color": (255, 46, 147),
                "active_stroke": (255, 255, 255),
                "active_stroke_w": 7,
                "bg_fill": (0, 0, 0, 0),
                "bg_outline": (0, 0, 0, 0),
                "bg_radius": 0,
                "has_bg": False,
            },
            "cinema_white": {
                "base_color": (255, 255, 255),
                "base_stroke": (15, 23, 42),
                "stroke_w": 4,
                "shadow_color": (0, 0, 0, 230),
                "shadow_offset": (2, 4),
                "active_color": (251, 191, 36),
                "active_stroke": (15, 23, 42),
                "active_stroke_w": 5,
                "bg_fill": (0, 0, 0, 0),
                "bg_outline": (0, 0, 0, 0),
                "bg_radius": 0,
                "has_bg": False,
            },
            "minimal_capsule": {
                "base_color": (248, 250, 252),
                "base_stroke": (15, 23, 42),
                "stroke_w": 2,
                "shadow_color": (0, 0, 0, 80),
                "shadow_offset": (0, 3),
                "active_color": (255, 235, 59),
                "active_stroke": (15, 23, 42),
                "active_stroke_w": 3,
                "bg_fill": (15, 23, 42, 175),
                "bg_outline": (255, 255, 255, 35),
                "bg_radius": 22,
                "has_bg": True,
            },
            "flame_gold": {
                "base_color": (254, 240, 138),
                "base_stroke": (50, 8, 8),
                "stroke_w": 6,
                "shadow_color": (239, 68, 68, 180),
                "shadow_offset": (3, 4),
                "active_color": (255, 69, 0),
                "active_stroke": (255, 235, 59),
                "active_stroke_w": 7,
                "bg_fill": (0, 0, 0, 0),
                "bg_outline": (0, 0, 0, 0),
                "bg_radius": 0,
                "has_bg": False,
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
    def _test_codec_available(cls, ffmpeg_exe: str, codec: str) -> bool:
        """运行短小的探测命令检验编码器是否能在当前硬件上实际初始化"""
        try:
            r = subprocess.run(
                [ffmpeg_exe, "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.04", "-c:v", codec, "-f", "null", "-"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            return r.returncode == 0
        except Exception:
            return False

    @classmethod
    def detect_hwaccel_codec(cls) -> str:
        """检测当前系统可用的硬件加速视频编码器，经过真实 probe 验证后优先使用 GPU 加速"""
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            res = subprocess.run([ffmpeg_exe, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            output = res.stdout or ""
            candidates = []
            if "h264_nvenc" in output:
                candidates.append(("h264_nvenc", "NVIDIA NVENC"))
            if "h264_qsv" in output:
                candidates.append(("h264_qsv", "Intel QSV"))
            if "h264_amf" in output:
                candidates.append(("h264_amf", "AMD AMF"))
            if "h264_mf" in output:
                candidates.append(("h264_mf", "MediaFoundation"))

            for codec_name, label in candidates:
                if cls._test_codec_available(ffmpeg_exe, codec_name):
                    logger.info("检测并通过验证硬件加速编码器: %s (%s)", codec_name, label)
                    return codec_name
                else:
                    logger.debug("编码器 %s 支持但当前系统环境无法初始化(如缺少驱动)，跳过", codec_name)
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
        return moving.with_duration(duration) if hasattr(moving, "with_duration") else moving.set_duration(duration)

    def create_pip_anchor_card(
        self,
        text: str,
        tag: str = "核心事实",
        width: int = 760,
        height: int = 140,
    ) -> Image.Image:
        """渲染轻量级画中画事实浮窗 (PIP Anchor Card)，在分镜前半段弹出，提供视觉焦点与信息增量"""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 磨砂感深色微晶底板
        draw.rounded_rectangle(
            [0, 0, width, height],
            radius=20,
            fill=(15, 23, 42, 220),
            outline=(255, 255, 255, 60),
            width=2,
        )

        try:
            font_tag = ImageFont.truetype(self._font_path, 22) if self._font_path else ImageFont.load_default()
            font_txt = ImageFont.truetype(self._font_path, 32) if self._font_path else ImageFont.load_default()
        except Exception:
            font_tag = ImageFont.load_default()
            font_txt = ImageFont.load_default()

        # 左侧胶囊标签
        tag_text = f"● {tag}"
        draw.rounded_rectangle([20, 18, 190, 56], radius=10, fill=(56, 189, 248, 40), outline=(56, 189, 248, 140), width=1)
        draw.text((32, 24), tag_text, font=font_tag, fill=(56, 189, 248, 255))

        # 主文案
        clean_txt = text.strip()
        if len(clean_txt) > 20:
            clean_txt = clean_txt[:19] + "…"
        draw.text((22, 74), clean_txt, font=font_txt, fill=(255, 255, 255, 255))

        return img

    def _prepare_adaptive_montage_clip(
        self,
        asset_file: str,
        asset_type: str,
        dur: float,
        scene_index: int,
        enable_punch_in: bool = True,
        render_w: int = None,
        render_h: int = None,
    ):
        """
        智能画框与微切镜蒙太奇 (Smart Framing & Micro-Cut Montage):
        1. 针对 16:9 横屏素材：采用“背景等比暗化模糊 + 前景完整圆角原比例三明治复合”，彻底告别断头断脸；
        2. 针对 9:16 竖屏素材：等比铺满；
        3. 当时长 > 4.2s 时拆解为 2~3 个子切镜（全景推进 -> 跳切特写 -> 景别缓动），彻底消灭静态 PPT 催眠感。
        """
        rw = render_w or self.width
        rh = render_h or self.height

        # A. 视频素材处理
        if asset_type == "video":
            v_raw = VideoFileClip(asset_file)
            if v_raw.duration < dur:
                loops = int(math.ceil(dur / v_raw.duration))
                v_raw = concatenate_videoclips([v_raw] * loops)
            v_sub = v_raw.subclipped(0, dur) if hasattr(v_raw, "subclipped") else v_raw.subclip(0, dur)
            return self._cover_clip(v_sub, target_w=rw, target_h=rh)

        # B. 图片素材处理
        try:
            with Image.open(asset_file) as im_test:
                orig_w, orig_h = im_test.size
        except Exception:
            orig_w, orig_h = rw, rh

        aspect = orig_w / max(1, orig_h)
        base_img_path = asset_file

        # 若是横屏素材 (如 16:9，aspect > 0.82)，构建三明治防断头复合底板
        if aspect > 0.82:
            try:
                sandwich_path = Path(asset_file).parent / f"adaptive_{Path(asset_file).stem}_{rw}x{rh}.jpg"
                if not sandwich_path.exists():
                    with Image.open(asset_file) as raw_im:
                        # 1. 背景层：等比铺满并重度高斯模糊与暗化
                        scale_bg = max(rw / orig_w, rh / orig_h)
                        bg_w, bg_h = int(round(orig_w * scale_bg)), int(round(orig_h * scale_bg))
                        bg_img = raw_im.resize((bg_w, bg_h), Image.Resampling.LANCZOS)
                        bx = (bg_w - rw) // 2
                        by = (bg_h - rh) // 2
                        bg_cropped = bg_img.crop((bx, by, bx + rw, by + rh))
                        bg_blurred = bg_cropped.filter(ImageFilter.GaussianBlur(radius=28))
                        # 暗调处理
                        dim_layer = Image.new("RGBA", (rw, rh), (8, 12, 20, 160))
                        bg_final = Image.alpha_composite(bg_blurred.convert("RGBA"), dim_layer)

                        # 2. 前景层：原比例圆角置于画面中心偏上
                        fg_target_w = int(rw * 0.94)
                        fg_target_h = int(fg_target_w / aspect)
                        fg_resized = raw_im.resize((fg_target_w, fg_target_h), Image.Resampling.LANCZOS).convert("RGBA")

                        # 给前景施加圆角与微边框
                        mask = Image.new("L", (fg_target_w, fg_target_h), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.rounded_rectangle([0, 0, fg_target_w, fg_target_h], radius=20, fill=255)

                        fg_x = (rw - fg_target_w) // 2
                        fg_y = int((rh - fg_target_h) * 0.42)
                        bg_final.paste(fg_resized, (fg_x, fg_y), mask)

                        bg_final.convert("RGB").save(str(sandwich_path), quality=95)
                base_img_path = str(sandwich_path)
            except Exception as e:
                logger.warning("构建自适应画框失败: %s", e)
                base_img_path = asset_file

        img_raw = ImageClip(base_img_path)

        # C. 微切镜蒙太奇 (Micro-Cut Montage)
        if dur <= 4.2:
            v_sub = img_raw.with_duration(dur) if hasattr(img_raw, "with_duration") else img_raw.set_duration(dur)
            v_clip = self._cover_clip(v_sub, target_w=rw, target_h=rh)
            return self._add_camera_motion(v_clip, dur, scene_index, enable_punch_in=enable_punch_in)

        # 长分镜 (> 4.2s)：拆解为 2~3 个富有电影感景别跳切的子切镜
        cut_durations = [dur * 0.48, dur * 0.52] if dur <= 7.5 else [dur * 0.33, dur * 0.35, dur * 0.32]
        sub_clips = []

        for c_idx, c_dur in enumerate(cut_durations):
            sub_raw = img_raw.with_duration(c_dur) if hasattr(img_raw, "with_duration") else img_raw.set_duration(c_dur)
            sub_base = self._cover_clip(sub_raw, target_w=rw, target_h=rh)

            if c_idx == 0:
                # 子切镜 1：全景平稳推镜 (1.0 -> 1.05) + 开篇卡点微弹跳
                def motion_s1(t, dur_val=c_dur):
                    p = min(1.0, max(0.0, t / max(dur_val, 0.1)))
                    eased = p * p * (3.0 - 2.0 * p)
                    drift = 1.0 + 0.05 * eased
                    if enable_punch_in and t < 0.32:
                        drift += 0.04 * math.sin(math.pi * (t / 0.32))
                    return drift
                sub_c = sub_base.resized(motion_s1) if hasattr(sub_base, "resized") else sub_base.resize(motion_s1)
            elif c_idx == 1:
                # 子切镜 2：★瞬间跳切至特写 (Jump-Cut Push-in)！从 1.13 缓慢回拉至 1.08，制造戏剧张力
                def motion_s2(t, dur_val=c_dur):
                    p = min(1.0, max(0.0, t / max(dur_val, 0.1)))
                    return 1.13 - 0.05 * (p * (2.0 - p))
                sub_c = sub_base.resized(motion_s2) if hasattr(sub_base, "resized") else sub_base.resize(motion_s2)
            else:
                # 子切镜 3：平稳推进与沉淀 (1.04 -> 1.09)
                def motion_s3(t, dur_val=c_dur):
                    p = min(1.0, max(0.0, t / max(dur_val, 0.1)))
                    return 1.04 + 0.05 * (p * p)
                sub_c = sub_base.resized(motion_s3) if hasattr(sub_base, "resized") else sub_base.resize(motion_s3)

            sub_c = sub_c.with_duration(c_dur) if hasattr(sub_c, "with_duration") else sub_c.set_duration(c_dur)
            sub_clips.append(sub_c)

        return concatenate_videoclips(sub_clips)

    def _apply_scene_transition(self, clip, transition: str, idx: int, duration: float):
        """为分镜交界处挂载爆款视觉转场（闪白高爆、极速推拉、平滑滑切、淡入溶解）"""
        try:
            import moviepy.video.fx as vfx
            t_name = (transition or "").lower()
            t_dur = min(0.32, max(0.16, duration * 0.12))

            # 第 0 镜首镜默认纯净快速淡入
            if idx == 0:
                if hasattr(clip, "with_effects") and hasattr(vfx, "FadeIn"):
                    return clip.with_effects([vfx.FadeIn(0.25)])
                return clip

            # 1. 闪白高光转场 (Flash White) - 仅在明确标记或高潮时触发，杜绝奇数镜头机械闪白
            if "flash" in t_name:
                flash_dur = min(0.18, t_dur)
                white_clip = ColorClip(size=(self.width, self.height), color=(255, 255, 255))
                white_clip = white_clip.with_duration(flash_dur) if hasattr(white_clip, "with_duration") else white_clip.set_duration(flash_dur)
                if hasattr(white_clip, "with_effects") and hasattr(vfx, "FadeOut"):
                    white_clip = white_clip.with_effects([vfx.FadeOut(flash_dur)])
                elif hasattr(white_clip, "fadeout"):
                    white_clip = white_clip.fadeout(flash_dur)
                composite = CompositeVideoClip([clip, white_clip], size=(self.width, self.height))
                return composite.with_duration(duration) if hasattr(composite, "with_duration") else composite.set_duration(duration)

            # 2. 滑入转场 (Slide In)
            if "slide" in t_name and hasattr(vfx, "SlideIn") and hasattr(clip, "with_effects"):
                side = "right" if "left" in t_name else "left"
                slided = clip.with_effects([vfx.SlideIn(t_dur, side)])
                canvas = CompositeVideoClip([slided], size=(self.width, self.height))
                return canvas.with_duration(duration) if hasattr(canvas, "with_duration") else canvas.set_duration(duration)

            # 3. 经典平滑淡入溶解 (Fade In)
            if hasattr(vfx, "FadeIn") and hasattr(clip, "with_effects"):
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
        """高性能流式短视频渲染合成 (支持 6 大字幕花字预设、闪白转场、卡点音效与 GPU 加速)"""
        output_path = output_path or (FINAL_OUTPUT_DIR / f"{project_id}_final.mp4")

        sfx_mgr = SFXManager()
        whoosh_sfx = sfx_mgr.get_whoosh()
        ding_sfx = sfx_mgr.get_ding()
        hit_sfx = sfx_mgr.get_hit()

        scene_video_clips = []
        voiceover_clips = []
        voice_intervals: List[Tuple[float, float]] = []
        sfx_clips = []

        current_time_offset = 0.0

        # 1. 遍历各分镜构建局部复合剪辑
        for idx, scene in enumerate(scenes):
            audio_file = scene.get("audio_file")
            dur = float(scene.get("duration", 4.0))
            s_type = scene.get("scene_type", "")
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

            # 转场破风音效 (Whoosh: 分镜交界处挂载，提供动态穿梭感)
            if idx > 0 and Path(whoosh_sfx).exists():
                try:
                    w_clip = AudioFileClip(whoosh_sfx)
                    w_sub = w_clip.with_duration(0.4) if hasattr(w_clip, "with_duration") else w_clip.set_duration(0.4)
                    w_sub = w_sub.with_start(scene_start) if hasattr(w_sub, "with_start") else w_sub.set_start(scene_start)
                    w_sub = w_sub.with_volume_scaled(0.45) if hasattr(w_sub, "with_volume_scaled") else w_sub.volumex(0.45)
                    sfx_clips.append(w_sub)
                except Exception:
                    pass

            # 核心冲突/转折/顿挫音效 (Hit: 强化高潮镜头的冲击感)
            if (s_type in ["action", "turn", "hook"] or idx in [1, 3]) and Path(hit_sfx).exists():
                try:
                    h_clip = AudioFileClip(hit_sfx)
                    h_sub = h_clip.with_duration(0.32) if hasattr(h_clip, "with_duration") else h_clip.set_duration(0.32)
                    h_sub = h_sub.with_start(scene_start + 0.05) if hasattr(h_sub, "with_start") else h_sub.set_start(scene_start + 0.05)
                    h_sub = h_sub.with_volume_scaled(0.40) if hasattr(h_sub, "with_volume_scaled") else h_sub.volumex(0.40)
                    sfx_clips.append(h_sub)
                except Exception:
                    pass

            # 尾部分镜结算与金句音效 (Ding: 清脆有力的价值感落点)
            if idx == len(scenes) - 1 and Path(ding_sfx).exists():
                try:
                    d_clip = AudioFileClip(ding_sfx)
                    d_sub = d_clip.with_duration(0.65) if hasattr(d_clip, "with_duration") else d_clip.set_duration(0.65)
                    d_sub = d_sub.with_start(scene_start) if hasattr(d_sub, "with_start") else d_sub.set_start(scene_start)
                    d_sub = d_sub.with_volume_scaled(0.45) if hasattr(d_sub, "with_volume_scaled") else d_sub.volumex(0.45)
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
                    v_clip = self._prepare_adaptive_montage_clip(
                        asset_file=asset_file,
                        asset_type=asset_type,
                        dur=dur,
                        scene_index=idx,
                        enable_punch_in=enable_punch_in,
                        render_w=render_w,
                        render_h=render_h,
                    )
                except Exception as e:
                    logger.warning("处理自适应微切镜素材失败 file=%s error=%s", asset_file, e)

            if v_clip is None:
                c_raw = ColorClip(size=(render_w, render_h), color=(15, 20, 32))
                v_clip = c_raw.with_duration(dur) if hasattr(c_raw, "with_duration") else c_raw.set_duration(dur)

            # 扁平化单层装配：底板 + 视频素材 + 画中画 + 字幕 + 转场高光
            layers = []
            if layout_template == "split_screen":
                bg_clip = ColorClip(size=(self.width, self.height), color=(12, 16, 24))
                bg_clip = bg_clip.with_duration(dur) if hasattr(bg_clip, "with_duration") else bg_clip.set_duration(dur)
                layers.append(bg_clip)
                if hasattr(v_clip, "with_position"):
                    v_clip = v_clip.with_position(("center", 0))
                else:
                    v_clip = v_clip.set_position(("center", 0))
            layers.append(v_clip)

            # 画中画视觉锚点图层 (PIP Overlay Card: 在实拍背景的 0.8s 优雅弹入，打破单调；若背景已是事实大字卡则跳过避免重叠)
            is_text_card = "fact_card" in str(asset_file).lower() or "typography" in str(asset_file).lower()
            pip_highlights = scene.get("caption_highlight", [])
            pip_keywords = scene.get("visual_keywords", [])
            pip_text = ""
            if pip_highlights and len(str(pip_highlights[0]).strip()) >= 2:
                pip_text = str(pip_highlights[0]).strip()
            elif pip_keywords and len(str(pip_keywords[0]).strip()) >= 2:
                pip_text = str(pip_keywords[0]).strip()
            elif idx in [0, 1, 3] and dur >= 3.5:
                vo_text = scene.get("voiceover_text", "")
                parts = [p.strip() for p in vo_text.replace("！", "，").replace("？", "，").split("，") if len(p.strip()) >= 4]
                if parts:
                    pip_text = parts[0][:16]

            if pip_text and dur >= 3.2 and not is_text_card:
                try:
                    pip_tag = {
                        "hook": "黄金前瞻",
                        "evidence": "关键证据",
                        "turn": "核心反转",
                        "action": "冲突焦点",
                        "outro": "深度复盘",
                    }.get(s_type, "事实视点")
                    pip_img = self.create_pip_anchor_card(text=pip_text, tag=pip_tag)
                    pip_clip = ImageClip(np.array(pip_img))
                    pip_dur = min(2.8, max(1.5, dur - 1.2))
                    pip_y = int(self.height * 0.18) if layout_template != "split_screen" else int(self.height * 0.12)
                    
                    if hasattr(pip_clip, "with_start"):
                        pip_clip = pip_clip.with_start(0.8).with_duration(pip_dur).with_position(("center", pip_y))
                    else:
                        pip_clip = pip_clip.set_start(0.8).set_duration(pip_dur).set_position(("center", pip_y))
                    
                    # 柔和淡入淡出动画
                    try:
                        import moviepy.video.fx as vfx
                        if hasattr(pip_clip, "with_effects") and hasattr(vfx, "FadeIn"):
                            pip_clip = pip_clip.with_effects([vfx.FadeIn(0.25), vfx.FadeOut(0.25)])
                    except Exception:
                        pass
                    layers.append(pip_clip)
                except Exception as e:
                    logger.debug("生成画中画锚点图层失败: %s", e)

            # 字幕生成 (单分镜精美通透大字花字)
            sub_y_pos = int(self.height * 0.69) if layout_template != "split_screen" else int(self.height * 0.66)
            for sub in subtitles:
                s_start = sub.get("start", 0.0)
                s_end = sub.get("end", s_start + 1.5)
                sub_text = sub.get("text", "").strip()
                if not sub_text:
                    continue

                if scene_start <= s_start < scene_end:
                    local_chunk_start = max(0.0, s_start - scene_start)
                    local_chunk_dur = max(0.2, min(s_end, scene_end) - s_start)
                    words_list = sub.get("words", [])

                    if enable_karaoke and words_list and len(words_list) <= 6:
                        for w in words_list:
                            w_text = w.get("text", "")
                            if not w_text:
                                continue
                            w_start = w.get("start", s_start)
                            w_end = w.get("end", w_start + 0.35)
                            w_local_start = max(0.0, w_start - scene_start)
                            w_local_dur = max(0.15, min(w_end, scene_end) - max(w_start, scene_start))

                            sub_img = self.create_karaoke_subtitle_image(sub_text, active_word=w_text, subtitle_style=subtitle_style)
                            sub_clip = ImageClip(np.array(sub_img))
                            if hasattr(sub_clip, "with_start"):
                                sub_clip = sub_clip.with_start(w_local_start).with_duration(w_local_dur).with_position(("center", sub_y_pos))
                            else:
                                sub_clip = sub_clip.set_start(w_local_start).set_duration(w_local_dur).set_position(("center", sub_y_pos))
                            layers.append(sub_clip)
                    else:
                        sub_img = self.create_dynamic_subtitle_image(sub_text, subtitle_style=subtitle_style)
                        sub_clip = ImageClip(np.array(sub_img))
                        if hasattr(sub_clip, "with_start"):
                            sub_clip = sub_clip.with_start(local_chunk_start).with_duration(local_chunk_dur).with_position(("center", sub_y_pos))
                        else:
                            sub_clip = sub_clip.set_start(local_chunk_start).set_duration(local_chunk_dur).set_position(("center", sub_y_pos))
                        layers.append(sub_clip)

            # 转场高光层 (仅在明确标记或转折/高潮镜头时触发，杜绝奇数镜头机械白屏)
            trans_name = (scene.get("transition", "") or "").lower()
            if ("flash" in trans_name or s_type in ["turn", "climax"]) and idx > 0:
                try:
                    flash_dur = min(0.18, dur * 0.12)
                    white_clip = ColorClip(size=(self.width, self.height), color=(255, 255, 255))
                    white_clip = white_clip.with_duration(flash_dur) if hasattr(white_clip, "with_duration") else white_clip.set_duration(flash_dur)
                    if hasattr(white_clip, "with_start"):
                        white_clip = white_clip.with_start(0.0)
                    else:
                        white_clip = white_clip.set_start(0.0)
                    layers.append(white_clip)
                except Exception:
                    pass

            if len(layers) > 1:
                scene_composite = CompositeVideoClip(layers, size=(self.width, self.height))
                scene_composite = scene_composite.with_duration(dur) if hasattr(scene_composite, "with_duration") else scene_composite.set_duration(dur)
            else:
                scene_composite = layers[0]

            scene_video_clips.append(scene_composite)
            current_time_offset += dur

        # 2. 串联所有分镜
        base_video = concatenate_videoclips(scene_video_clips, method="compose")
        total_duration = base_video.duration

        # 3. 顶部吸睛短标题 (前 4.5 秒亮明主题后平滑淡出，还给画面完整视界)
        banner_dur = min(4.5, total_duration)
        title_img = self.create_title_banner_image(title[:18], layout=layout_template)
        title_np = np.array(title_img)
        title_clip = ImageClip(title_np)
        title_clip = title_clip.with_duration(banner_dur) if hasattr(title_clip, "with_duration") else title_clip.set_duration(banner_dur)
        title_y = int(self.height * 0.055) if layout_template != "split_screen" else int(self.height * 0.035)
        if hasattr(title_clip, "with_position"):
            title_clip = title_clip.with_position(("center", title_y))
        else:
            title_clip = title_clip.set_position(("center", title_y))
        try:
            import moviepy.video.fx as vfx
            if hasattr(title_clip, "with_effects") and hasattr(vfx, "FadeOut"):
                title_clip = title_clip.with_effects([vfx.FadeOut(0.4)])
        except Exception:
            pass

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
            try:
                final_video_composite.write_videofile(
                    str(output_path),
                    **write_kwargs,
                )
            except Exception as encode_err:
                if chosen_codec != "libx264":
                    logger.warning("编码器 %s 写入视频失败(%s)，正在自动降级为 libx264 重试...", chosen_codec, encode_err)
                    write_kwargs["codec"] = "libx264"
                    write_kwargs["preset"] = "ultrafast"
                    final_video_composite.write_videofile(
                        str(output_path),
                        **write_kwargs,
                    )
                else:
                    raise encode_err
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
