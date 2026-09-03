"""
Phase 2 批量无人值守生产线单元测试 (Batch Processing Pipeline Tests)
测试项目：
1. JobManager 批量任务创建与持久化 (create_batch, _persist_batch)
2. 批次状态与进度实时聚合 (get_batch, public_batch)
3. 批次一键批量取消 (cancel_batch)
4. Web API 批次接口契约 (POST /api/batch_jobs, GET /api/batches/{batch_id})
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from web_studio.job_manager import JobManager
from web_studio.server import app


@pytest.fixture
def temp_job_manager(tmp_path):
    jm = JobManager(jobs_dir=tmp_path)
    yield jm
    jm.shutdown(wait=False)


def test_job_manager_create_and_get_batch(temp_job_manager):
    items = [
        {"topic": "自律与早起的真相"},
        {"topic": "为什么程序员越努力越焦虑"},
        {"topic": "黄金价格暴涨背后的逻辑"},
    ]
    common_options = {
        "voice": "zh-CN-YunxiNeural",
        "bgm_type": "energetic",
        "video_layout": "impact",
        "enable_karaoke": True,
        "subtitle_style": "impact_yellow",
    }

    batch = temp_job_manager.create_batch(items, common_options)
    assert batch["batch_id"].startswith("batch_")
    assert batch["total_count"] == 3
    assert len(batch["jobs"]) == 3
    assert batch["status"] in {"queued", "running"}

    # 验证获取批次
    fetched = temp_job_manager.get_batch(batch["batch_id"])
    assert fetched is not None
    assert fetched["batch_id"] == batch["batch_id"]
    assert fetched["total_count"] == 3

    # 验证子任务关联
    for job in fetched["jobs"]:
        assert job["batch_id"] == batch["batch_id"]
        assert job["status"] in {"queued", "running", "succeeded", "failed"}


def test_job_manager_cancel_batch(temp_job_manager):
    items = [
        {"topic": "选题A"},
        {"topic": "选题B"},
    ]
    batch = temp_job_manager.create_batch(items, {"voice": "zh-CN-YunxiNeural"})
    batch_id = batch["batch_id"]

    cancelled = temp_job_manager.cancel_batch(batch_id)
    assert cancelled is not None
    assert cancelled["batch_id"] == batch_id
    # 子任务状态应进入 cancelling 或 cancelled
    for job in cancelled["jobs"]:
        assert job["status"] in {"cancelling", "cancelled", "succeeded", "failed"}


def test_batch_api_endpoints():
    client = TestClient(app)

    # 1. 提交批量任务
    resp = client.post("/api/batch_jobs", json={
        "topics": ["热点选题一", "热点选题二"],
        "voice": "zh-CN-YunxiNeural",
        "bgm_type": "energetic",
        "video_layout": "impact",
        "enable_karaoke": True,
        "subtitle_style": "impact_yellow",
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data["success"] is True
    batch_id = data["batch"]["batch_id"]
    assert batch_id.startswith("batch_")
    assert data["batch"]["total_count"] == 2

    # 2. 查询批次状态
    resp_get = client.get(f"/api/batches/{batch_id}")
    assert resp_get.status_code == 200
    batch_detail = resp_get.json()["batch"]
    assert batch_detail["batch_id"] == batch_id
    assert len(batch_detail["jobs"]) == 2

    # 3. 批次列表查询
    resp_list = client.get("/api/batches")
    assert resp_list.status_code == 200
    batches = resp_list.json()["batches"]
    assert any(b["batch_id"] == batch_id for b in batches)

    # 4. 取消批次
    resp_cancel = client.post(f"/api/batches/{batch_id}/cancel")
    assert resp_cancel.status_code == 202
    assert resp_cancel.json()["success"] is True


def test_batch_api_validation_error():
    client = TestClient(app)
    # 空选题报错
    resp = client.post("/api/batch_jobs", json={"topics": []})
    assert resp.status_code == 400
