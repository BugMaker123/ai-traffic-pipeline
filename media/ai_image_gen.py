"""
AI 图像生成模块 (AI Image Generator)
支持 OpenAI DALL-E 3、SiliconFlow / Flux / SDXL、智谱 CogView 等生图 API。
当分镜关键词在 Pexels 中未检索到合适素材时，自动调用 AI 生图作为高质感兜底。
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config.settings import ASSETS_OUTPUT_DIR, OPENAI_API_KEY, OPENAI_BASE_URL, VIDEO_HEIGHT, VIDEO_WIDTH

from media.style_presets import style_manager

logger = logging.getLogger(__name__)


class AIImageGenerator:
    """AI 多模态生图客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.base_url = base_url or OPENAI_BASE_URL

    def enhance_prompt(self, raw_prompt: str, style_id: Optional[str] = "cinematic_dark") -> str:
        """强化提示词：注入全局艺术风格、竖屏构图与光影参数"""
        return style_manager.enhance_prompt(raw_prompt, style_id)

    def generate_image(
        self,
        prompt: str,
        project_id: str = "proj_demo",
        scene_index: int = 1,
        output_dir: Optional[Path] = None,
        style_id: Optional[str] = "cinematic_dark",
        voiceover_text: str = "",
        scene_type: str = "",
    ) -> Optional[str]:
        """
        生成 1080x1920 竖屏分镜配图
        """
        out_dir = output_dir or ASSETS_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{project_id}_ai_scene_{scene_index}_{uuid.uuid4().hex[:6]}.jpg"

        enhanced_p = self.enhance_prompt(prompt, style_id=style_id)

        # 1. 尝试调用 OpenAI / DALL-E 3 / 兼容生图 API
        if self.api_key and "deepseek" not in str(self.base_url).lower():
            try:
                base = self.base_url.rstrip("/")
                endpoint = f"{base}/images/generations"
                logger.info("正在调用 OpenAI/兼容 AI 生图 API (分镜 #%d): %s", scene_index, prompt[:40])

                payload = {
                    "prompt": enhanced_p,
                    "n": 1,
                    "size": "1024x1792" if "dall-e-3" in endpoint.lower() else "1024x1024",
                    "response_format": "b64_json",
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }

                resp = requests.post(endpoint, json=payload, headers=headers, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    item = data["data"][0]
                    if "b64_json" in item:
                        img_bytes = base64.b64decode(item["b64_json"])
                        with open(file_path, "wb") as f:
                            f.write(img_bytes)
                    elif "url" in item:
                        img_url = item["url"]
                        r_img = requests.get(img_url, timeout=20)
                        if r_img.status_code == 200:
                            with open(file_path, "wb") as f:
                                f.write(r_img.content)

                    if file_path.exists():
                        self._resize_and_crop(file_path)
                        logger.info("OpenAI AI 生图成功保存至: %s", file_path)
                        return str(file_path)
            except Exception as e:
                logger.warning("OpenAI 生图 API 调用失败 (%s)，降级至备选引擎", e)

        # 2. 免费高速 Flux / SDXL AI 生图引擎 (带短超时保护，避免阻塞)
        try:
            import urllib.parse
            clean_kw = prompt.replace("\n", " ").strip()
            encoded_prompt = urllib.parse.quote(f"{clean_kw}, cinematic, highly detailed 8k, photorealistic, 9:16 vertical")
            seed = abs(hash(prompt + str(scene_index))) % 1000000
            poll_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&model=flux&nologo=true&seed={seed}"
            logger.info("正在调用 Flux AI 多模态生成引擎 (分镜 #%d)...", scene_index)
            r_poll = requests.get(poll_url, timeout=10)
            if r_poll.status_code == 200 and len(r_poll.content) > 10000:
                with open(file_path, "wb") as f:
                    f.write(r_poll.content)
                if file_path.exists():
                    self._resize_and_crop(file_path)
                    logger.info("Flux AI 生图成功保存至: %s", file_path)
                    return str(file_path)
        except Exception as e:
            logger.warning("Pollinations 生图不可达 (%s)，切换至商业摄影图库或高级事实海报", e)

        # 3. 垂直商业摄影库匹配 (严格带项目去重)
        try:
            from media.pexels_client import PexelsMediaClient
            pexels_client = PexelsMediaClient()
            asset_res = pexels_client._match_and_download_curated_photo(prompt, scene_index, project_id)
            if asset_res and asset_res.get("asset_file"):
                src_path = Path(asset_res["asset_file"])
                if src_path.exists():
                    self._resize_and_crop(src_path)
                    logger.info("成功匹配并下载分镜 #%d 垂直摄影素材: %s", scene_index, src_path)
                    return str(src_path)
        except Exception as e:
            logger.warning("摄影素材库检索失败 (%s)，启用纪录片级事实排版卡片保底", e)

        # 4. 本地电影级事实引文与排版卡片保底 (强相关于当前文案，拒绝风马牛不相及的假图)
        return self._generate_documentary_typography_card(
            prompt=prompt,
            output_path=file_path,
            scene_index=scene_index,
            voiceover_text=voiceover_text,
            scene_type=scene_type,
        )

    def _resize_and_crop(self, image_path: Path) -> None:
        """确保图片严格裁剪为 1080x1920 竖屏规格"""
        try:
            with Image.open(image_path) as img:
                w, h = img.size
                scale = max(VIDEO_WIDTH / w, VIDEO_HEIGHT / h)
                nw, nh = int(round(w * scale)), int(round(h * scale))
                resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
                
                left = (nw - VIDEO_WIDTH) // 2
                top = (nh - VIDEO_HEIGHT) // 2
                cropped = resized.crop((left, top, left + VIDEO_WIDTH, top + VIDEO_HEIGHT))
                cropped.convert("RGB").save(image_path, "JPEG", quality=95)
        except Exception as e:
            logger.warning("调整 AI 图像尺寸失败: %s", e)

    def _find_font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/Dengb.ttf" if bold else "C:/Windows/Fonts/Deng.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _generate_documentary_typography_card(
        self,
        prompt: str,
        output_path: Path,
        scene_index: int,
        voiceover_text: str = "",
        scene_type: str = "",
    ) -> str:
        """
        生成工业级【电影纪实事实引文卡 (Documentary Typography Card)】
        契合当前文案语义，大字排版、磨砂高光与时间码装饰，质感比肩 Netflix 深度调查片
        """
        import math
        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (10, 14, 22))
        draw = ImageDraw.Draw(img)

        # 1. 绘制带有微光冷暖变化的暗夜深海渐变底板
        color_themes = [
            ((12, 16, 26), (20, 30, 48), (56, 189, 248)),   # 科技冷蓝
            ((16, 14, 24), (32, 22, 44), (168, 85, 247)),   # 幽深暗紫
            ((14, 18, 16), (24, 38, 30), (52, 211, 153)),   # 正义翡翠
            ((22, 16, 14), (44, 28, 22), (251, 146, 60)),   # 纪实琥珀
            ((24, 12, 16), (48, 20, 28), (244, 63, 94)),    # 冲突深绯
        ]
        c_dark, c_mid, c_accent = color_themes[(scene_index - 1) % len(color_themes)]

        for y in range(0, VIDEO_HEIGHT, 4):
            ratio = y / VIDEO_HEIGHT
            r = int(c_dark[0] * (1 - ratio) + c_mid[0] * ratio)
            g = int(c_dark[1] * (1 - ratio) + c_mid[1] * ratio)
            b = int(c_dark[2] * (1 - ratio) + c_mid[2] * ratio)
            draw.rectangle([0, y, VIDEO_WIDTH, y + 4], fill=(r, g, b))

        # 2. 局部高光微光漫反射球
        glow_layer = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(glow_layer)
        cx, cy = VIDEO_WIDTH // 2, int(VIDEO_HEIGHT * 0.45)
        g_draw.ellipse([cx - 480, cy - 360, cx + 480, cy + 360], fill=(c_accent[0], c_accent[1], c_accent[2], 38))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=90))
        img = Image.alpha_composite(img.convert("RGBA"), glow_layer).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 3. 顶部专业视听标记 (HUD / Viewfinder)
        font_sm = self._find_font(28, bold=True)
        font_mono = self._find_font(22, bold=False)
        scene_tag = {
            "hook": "● 01. 核心悬停 / HOOK",
            "evidence": "● 02. 关键事实 / EVIDENCE",
            "action": "● 03. 冲突升级 / CONFLICT",
            "turn": "● 04. 命运转折 / PIVOT",
            "outro": "● 05. 深度复盘 / OUTRO",
        }.get(scene_type, f"● SCENE 0{scene_index:02d} / ARCHIVE")

        # 顶部胶囊标签 (自适应文字宽度，防止切字)
        tag_bbox = draw.textbbox((0, 0), scene_tag, font=font_sm)
        tag_w = tag_bbox[2] - tag_bbox[0]
        pill_w = max(360, tag_w + 50)
        draw.rounded_rectangle([90, 160, 90 + pill_w, 216], radius=14, fill=(255, 255, 255, 18), outline=(255, 255, 255, 40), width=1)
        draw.text((115, 172), scene_tag, font=font_sm, fill=c_accent)
        draw.text((VIDEO_WIDTH - 380, 175), f"TC 00:0{scene_index}:18:24  RAW", font=font_mono, fill=(148, 163, 184))

        # 4. 中间区域：核心引文与金句卡片 (Card Frame)
        card_x1, card_y1, card_x2, card_y2 = 80, 360, VIDEO_WIDTH - 80, 1380
        # 磨砂质感卡片底衬
        card_overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        c_draw = ImageDraw.Draw(card_overlay)
        c_draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=28, fill=(15, 23, 42, 195), outline=(255, 255, 255, 30), width=2)
        
        # 装饰性大双引号
        font_quote = self._find_font(120, bold=True)
        c_draw.text((card_x1 + 45, card_y1 + 35), "“", font=font_quote, fill=(c_accent[0], c_accent[1], c_accent[2], 120))

        img = Image.alpha_composite(img.convert("RGBA"), card_overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 5. 提取并排版台词核心句 (自动优雅断句与换行，确保永不溢出)
        raw_text = voiceover_text.strip() or prompt.strip()
        clean_text = raw_text.replace("！", "，").replace("？", "，").replace("。", "，")
        clauses = [c.strip() for c in clean_text.split("，") if len(c.strip()) >= 3]
        if not clauses:
            clauses = [raw_text[:24]]

        display_lines = []
        for c in clauses[:4]:
            while len(c) > 13:
                display_lines.append(c[:13])
                c = c[13:]
            if c:
                display_lines.append(c)
            if len(display_lines) >= 3:
                break
        display_lines = display_lines[:3]

        font_title = self._find_font(50, bold=True)
        text_start_y = card_y1 + 175
        for idx, line in enumerate(display_lines):
            # 前两句用大字白字，末句用强调色
            fill_c = c_accent if idx == len(display_lines) - 1 else (248, 250, 252)
            draw.text((card_x1 + 65, text_start_y + idx * 85), line, font=font_title, fill=fill_c)

        # 6. 底部引文下装饰线与坐标徽标
        draw.line([card_x1 + 65, card_y2 - 130, card_x2 - 65, card_y2 - 130], fill=(255, 255, 255, 35), width=1)
        draw.text((card_x1 + 65, card_y2 - 95), "FACT-CHECKED INVESTIGATION", font=font_mono, fill=(100, 116, 139))
        draw.text((card_x2 - 240, card_y2 - 95), "VERIFIED AUDIO", font=font_mono, fill=c_accent)

        # 7. 画面底部全局水印与进度标尺
        draw.rectangle([80, VIDEO_HEIGHT - 120, VIDEO_WIDTH - 80, VIDEO_HEIGHT - 116], fill=(255, 255, 255, 25))
        progress_w = int((VIDEO_WIDTH - 160) * (scene_index / 8.0))
        draw.rectangle([80, VIDEO_HEIGHT - 120, 80 + progress_w, VIDEO_HEIGHT - 116], fill=c_accent)

        img.save(output_path, "JPEG", quality=95)
        return str(output_path)

    def _generate_styled_graphic(self, prompt: str, output_path: Path, scene_index: int) -> str:
        """向后兼容接口：委托至高级电影纪实事实引文排版卡片生成器"""
        return self._generate_documentary_typography_card(
            prompt=prompt,
            output_path=output_path,
            scene_index=scene_index,
            voiceover_text=prompt,
        )

