"""
Phase 3 声音克隆与音色定制、社媒短视频内容解构单元测试
测试项目：
1. EdgeTTSAdapter 与 CosyVoiceAdapter 平滑降级测试
2. VoiceProfileManager 音色注册与持久化测试
3. SocialVideoExtractor 链接清理、平台识别与文本提取测试
4. Web API 接口测试: /api/voices, /api/voices/clone, /api/extract_video
"""
import pytest
import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
import io

from audio.adapters import EdgeTTSAdapter, CosyVoiceAdapter
from audio.voice_manager import VoiceProfileManager
from extractors.video_extractor import SocialVideoExtractor
from web_studio.server import app


@pytest.fixture
def temp_voice_manager(tmp_path):
    vm = VoiceProfileManager(storage_dir=tmp_path)
    return vm


def test_edge_tts_adapter_silent_fallback(tmp_path):
    adapter = EdgeTTSAdapter()
    out_file = tmp_path / "test_edge.mp3"
    # 模拟网络不可达触发兜底
    class FailingCommunicate:
        def __init__(self, **kwargs):
            pass
        async def stream(self):
            raise OSError("Mock connection error")
            yield

    import audio.adapters as adapters_mod
    orig_communicate = adapters_mod.edge_tts.Communicate
    adapters_mod.edge_tts.Communicate = FailingCommunicate
    try:
        res = asyncio.run(adapter.synthesize(
            text="测试EdgeTTS合成兜底逻辑",
            output_path=out_file,
            voice="zh-CN-YunxiNeural"
        ))
        assert out_file.exists()
        assert res["tts_fallback"] == "silent"
        assert res["duration"] > 0
        assert len(res["word_timestamps"]) > 0
    finally:
        adapters_mod.edge_tts.Communicate = orig_communicate


def test_cosyvoice_offline_graceful_fallback(tmp_path):
    """当 CosyVoice 本地/远程服务端口离线时，自动平滑降级至 Edge-TTS 备用音色"""
    # 构造不可达的本地端口
    cosy_adapter = CosyVoiceAdapter(
        api_url="http://127.0.0.1:59999/api/tts_offline",
        timeout=0.2,
        fallback_voice="zh-CN-YunxiNeural"
    )
    out_file = tmp_path / "test_cosy_fallback.mp3"

    # 模拟 EdgeTTSAdapter 成功
    class FakeEdgeAdapter(EdgeTTSAdapter):
        async def synthesize(self, text, output_path, **kwargs):
            output_path.write_bytes(b"mock-edge-audio")
            return {
                "audio_path": str(output_path),
                "duration": 2.5,
                "word_timestamps": [{"text": "测", "start": 0.0, "end": 0.5, "duration": 0.5}],
                "text": text,
                "voice": kwargs.get("voice", "zh-CN-YunxiNeural"),
                "tts_engine": "edge_tts",
            }

    cosy_adapter.fallback_adapter = FakeEdgeAdapter()

    res = asyncio.run(cosy_adapter.synthesize(
        text="测试声音克隆离线降级",
        output_path=out_file,
        voice="custom_clone_voice"
    ))

    assert out_file.exists()
    assert res["tts_fallback"] == "cosyvoice_to_edge"
    assert res["original_voice"] == "custom_clone_voice"
    assert res["voice"] == "zh-CN-YunxiNeural"


def test_voice_profile_manager(temp_voice_manager, tmp_path):
    # 1. 预设列表验证
    presets = temp_voice_manager.list_voices()
    assert len(presets) >= 6
    assert any(p.voice_id == "zh-CN-YunxiNeural" for p in presets)

    # 2. 注册克隆音色
    sample_wav = tmp_path / "sample_voice.wav"
    sample_wav.write_bytes(b"RIFFmockwavdata")

    cloned = temp_voice_manager.register_clone_voice(
        name="科技老张",
        audio_source_path=sample_wav,
        prompt_text="大家好我是老张，今天聊聊AI",
        gender="male",
        description="硬核科技自媒体声音克隆"
    )

    assert cloned.voice_id.startswith("clone_")
    assert cloned.name == "科技老张"
    assert cloned.is_custom is True
    assert Path(cloned.reference_audio).is_file()

    # 3. 重新加载验证持久化
    reloaded_vm = VoiceProfileManager(storage_dir=temp_voice_manager.storage_dir)
    fetched = reloaded_vm.get_voice(cloned.voice_id)
    assert fetched is not None
    assert fetched.name == "科技老张"

    # 4. 删除音色
    assert reloaded_vm.delete_clone_voice(cloned.voice_id) is True
    assert reloaded_vm.get_voice(cloned.voice_id) is None


def test_social_video_extractor():
    extractor = SocialVideoExtractor()

    # 测试抖音短链与附带中文分享文本分离
    raw_douyin = "7.30 v@p.lu 07/04 为什么高手都在悄悄戒掉情绪？ https://v.douyin.com/iJ8x999/ 复制此链接打开抖音"
    url, title = extractor.extract_url_and_surrounding_text(raw_douyin)
    assert url == "https://v.douyin.com/iJ8x999/"
    assert "为什么高手都在悄悄戒掉情绪" in title

    # 测试平台识别
    assert extractor.detect_platform("https://v.douyin.com/abc") == "抖音"
    assert extractor.detect_platform("https://www.bilibili.com/video/BV1xx") == "B站"
    assert extractor.detect_platform("https://www.xiaohongshu.com/discovery/item/123") == "小红书"

    # 核心解构方法测试
    info = extractor.extract(raw_douyin)
    assert info["success"] is True
    assert info["platform"] == "抖音"
    assert "为什么高手都在悄悄戒掉情绪" in info["title"]
    assert len(info["transcript"]) > 20


def test_web_studio_voice_and_extract_api():
    client = TestClient(app)

    # 1. 查询音色列表
    resp_voices = client.get("/api/voices")
    assert resp_voices.status_code == 200
    voices = resp_voices.json()["voices"]
    assert len(voices) >= 6
    assert any(v["id"] == "zh-CN-YunxiNeural" for v in voices)

    # 2. 上传参考音频创建克隆音色
    fake_audio = io.BytesIO(b"RIFFfakeaudiobytes")
    resp_clone = client.post(
        "/api/voices/clone",
        data={
            "name": "测试克隆主播",
            "gender": "female",
            "prompt_text": "测试参考文本",
            "description": "单元测试音色",
        },
        files={"file": ("sample.wav", fake_audio, "audio/wav")}
    )
    assert resp_clone.status_code == 201
    clone_data = resp_clone.json()
    assert clone_data["success"] is True
    cloned_id = clone_data["voice"]["voice_id"]
    assert cloned_id.startswith("clone_")

    # 3. 验证音色列表包含新克隆音色
    resp_voices_updated = client.get("/api/voices")
    updated_voices = resp_voices_updated.json()["voices"]
    assert any(v["id"] == cloned_id for v in updated_voices)

    # 4. 提取视频内容 API (POST /api/extract_video)
    resp_extract = client.post(
        "/api/extract_video",
        json={"url_or_text": "【科技趋势】大模型最新突破 https://v.douyin.com/demo123/ 复制打开"}
    )
    assert resp_extract.status_code == 200
    extract_res = resp_extract.json()
    assert extract_res["success"] is True
    assert "大模型" in extract_res["title"]
    assert len(extract_res["transcript"]) > 0

    # 5. 清理删除测试音色
    resp_del = client.delete(f"/api/voices/{cloned_id}")
    assert resp_del.status_code == 200
