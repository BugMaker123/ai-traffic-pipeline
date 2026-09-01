from fastapi.testclient import TestClient

from web_studio import server


client = TestClient(server.app)


def test_create_job_validates_and_returns_202(monkeypatch):
    monkeypatch.setattr(
        server.job_manager,
        "create",
        lambda payload: {
            "job_id": "job_123",
            "project_id": payload["project_id"],
            "status": "queued",
            "stage": "queued",
        },
    )
    response = client.post(
        "/api/jobs",
        json={
            "title": "测试视频",
            "scenes": [{"scene_index": 1, "voiceover_text": "有效台词"}],
            "voice": "zh-CN-YunxiNeural",
            "bgm_type": "energetic",
        },
    )
    assert response.status_code == 202
    assert response.json()["job"]["status"] == "queued"


def test_open_draft_rejects_path_traversal():
    response = client.post("/api/projects/..%2F..%2FWindows/open-draft")
    assert response.status_code in {404, 422}


def test_render_rejects_too_many_scenes():
    response = client.post(
        "/api/jobs",
        json={
            "title": "过多分镜",
            "scenes": [{"scene_index": i + 1, "voiceover_text": "台词"} for i in range(13)],
        },
    )
    assert response.status_code == 422


def test_media_status_is_explicit():
    response = client.get("/api/media/status")
    assert response.status_code == 200
    assert isinstance(response.json()["pexels_configured"], bool)


def test_upload_scene_asset(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "ASSETS_OUTPUT_DIR", tmp_path)
    response = client.post(
        "/api/projects/proj_upload/scenes/1/asset?filename=cover.jpg",
        content=b"fake-image-content",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    assert response.json()["asset_type"] == "image"
    assert len(list(tmp_path.glob("proj_upload_upload_scene_1_*.jpg"))) == 1


def test_list_jobs_endpoint(monkeypatch):
    monkeypatch.setattr(server.job_manager, "list", lambda limit: [{"job_id": "job_1", "progress": 75}])
    response = client.get("/api/jobs?limit=8")
    assert response.status_code == 200
    assert response.json()["jobs"][0]["progress"] == 75
