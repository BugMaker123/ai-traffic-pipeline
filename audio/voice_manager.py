"""
音色配置与声音克隆管理器 (Voice Profile & Clone Manager)
管理系统预设音色库与用户自定义克隆音色配置，支持参考音频管理与适配器自动路由。
"""
import os
import json
import uuid
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from config.settings import OUTPUT_DIR, DEFAULT_TTS_VOICE
from audio.adapters import BaseTTSAdapter, EdgeTTSAdapter, CosyVoiceAdapter

logger = logging.getLogger(__name__)

VOICES_DIR = OUTPUT_DIR / "voices"
VOICES_AUDIO_DIR = VOICES_DIR / "audio"
PROFILES_FILE = VOICES_DIR / "profiles.json"


class VoiceProfile(BaseModel):
    voice_id: str
    name: str
    gender: str = "male"  # male | female
    provider: str = "edge_tts"  # edge_tts | cosyvoice
    description: str = ""
    is_custom: bool = False
    reference_audio: Optional[str] = None
    reference_text: Optional[str] = None
    fallback_voice: str = DEFAULT_TTS_VOICE


PRESET_VOICES: List[VoiceProfile] = [
    VoiceProfile(
        voice_id="zh-CN-YunxiNeural",
        name="云希 (男声/活力爆款)",
        gender="male",
        provider="edge_tts",
        description="最经典的短视频爆款旁白解说音色，咬字清晰，节奏紧凑",
    ),
    VoiceProfile(
        voice_id="zh-CN-YunjianNeural",
        name="云健 (男声/沉稳磁性)",
        gender="male",
        provider="edge_tts",
        description="沉稳大气的成熟男声，适合商业认知、科技分析与历史解密",
    ),
    VoiceProfile(
        voice_id="zh-CN-XiaoxiaoNeural",
        name="晓晓 (女声/温暖知性)",
        gender="female",
        provider="edge_tts",
        description="知性亲切的女声，适合生活情感、心理学、治愈系文案",
    ),
    VoiceProfile(
        voice_id="zh-CN-YunyangNeural",
        name="云扬 (男声/专业播音)",
        gender="male",
        provider="edge_tts",
        description="专业的新闻播报语调，适合严谨时事、事实剖析与深度科普",
    ),
    VoiceProfile(
        voice_id="zh-CN-YunxiaNeural",
        name="云夏 (女声/活力元气)",
        gender="female",
        provider="edge_tts",
        description="年轻活泼的元气少女音，适合快节奏日常、娱乐盘点与好物推荐",
    ),
    VoiceProfile(
        voice_id="zh-CN-YunjieNeural",
        name="云捷 (男声/纪实故事)",
        gender="male",
        provider="edge_tts",
        description="富有讲述感的故事音色，适合纪录片旁白、传记与人生思考",
    ),
]


class VoiceProfileManager:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or VOICES_DIR
        self.audio_dir = self.storage_dir / "audio"
        self.profiles_file = self.storage_dir / "profiles.json"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._custom_profiles: Dict[str, VoiceProfile] = {}
        self._load()

    def _load(self) -> None:
        if self.profiles_file.is_file():
            try:
                data = json.loads(self.profiles_file.read_text(encoding="utf-8"))
                for item in data:
                    vp = VoiceProfile(**item)
                    self._custom_profiles[vp.voice_id] = vp
            except Exception:
                logger.exception("无法加载音色配置文件 %s", self.profiles_file)

    def _save(self) -> None:
        data = [vp.model_dump() for vp in self._custom_profiles.values()]
        temp = self.profiles_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.profiles_file)

    def list_voices(self) -> List[VoiceProfile]:
        """返回全部可用音色列表（预设 + 自定义克隆）"""
        return list(PRESET_VOICES) + list(self._custom_profiles.values())

    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        for p in PRESET_VOICES:
            if p.voice_id == voice_id:
                return p
        return self._custom_profiles.get(voice_id)

    def register_clone_voice(
        self,
        name: str,
        audio_source_path: str | Path,
        prompt_text: str = "",
        gender: str = "male",
        fallback_voice: str = DEFAULT_TTS_VOICE,
        description: str = "",
    ) -> VoiceProfile:
        """
        注册新的克隆音色：
        将参考音频持久化至 audio 目录，并保存 profile。
        """
        voice_id = f"clone_{uuid.uuid4().hex[:8]}"
        src = Path(audio_source_path)
        ext = src.suffix or ".wav"
        dest_filename = f"{voice_id}{ext}"
        dest_path = self.audio_dir / dest_filename
        shutil.copyfile(src, dest_path)

        profile = VoiceProfile(
            voice_id=voice_id,
            name=name,
            gender=gender,
            provider="cosyvoice",
            description=description or f"基于《{src.name}》定制的声音克隆音色",
            is_custom=True,
            reference_audio=str(dest_path.resolve()),
            reference_text=prompt_text,
            fallback_voice=fallback_voice,
        )
        self._custom_profiles[voice_id] = profile
        self._save()
        return profile

    def delete_clone_voice(self, voice_id: str) -> bool:
        if voice_id in self._custom_profiles:
            vp = self._custom_profiles.pop(voice_id)
            if vp.reference_audio and os.path.isfile(vp.reference_audio):
                try:
                    os.remove(vp.reference_audio)
                except OSError:
                    pass
            self._save()
            return True
        return False

    def get_adapter(self, voice_id: Optional[str] = None) -> BaseTTSAdapter:
        """根据音色 ID 获取对应的 TTS 适配器"""
        effective_id = voice_id or DEFAULT_TTS_VOICE
        profile = self.get_voice(effective_id)

        if profile and profile.provider == "cosyvoice":
            return CosyVoiceAdapter(
                reference_audio=profile.reference_audio,
                reference_text=profile.reference_text,
                fallback_voice=profile.fallback_voice,
            )
        # 默认返回 EdgeTTSAdapter
        return EdgeTTSAdapter(default_voice=effective_id)


voice_manager = VoiceProfileManager()
