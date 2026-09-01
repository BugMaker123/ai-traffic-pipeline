import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env (启用 override=True 优先读取项目级配置)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# 目录路径定义
OUTPUT_DIR = BASE_DIR / "output"
AUDIO_OUTPUT_DIR = OUTPUT_DIR / "audio"
ASSETS_OUTPUT_DIR = OUTPUT_DIR / "video_assets"
FINAL_OUTPUT_DIR = OUTPUT_DIR / "final"
DRAFTS_OUTPUT_DIR = OUTPUT_DIR / "drafts"
STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"
BGM_DIR = STATIC_DIR / "bgm"

for d in [OUTPUT_DIR, AUDIO_OUTPUT_DIR, ASSETS_OUTPUT_DIR, FINAL_OUTPUT_DIR, DRAFTS_OUTPUT_DIR, STATIC_DIR, FONTS_DIR, BGM_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 大模型配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

# Pexels 素材 API
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# TTS 语音配置
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "zh-CN-YunxiNeural")  # 活力少年/解说风
DEFAULT_TTS_RATE = os.getenv("DEFAULT_TTS_RATE", "+0%")
DEFAULT_TTS_VOLUME = os.getenv("DEFAULT_TTS_VOLUME", "+0%")
DEFAULT_TTS_PITCH = os.getenv("DEFAULT_TTS_PITCH", "-2Hz")

# 视频输出规格 (9:16 爆款短视频分辨率)
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1920"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "30"))
MAX_RENDER_JOBS = max(1, int(os.getenv("MAX_RENDER_JOBS", "1")))
TTS_CONCURRENCY = max(1, min(6, int(os.getenv("TTS_CONCURRENCY", "3"))))
MEDIA_FETCH_CONCURRENCY = max(1, min(6, int(os.getenv("MEDIA_FETCH_CONCURRENCY", "3"))))
MAX_SCENES = max(1, int(os.getenv("MAX_SCENES", "12")))
OUTPUT_RETENTION_HOURS = max(1, int(os.getenv("OUTPUT_RETENTION_HOURS", "72")))

# 常用高质量音色预设
VOICE_PRESETS = {
    "yunxi": "zh-CN-YunxiNeural",       # 活力解说 (最推荐)
    "yunjian": "zh-CN-YunjianNeural",   # 稳重大气沉浸
    "xiaoxiao": "zh-CN-XiaoxiaoNeural", # 亲切知性女声
    "yunyang": "zh-CN-YunyangNeural",   # 专业新闻干货
    "xiaoyi": "zh-CN-XiaoyiNeural",     # 甜美自然女声
}
