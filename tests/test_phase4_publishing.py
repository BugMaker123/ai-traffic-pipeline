"""
Phase 4 自媒体多平台自动化发布与智能抗查重微混淆单元测试
测试项目：
1. AntiDuplicateProcessor 视频微裁切、变速与数字指纹打散测试
2. 各自媒体平台 Publisher (抖音/B站/小红书/视频号) 接口与标签规范化测试
3. PublishManager 矩阵分发调度与历史记录归档测试
4. Web Studio /api/publish 与 /api/publish/history 接口契约测试
"""
import pytest
import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
import numpy as np

from compositors.anti_duplicate import AntiDuplicateOptions, AntiDuplicateProcessor, calculate_file_hash
from publishers.base import BasePublisher
from publishers.douyin_publisher import DouyinPublisher
from publishers.bilibili_publisher import BilibiliPublisher
from publishers.xiaohongshu_publisher import XiaohongshuPublisher
from publishers.channels_publisher import ChannelsPublisher
from publishers.manager import PublishManager
from web_studio.server import app


@pytest.fixture
def sample_video_path(tmp_path):
    """使用 MoviePy 创建一个轻量 1 秒 720x1280 测试视频文件"""
    from moviepy import ColorClip
    video_file = tmp_path / "sample_test_video.mp4"
    clip = ColorClip(size=(720, 1280), color=(50, 100, 150), duration=1.0)
    clip.write_videofile(
        str(video_file),
        fps=15,
        codec="libx264",
        audio=False,
        logger=None
    )
    clip.close()
    return video_file


def test_anti_duplicate_processor(sample_video_path, tmp_path):
    """验证抗查重微混淆处理前后 MD5 彻底改变，且参数与指纹有效注入"""
    out_video = tmp_path / "antidup_result.mp4"
    opts = AntiDuplicateOptions(
        crop_percent=0.015,
        speed_factor=1.01,
        contrast_adjust=1.02,
        brightness_adjust=0.01,
        randomize=False,
        scrub_metadata=True
    )

    res = AntiDuplicateProcessor.process_video(
        input_video_path=sample_video_path,
        output_video_path=out_video,
        options=opts
    )

    assert res["success"] is True
    assert Path(res["processed_path"]).is_file()
    assert res["is_hash_different"] is True
    assert res["original_md5"] != res["processed_md5"]
    assert "fingerprint" in res["applied_params"]


def test_platform_publishers_and_tags_formatting(sample_video_path):
    """验证四大主流自媒体平台发布适配器与标签规范化逻辑"""
    raw_tags = ["深度思考", "#商业逻辑", " 认知思维  "]
    cleaned = BasePublisher.clean_tags(raw_tags)
    assert cleaned == ["#深度思考", "#商业逻辑", "#认知思维"]

    # 1. 抖音
    dy_pub = DouyinPublisher()
    dy_res = asyncio.run(dy_pub.publish(
        video_path=sample_video_path,
        title="如何戒掉情绪内耗",
        tags=raw_tags
    ))
    assert dy_res.platform == "douyin"
    assert dy_res.status in {"success", "draft_ready"}
    assert all(t.startswith("#") for t in dy_res.tags)

    # 2. B站 (去除 # 号规范)
    bili_pub = BilibiliPublisher()
    bili_res = asyncio.run(bili_pub.publish(
        video_path=sample_video_path,
        title="深度商业思维拆解",
        tags=raw_tags
    ))
    assert bili_res.platform == "bilibili"
    assert bili_res.status in {"success", "draft_ready"}
    assert all(not t.startswith("#") for t in bili_res.tags)

    # 3. 小红书 (标题上限 20 字截断与标签合并)
    xhs_pub = XiaohongshuPublisher()
    long_title = "这是一个超过二十个汉字长度的超级自媒体爆款长标题用于测试截断"
    xhs_res = asyncio.run(xhs_pub.publish(
        video_path=sample_video_path,
        title=long_title,
        tags=raw_tags
    ))
    assert xhs_res.platform == "xiaohongshu"
    assert len(xhs_res.title) <= 20

    # 4. 微信视频号
    wx_pub = ChannelsPublisher()
    wx_res = asyncio.run(wx_pub.publish(
        video_path=sample_video_path,
        title="认知破局指南",
        tags=raw_tags
    ))
    assert wx_res.platform == "channels"
    assert wx_res.status in {"success", "draft_ready"}


def test_publish_manager_orchestration(sample_video_path, tmp_path):
    """验证 PublishManager 统一调度多平台并发分发与历史归档"""
    mgr = PublishManager(logs_dir=tmp_path / "logs")
    platforms = mgr.list_supported_platforms()
    assert len(platforms) >= 4
    assert any(p["id"] == "douyin" for p in platforms)

    # 执行向 3 个平台分发（关闭微混淆以加速测试）
    record = asyncio.run(mgr.publish_to_platforms(
        video_path=sample_video_path,
        platforms=["douyin", "bilibili", "xiaohongshu"],
        title="单元测试矩阵分发",
        tags=["#测试", "#科技"],
        enable_anti_duplicate=False
    ))

    assert record["platforms_count"] == 3
    assert len(record["results"]) == 3
    assert record["batch_id"].startswith("matrix_")

    # 验证历史持久化与回读
    history = mgr.get_history()
    assert len(history) >= 1
    assert history[0]["batch_id"] == record["batch_id"]
    assert history[0]["title"] == "单元测试矩阵分发"


def test_web_studio_publish_api(sample_video_path):
    """测试 Web Studio 矩阵分发相关 HTTP API 契约"""
    client = TestClient(app)

    # 1. 获取平台列表
    resp_plat = client.get("/api/publish/platforms")
    assert resp_plat.status_code == 200
    platforms = resp_plat.json()["platforms"]
    assert len(platforms) >= 4

    # 2. 获取发布历史
    resp_hist = client.get("/api/publish/history")
    assert resp_hist.status_code == 200
    assert "history" in resp_hist.json()

    # 3. 提交矩阵发布请求（指向已存在的测试视频）
    resp_pub = client.post("/api/publish", json={
        "video_path": str(sample_video_path),
        "platforms": ["douyin", "channels"],
        "title": "API测试分发标题",
        "tags": ["#商业", "#认知"],
        "description": "这是测试文案描述",
        "enable_anti_duplicate": False  # 测试环境关闭微混淆以秒级返回
    })

    assert resp_pub.status_code == 200
    data = resp_pub.json()
    assert data["success"] is True
    rec = data["publish_record"]
    assert rec["platforms_count"] == 2
    assert rec["title"] == "API测试分发标题"

    # 4. 测试错误视频路径容错 404
    resp_err = client.post("/api/publish", json={
        "video_path": "output/final/not_exist_file_9999.mp4",
        "platforms": ["douyin"],
        "title": "不存在的视频"
    })
    assert resp_err.status_code == 404
