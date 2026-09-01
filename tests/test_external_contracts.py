import asyncio
import json

from audio import tts_engine
from writers import script_generator
from media.pexels_client import PexelsMediaClient


def test_temporal_claim_guard_rejects_unsupported_product_facts():
    script = {
        "title": "苹果涨价",
        "scenes": [{"voiceover_text": "2023年苹果砍掉iPhone 14 Plus和Apple Watch Series 3。"}],
    }
    claims = script_generator.ScriptGenerator._unsupported_temporal_claims(script, "苹果涨价")
    assert "2023年" in claims
    assert any("iPhone" in claim for claim in claims)


def test_temporal_claim_guard_accepts_claim_present_in_source():
    script = {"scenes": [{"voiceover_text": "消息提到iPhone 17。"}]}
    assert script_generator.ScriptGenerator._unsupported_temporal_claims(script, "来源：iPhone 17") == []


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "title": "Mock 标题",
                        "topic_summary": "Mock 概要",
                        "scenes": [{
                            "scene_index": 1,
                            "voiceover_text": "Mock 台词",
                            "visual_keywords": ["mock"],
                        }],
                    }, ensure_ascii=False)
                }
            }]
        }


def test_llm_response_contract_is_parsed(monkeypatch):
    monkeypatch.setattr(script_generator.requests, "post", lambda *args, **kwargs: FakeResponse())
    generator = script_generator.ScriptGenerator(api_key="test-key", base_url="https://mock.invalid", model="gpt-mock")
    result = generator.generate_script("测试", project_id="proj_mock")
    assert result.project_id == "proj_mock"
    assert result.scenes[0].voiceover_text == "Mock 台词"


def test_tts_stream_contract_is_parsed(monkeypatch, tmp_path):
    class FakeCommunicate:
        def __init__(self, **kwargs):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"mock-audio"}
            yield {"type": "WordBoundary", "offset": 0, "duration": 10_000_000, "text": "测试"}

    monkeypatch.setattr(tts_engine.edge_tts, "Communicate", FakeCommunicate)
    monkeypatch.setattr(tts_engine, "AUDIO_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(tts_engine, "get_audio_file_duration", lambda _path: 0.0)
    result = asyncio.run(tts_engine.TTSEngine().generate_speech_with_timestamps("测试", "mock.mp3"))
    assert (tmp_path / "mock.mp3").read_bytes() == b"mock-audio"
    assert result["duration"] == 1.0
    assert result["word_timestamps"][0]["text"] == "测试"


def test_tts_network_failure_falls_back_to_silent_audio(monkeypatch, tmp_path):
    class FailingCommunicate:
        def __init__(self, **kwargs):
            pass

        async def stream(self):
            raise OSError("Cannot connect to host speech.platform.bing.com")
            yield

    monkeypatch.setattr(tts_engine.edge_tts, "Communicate", FailingCommunicate)
    monkeypatch.setattr(tts_engine, "AUDIO_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(tts_engine, "TTS_RETRY_ATTEMPTS", 1)
    monkeypatch.setattr(tts_engine, "TTS_FALLBACK_SILENCE", True)

    result = asyncio.run(tts_engine.TTSEngine().generate_speech_with_timestamps("测试失败兜底", "fallback.mp3"))

    assert (tmp_path / "fallback.mp3").exists()
    assert result["tts_fallback"] == "silent"
    assert result["duration"] > 0
    assert result["word_timestamps"][0]["text"] == "测"


def test_pexels_photo_fallback_contract(monkeypatch, tmp_path):
    class Response:
        def __init__(self, payload=None, content=b""):
            self._payload, self.content, self.status_code = payload or {}, content, 200
        def json(self): return self._payload
        def raise_for_status(self): return None

    client = PexelsMediaClient(api_key="mock-key")
    responses = [
        Response({"videos": []}),
        Response({"photos": [{"src": {"portrait": "https://mock/photo.jpg"}, "photographer": "Mock"}]}),
        Response(content=b"x" * 25_000),
    ]
    monkeypatch.setattr(client.session, "get", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr("media.pexels_client.ASSETS_OUTPUT_DIR", tmp_path)
    result = client._search_pexels("office", 1, "proj_mock")
    assert result["source"] == "pexels_photo"
    assert (tmp_path / "proj_mock_asset_scene_1.jpg").exists()
