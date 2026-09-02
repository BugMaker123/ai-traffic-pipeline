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


def test_tasks_page_and_global_job_list(monkeypatch):
    monkeypatch.setattr(server.job_manager, "list", lambda **kwargs: [])
    assert client.get("/tasks").status_code == 200
    response = client.get("/api/jobs")
    assert response.status_code == 200
    assert response.json()["jobs"] == []


def test_upload_asset_image_and_video():
    # Test uploading image
    fake_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
    response = client.post(
        "/api/upload_asset",
        files={"file": ("test_scene.jpg", fake_img, "image/jpeg")},
        data={"scene_index": "1", "project_id": "test_proj"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["asset_type"] == "image"
    assert "/output/video_assets/" in data["asset_url"]

    # Test uploading video clip
    fake_video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
    response_vid = client.post(
        "/api/upload_asset",
        files={"file": ("clip_scene.mp4", fake_video, "video/mp4")},
        data={"scene_index": "2", "project_id": "test_proj"},
    )
    assert response_vid.status_code == 200
    vid_data = response_vid.json()
    assert vid_data["success"] is True
    assert vid_data["asset_type"] == "video"

