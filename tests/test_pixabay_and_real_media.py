"""
测试 Pixabay 4K/1080P 实拍视频/摄影引擎与多源去 AI 塑料感素材检索管线
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from media.pixabay_client import PixabayMediaClient
from media.pexels_client import PexelsMediaClient, COMMERCIAL_QUERY_MAP


class MockResponse:
    def __init__(self, json_data: dict, status_code: int = 200, content: bytes = b""):
        self._json_data = json_data
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._json_data


def test_pixabay_client_unconfigured():
    client = PixabayMediaClient(api_key="")
    assert not client.is_configured
    assert client.search_video("basketball", 1, "test_proj") is None
    assert client.search_photo("basketball", 1, "test_proj") is None


def test_pixabay_client_search_video_success(monkeypatch, tmp_path):
    monkeypatch.setattr("media.pixabay_client.ASSETS_OUTPUT_DIR", tmp_path)
    client = PixabayMediaClient(api_key="mock_pixabay_key")
    assert client.is_configured

    fake_api_data = {
        "totalHits": 1,
        "hits": [
            {
                "id": 101,
                "duration": 12,
                "videos": {
                    "large": {"url": "https://example.com/video_1080p.mp4", "width": 1080, "height": 1920},
                    "medium": {"url": "https://example.com/video_720p.mp4", "width": 720, "height": 1280},
                },
            }
        ],
    }

    def mock_get(url, *args, **kwargs):
        if "videos" in url:
            return MockResponse(fake_api_data, 200)
        # Mock 视频二进制下载 (需大于 100KB)
        return MockResponse({}, 200, content=b"\x00" * 150_000)

    monkeypatch.setattr(client.session, "get", mock_get)

    res = client.search_video("basketball match", 1, "proj_test")
    assert res is not None
    assert res["asset_type"] == "video"
    assert res["source"] == "pixabay_video"
    assert Path(res["asset_file"]).exists()


def test_pixabay_client_search_photo_success(monkeypatch, tmp_path):
    monkeypatch.setattr("media.pixabay_client.ASSETS_OUTPUT_DIR", tmp_path)
    client = PixabayMediaClient(api_key="mock_pixabay_key")

    fake_photo_data = {
        "totalHits": 1,
        "hits": [
            {
                "id": 202,
                "largeImageURL": "https://example.com/photo_large.jpg",
                "user": "pro_photographer",
            }
        ],
    }

    def mock_get(url, *args, **kwargs):
        if "api/" in url and "videos" not in url:
            return MockResponse(fake_photo_data, 200)
        # Mock 图片二进制下载
        return MockResponse({}, 200, content=b"\xff\xd8\xff" + b"\x00" * 20_000)

    monkeypatch.setattr(client.session, "get", mock_get)

    res = client.search_photo("basketball", 1, "proj_test")
    assert res is not None
    assert res["asset_type"] == "image"
    assert res["source"] == "pixabay_photo"
    assert res["photographer"] == "pro_photographer"
    assert Path(res["asset_file"]).exists()


def test_commercial_query_normalization():
    client = PexelsMediaClient()

    # 1. 验证体育/篮球映射
    q1 = client._normalize_commercial_query(["女篮世界杯夺冠难度"], "women basketball court", "真实难度远超想象")
    assert "women basketball" in q1

    # 2. 验证财经/股票/黄金映射
    q2 = client._normalize_commercial_query(["黄金暴涨背后的逻辑"], None, "算清楚这笔账")
    assert "gold bars" in q2

    # 3. 验证自律/晨跑映射
    q3 = client._normalize_commercial_query(["自律改变人生"], None, "为什么越自律越自由")
    assert "morning routine" in q3 or "workout" in q3

    # 4. 验证科技/芯片映射
    q4 = client._normalize_commercial_query(["国产芯片突破封锁"], None, "硬件算力升级")
    assert "semiconductor" in q4 or "microchip" in q4


def test_fetch_scene_asset_prioritizes_real_video(monkeypatch, tmp_path):
    """验证分镜获取素材优先使用真实视频，彻底消除 AI 塑料感"""
    monkeypatch.setattr("media.pexels_client.ASSETS_OUTPUT_DIR", tmp_path)
    client = PexelsMediaClient(api_key="mock_key")

    mock_video_res = {
        "asset_file": str(tmp_path / "mock_video.mp4"),
        "asset_type": "video",
        "source": "pexels",
        "keyword": "basketball match",
        "duration": 5.0,
    }
    (tmp_path / "mock_video.mp4").write_bytes(b"\x00" * 1000)

    monkeypatch.setattr(client, "_search_pexels", lambda *args, **kwargs: mock_video_res)

    res = client.fetch_scene_asset(
        keywords=["女篮世界杯"],
        scene_idx=1,
        project_id="proj_real_test",
        prefer_video=True,
    )
    assert res["asset_type"] == "video"
    assert res["source"] == "pexels"


def test_scifi_strategy_query_and_core_extraction():
    """验证三体/宇宙/博弈商业词映射与高频视频核心词提炼"""
    client = PexelsMediaClient()

    # 三体 / 宇宙
    q1 = client._normalize_commercial_query(["三体执剑人的抉择"], None, "罗辑面对黑暗森林")
    assert "space" in q1 or "universe" in q1
    core1 = client._extract_core_video_query(q1)
    assert core1 in ["universe", "space", "galaxy"]

    # 国际象棋 / 博弈
    q2 = client._normalize_commercial_query(["终局博弈与危机"], None, "按纽被按下的那一瞬间")
    assert "chess" in q2 or "strategy" in q2 or "button" in q2
    core2 = client._extract_core_video_query(q2)
    assert core2 in ["chess", "pressing button"]


def test_curated_photo_strict_deduplication(monkeypatch, tmp_path):
    """验证同一项目内连续获取精选大片时，严格消除重复，各镜头素材独一无二"""
    monkeypatch.setattr("media.pexels_client.ASSETS_OUTPUT_DIR", tmp_path)
    client = PexelsMediaClient()

    def mock_download(url, *args, **kwargs):
        return MockResponse({}, 200, content=b"\xff\xd8\xff" + b"\x00" * 15_000)

    monkeypatch.setattr(client.session, "get", mock_download)

    project_id = "test_dedup_proj"
    res1 = client._match_and_download_curated_photo("space galaxy", scene_idx=1, project_id=project_id)
    res2 = client._match_and_download_curated_photo("space galaxy", scene_idx=2, project_id=project_id)
    res3 = client._match_and_download_curated_photo("space galaxy", scene_idx=3, project_id=project_id)

    assert res1 is not None
    assert res2 is not None
    assert res3 is not None
    # 验证已用集合包含了 3 个不同图片 ID
    used_set = client._used_assets_by_project[project_id]
    assert len(used_set) == 3


def test_sfx_manager_generation():
    """验证转场破风 (whoosh)、重音顿挫 (hit)、金句强调 (ding) 均能程序化生成高质量音频"""
    from media.sfx_manager import SFXManager

    whoosh_p = SFXManager.get_whoosh()
    ding_p = SFXManager.get_ding()
    hit_p = SFXManager.get_hit()
    pop_p = SFXManager.get_pop()

    for p in [whoosh_p, ding_p, hit_p, pop_p]:
        path = Path(p)
        assert path.exists()
        assert path.stat().st_size > 1000

