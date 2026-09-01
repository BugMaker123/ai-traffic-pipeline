import asyncio
import json

from audio import tts_engine
from writers import script_generator
from media.pexels_client import PexelsMediaClient


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
