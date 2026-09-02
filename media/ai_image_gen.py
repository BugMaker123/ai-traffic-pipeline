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
from PIL import Image, ImageDraw, ImageFont

from config.settings import ASSETS_OUTPUT_DIR, OPENAI_API_KEY, OPENAI_BASE_URL, VIDEO_HEIGHT, VIDEO_WIDTH

logger = logging.getLogger(__name__)


class AIImageGenerator:
    """AI 多模态生图客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.base_url = base_url or OPENAI_BASE_URL

    def enhance_prompt(self, raw_prompt: str) -> str:
        """强化提示词：注入电影质感、竖屏构图与真实光影"""
        clean = raw_prompt.strip()
        if not clean:
            clean = "modern high tech digital concept art"
        # 增加高质量修饰词
        return f"{clean}, 9:16 vertical composition, cinematic lighting, ultra detailed, 8k resolution, photorealistic, masterwork, masterpiece"

    def generate_image(
        self,
        prompt: str,
        project_id: str = "proj_demo",
        scene_index: int = 1,
        output_dir: Optional[Path] = None,
    ) -> Optional[str]:
        """
        生成 1080x1920 竖屏分镜配图
        """
        out_dir = output_dir or ASSETS_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{project_id}_ai_scene_{scene_index}_{uuid.uuid4().hex[:6]}.jpg"

        enhanced_p = self.enhance_prompt(prompt)

        # 1. 尝试调用 OpenAI / 兼容 /v1/images/generations
        if self.api_key:
            try:
                base = self.base_url.rstrip("/")
                endpoint = f"{base}/images/generations"
                logger.info("正在调用 AI 生图 API (分镜 #%d): %s", scene_index, prompt[:40])

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

                resp = requests.post(endpoint, json=payload, headers=headers, timeout=45)
                if resp.status_code == 200:
                    data = resp.json()
                    item = data["data"][0]
                    if "b64_json" in item:
                        img_bytes = base64.b64decode(item["b64_json"])
                        with open(file_path, "wb") as f:
                            f.write(img_bytes)
                    elif "url" in item:
                        img_url = item["url"]
                        r_img = requests.get(img_url, timeout=30)
                        if r_img.status_code == 200:
                            with open(file_path, "wb") as f:
                                f.write(r_img.content)

                    if file_path.exists():
                        self._resize_and_crop(file_path)
                        logger.info("AI 生图成功保存至: %s", file_path)
                        return str(file_path)
            except Exception as e:
                logger.warning("AI 生图 API 调用未成功 (%s)，使用高质感渐变海报兜底", e)

        # 2. 本地高质感海报渲染保底
        return self._generate_styled_graphic(prompt, file_path, scene_index)

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

    def _generate_styled_graphic(self, prompt: str, output_path: Path, scene_index: int) -> str:
        """生成带现代暗黑极光美学的极简视觉卡片作为可靠兜底"""
        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (12, 16, 24))
        draw = ImageDraw.Draw(img)

        # 绘制科技感氛围圆环与流光背景
        palettes = [
            ((30, 41, 59), (59, 130, 246), (147, 51, 234)),  # 科技蓝紫
            ((15, 23, 42), (16, 185, 129), (6, 182, 212)),   # 翡翠极光
            ((24, 24, 27), (245, 158, 11), (239, 68, 68)),   # 晚霞琥珀
            ((20, 20, 30), (139, 92, 246), (236, 72, 153)),  # 霓虹电音
        ]
        p = palettes[scene_index % len(palettes)]

        for i in range(12):
            radius = 160 + i * 45
            alpha_color = (
                int(p[1][0] * (1 - i / 12) + p[2][0] * (i / 12)),
                int(p[1][1] * (1 - i / 12) + p[2][1] * (i / 12)),
                int(p[1][2] * (1 - i / 12) + p[2][2] * (i / 12)),
            )
            cx, cy = VIDEO_WIDTH // 2, VIDEO_HEIGHT // 2 - 80
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius],
                outline=alpha_color,
                width=2
            )

        img.save(output_path, "JPEG", quality=95)
        return str(output_path)
