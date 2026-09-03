"""
全局艺术风格预设与视觉一致性引擎 (Visual Art Style Presets & Entity Mapping)
统一短视频全部镜头的美术质感、色彩基调与光影参数，并为中式本土实体提供精准图库检索映射。
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StyleProfile(BaseModel):
    id: str
    name: str
    icon: str
    description: str
    positive_suffix: str
    negative_prompt: str
    color_palette: str = "moody"
    camera_hint: str = "35mm cinematic lens"


# 6 大工业级视觉风格定义
STYLE_PROFILES: Dict[str, StyleProfile] = {
    "cinematic_dark": StyleProfile(
        id="cinematic_dark",
        name="暗黑电影胶片",
        icon="🎬",
        description="柯达 35mm 电影胶片质感，高反差戏剧光影，深邃沉浸氛围",
        positive_suffix="cinematic lighting, 35mm Kodak Vision3 film grain, dramatic moody lighting, shallow depth of field, anamorphic lens, hyper-realistic, 8k resolution, photorealistic masterpiece",
        negative_prompt="cartoon, 3d render, illustration, low contrast, oversaturated, flat lighting, blurry, distorted face, watermark",
        color_palette="dark teal and amber",
        camera_hint="35mm anamorphic lens, f/1.8",
    ),
    "cyberpunk_neon": StyleProfile(
        id="cyberpunk_neon",
        name="赛博朋克霓虹",
        icon="🏙️",
        description="银翼杀手科技美学，高饱和洋红与青色霓虹辉光，未来都市感",
        positive_suffix="cyberpunk Blade Runner aesthetic, vivid magenta and cyan neon glow, reflections on wet dark asphalt, futuristic high-tech city atmosphere, volumetric fog, ray tracing, 8k",
        negative_prompt="daylight, natural sunlight, vintage, rustic, black and white, pastel colors, low quality",
        color_palette="neon magenta and cyan",
        camera_hint="cinematic wide lens, night glow",
    ),
    "minimalist_tech": StyleProfile(
        id="minimalist_tech",
        name="极简商业科技",
        icon="🍏",
        description="苹果商业广告质感，纯净通透漫反射柔光，高端克制现代空间",
        positive_suffix="Apple commercial aesthetic, pristine studio soft lighting, minimalist modern architectural interior, clean neutral color grading, ultra-sharp detail, elegant, 8k",
        negative_prompt="grunge, messy, dirty, dark horror, over-detailed, chaotic background, vintage",
        color_palette="neutral whites and metallic grays",
        camera_hint="50mm prime clean lens",
    ),
    "vintage_retro": StyleProfile(
        id="vintage_retro",
        name="复古港风胶片",
        icon="🎞️",
        description="90年代经典电影暖调微醺感，柔和胶片光晕，怀旧故事感",
        positive_suffix="90s Hong Kong vintage movie aesthetic, warm nostalgic golden tone, soft bloom lens flare, subtle film grain, Kodak Portra 400 colors, emotional atmosphere, 8k",
        negative_prompt="futuristic, cold blue digital, modern clinical, over-sharp, flat digital art",
        color_palette="warm amber and vintage green",
        camera_hint="vintage 50mm lens, soft focus",
    ),
    "anime_shinkai": StyleProfile(
        id="anime_shinkai",
        name="唯美新海诚风",
        icon="☁️",
        description="新海诚唯美动漫光影，壮丽云海、黄昏金色逆光与清透空气感",
        positive_suffix="Makoto Shinkai anime style, breathtaking sky with dramatic clouds, golden hour sunset glow, vibrant lush colors, painterly background art, cinematic anime masterpiece, 8k",
        negative_prompt="photorealistic, 3d cgi, dark horror, ugly face, western cartoon, noisy photo",
        color_palette="vivid cerulean blue and sunset orange",
        camera_hint="anime wide angle sky composition",
    ),
    "chinese_traditional": StyleProfile(
        id="chinese_traditional",
        name="新中式国潮风",
        icon="🎋",
        description="宋代极简东方美学，水墨留白与现代光影交融，典雅沉静禅意",
        positive_suffix="neo-Chinese traditional aesthetics, Song dynasty subtle elegance, minimalist ink wash texture fusion, soft zen atmospheric lighting, cinematic oriental composition, high detail, 8k",
        negative_prompt="western gothic, futuristic sci-fi neon, chaotic, noisy, neon oversaturated",
        color_palette="celadon jade and ink black",
        camera_hint="oriental minimalist framing",
    ),
}

# 中式本土高频实体意象与商业场景映射
LOCALIZED_ENTITY_MAP: Dict[str, str] = {
    "外卖": "food delivery courier scooter city street",
    "外卖员": "food delivery courier with helmet riding motorcycle in rain",
    "外卖骑手": "delivery courier riding electric scooter in rain city",
    "烧烤": "outdoor street food night market barbecue skewers",
    "夜市": "bustling Asian night market street food stalls steam",
    "相亲": "young adult man and woman meeting in modern cafe table conversation",
    "大厂": "high-tech corporate office building glass skyscraper",
    "加班": "tired young professional working late at computer office night",
    "自律": "disciplined person morning routine workout notebook desk",
    "内耗": "thoughtful anxious person looking through rain window reflections",
    "逆袭": "confident person walking determined city sunset light",
    "省钱": "person reviewing financial bills budget spreadsheet calculator",
    "房贷": "young couple reviewing real estate mortgage papers apartment",
    "县城": "peaceful Chinese small town street residential buildings trees",
    "菜市场": "vibrant traditional fresh vegetable market stalls morning sunlight",
    "打工人": "young urban office commuter walking in subway station crowd",
}


class StylePresetManager:
    """视觉艺术风格与实体映射管理器"""

    def __init__(self):
        self._profiles = STYLE_PROFILES
        self._entity_map = LOCALIZED_ENTITY_MAP

    def list_styles(self) -> List[Dict[str, str]]:
        """列出所有支持的美术风格"""
        return [
            {
                "id": p.id,
                "name": p.name,
                "icon": p.icon,
                "description": p.description,
                "color_palette": p.color_palette,
            }
            for p in self._profiles.values()
        ]

    def get_style(self, style_id: Optional[str]) -> StyleProfile:
        """获取指定风格，若无则默认 cinematic_dark"""
        if not style_id or style_id not in self._profiles:
            return self._profiles["cinematic_dark"]
        return self._profiles[style_id]

    def enhance_prompt(self, raw_prompt: str, style_id: Optional[str] = "cinematic_dark") -> str:
        """注入全局统一艺术风格修饰词与 9:16 构图规范"""
        profile = self.get_style(style_id)
        clean = raw_prompt.strip().rstrip(",")
        if not clean:
            clean = "cinematic scene visual"

        # 检查是否已包含该风格后缀
        if profile.positive_suffix[:20] in clean:
            return f"{clean}, 9:16 vertical composition"

        return f"{clean}, 9:16 vertical composition, {profile.positive_suffix}"

    def get_negative_prompt(self, style_id: Optional[str] = "cinematic_dark") -> str:
        profile = self.get_style(style_id)
        return profile.negative_prompt

    def map_localized_keywords(self, text_or_keywords: str) -> Optional[str]:
        """将中文本土特色词映射为适合海外图库/生图检索的具象英文概念"""
        for k, v in self._entity_map.items():
            if k in text_or_keywords:
                return v
        return None


style_manager = StylePresetManager()
