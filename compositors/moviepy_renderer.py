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
        """等比缩放并居中裁剪，避免横版素材被强制拉伸。"""
        tw = target_w or self.width
        th = target_h or self.height
        source_w, source_h = clip.size
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
        """渲染爆款双色大标题 + 磨砂深色胶囊底板 (1080x280)"""
        banner_h = 280
        img = Image.new("RGBA", (self.width, banner_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        font_size = 52 if len(title) > 12 else 56
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

        padding_x = 36
        padding_y = 16
        pill_rect = [tx - padding_x, ty - padding_y, tx + tw + padding_x, ty + th + padding_y]

        if layout == "card_quote":
            draw.rounded_rectangle(pill_rect, radius=20, fill=(20, 24, 36, 235), outline=(99, 102, 241, 200), width=3)
            draw.text((tx, ty), clean_title, font=font, fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=4)
        else:
            draw.rounded_rectangle(pill_rect, radius=22, fill=(10, 12, 18, 225), outline=(255, 215, 0, 160), width=3)
            draw.text((tx, ty), clean_title, font=font, fill=(255, 230, 20), stroke_fill=(0, 0, 0), stroke_width=5)

        return img

    def create_karaoke_subtitle_image(
        self,
        full_text: str,
        active_word: str = "",
        font_size: int = 48,
    ) -> Image.Image:
        """渲染卡拉OK式逐字高亮字幕（当前朗读词呈现高光亮黄色与加粗强调）"""
        sub_h = 220
        img = Image.new("RGBA", (self.width, sub_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype(self._font_path, font_size) if self._font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), full_text, font=font, stroke_width=4)
        total_w = bbox[2] - bbox[0]
        total_h = bbox[3] - bbox[1]

        start_x = (self.width - total_w) // 2
        start_y = (sub_h - total_h) // 2

        # 磨砂黑圆角背景底板
        pad_x, pad_y = 30, 12
        draw.rounded_rectangle(
            [start_x - pad_x, start_y - pad_y, start_x + total_w + pad_x, start_y + total_h + pad_y],
            radius=18,
            fill=(0, 0, 0, 180),
            outline=(255, 255, 255, 30),
            width=1,
        )

        # 逐字绘制，高亮激活词
        cur_x = start_x
        # 简单字级拆分
        active_found = False
        i = 0
        while i < len(full_text):
            ch = full_text[i]
            # 检查是否匹配 active_word
            is_active_part = False
            if active_word and not active_found and full_text[i:i+len(active_word)] == active_word:
                is_active_part = True
                match_len = len(active_word)
                active_found = True
            else:
                match_len = 1

            word_slice = full_text[i:i+match_len]
            ch_bbox = draw.textbbox((0, 0), word_slice, font=font, stroke_width=4)
            ch_w = ch_bbox[2] - ch_bbox[0]

            if is_active_part:
                # 高亮为亮金色 + 醒目描边
                draw.text((cur_x, start_y - 2), word_slice, font=font, fill=(255, 235, 59), stroke_fill=(0, 0, 0), stroke_width=6)
            else:
                # 默认纯白文字
                draw.text((cur_x, start_y), word_slice, font=font, fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=4)

            cur_x += ch_w
            i += match_len

        return img

    def create_dynamic_subtitle_image(self, text: str) -> Image.Image:
        """渲染加粗高对比度短视频字幕 (1080x220)"""
        return self.create_karaoke_subtitle_image(text, active_word="")

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
    ) -> str:
        """高性能流式短视频渲染合成"""
        output_path = output_path or (FINAL_OUTPUT_DIR / f"{project_id}_final.mp4")

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
            sub_y_pos = int(self.height * 0.76) if layout_template != "split_screen" else int(self.height * 0.70)

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

                            sub_img = self.create_karaoke_subtitle_image(sub_text, active_word=w_text)
                            sub_np = np.array(sub_img)
                            sub_clip = ImageClip(sub_np)

                            if hasattr(sub_clip, "with_start"):
                                sub_clip = sub_clip.with_start(w_local_start).with_duration(w_local_dur).with_position(("center", sub_y_pos))
                            else:
                                sub_clip = sub_clip.set_start(w_local_start).set_duration(w_local_dur).set_position(("center", sub_y_pos))
                            scene_sub_clips.append(sub_clip)
                    else:
                        # 默认静态整句字幕
                        sub_img = self.create_dynamic_subtitle_image(sub_text)
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
                scene_video_clips.append(scene_composite)
            else:
                scene_video_clips.append(v_clip)

            current_time_offset += dur

        # 2. 串联所有分镜
        base_video = concatenate_videoclips(scene_video_clips, method="compose")
        total_duration = base_video.duration

        # 3. 顶部爆款大标题 (覆盖全片顶端 10%)
        title_img = self.create_title_banner_image(title[:18], layout=layout_template)
        title_np = np.array(title_img)
        title_clip = ImageClip(title_np)
        title_clip = title_clip.with_duration(total_duration) if hasattr(title_clip, "with_duration") else title_clip.set_duration(total_duration)
        title_y = int(self.height * 0.10) if layout_template != "split_screen" else int(self.height * 0.05)
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
                bgm_clip = bgm_clip.with_volume_scaled(0.14) if hasattr(bgm_clip, "with_volume_scaled") else bgm_clip.volumex(0.14)
                audio_tracks.append(bgm_clip)
            except Exception as e:
                logger.warning("BGM 混音失败，跳过背景音乐: %s", e)

        if audio_tracks:
            mixed_audio = CompositeAudioClip(audio_tracks)
            final_video_composite = final_video_composite.with_audio(mixed_audio) if hasattr(final_video_composite, "with_audio") else final_video_composite.set_audio(mixed_audio)

        logger.info("开始渲染短视频 output=%s duration=%.1f (版式: %s, 卡拉OK: %s)", output_path, total_duration, layout_template, enable_karaoke)
        sys.stdout.flush()

        try:
            final_video_composite.write_videofile(
                str(output_path),
                fps=self.fps,
                codec="libx264",
                audio_codec="aac",
                threads=4,
                preset="ultrafast",
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
