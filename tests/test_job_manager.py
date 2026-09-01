import threading

from web_studio.job_manager import JobManager


def test_job_persistence_and_restart_recovery(tmp_path):
    manager = JobManager(tmp_path, max_workers=1)
    job = {
        "job_id": "job_deadbeef0000",
        "project_id": "proj_test",
        "status": "running",
        "stage": "media_sourcing",
        "payload": {},
    }
    job.update(created_at=manager._now(), updated_at=manager._now(), result=None, error=None, logs=[])
    manager._jobs[job["job_id"]] = job
    manager._persist(job)

    recovered = JobManager(tmp_path, max_workers=1).get(job["job_id"])
    assert recovered["status"] == "interrupted"
    assert "可调用 retry" in recovered["error"]


def test_cancel_unknown_job_returns_none(tmp_path):
    assert JobManager(tmp_path, max_workers=1).cancel("job_missing") is None


def test_job_list_restart_and_progress_metadata(tmp_path, monkeypatch):
    manager = JobManager(tmp_path, max_workers=1)
    payload = {"project_id": "proj_test", "script_data": {}, "voice": "voice", "bgm_type": "chill"}
    manager._jobs["job_failed00001"] = {
        "job_id": "job_failed00001", "project_id": "proj_test", "status": "failed", "stage": "failed",
        "payload": payload, "checkpoint": None, "created_at": manager._now(), "updated_at": manager._now(),
        "started_at": manager._now(), "finished_at": manager._now(), "progress": 100,
        "result": None, "error": "boom", "logs": [],
    }
    monkeypatch.setattr(manager._executor, "submit", lambda *args, **kwargs: None)
    restarted = manager.restart("job_failed00001")
    assert restarted["status"] == "queued"
    assert next(job for job in manager.list() if job["job_id"] == restarted["job_id"])["progress"] == 0


def test_resume_interrupted_submits_from_checkpoint(tmp_path, monkeypatch):
    manager = JobManager(tmp_path, max_workers=1)
    manager._jobs["job_interrupted"] = {
        "job_id": "job_interrupted", "project_id": "proj_test", "status": "interrupted", "stage": "media_sourcing",
        "payload": {}, "checkpoint": {"status": "audio_ready"}, "created_at": manager._now(),
        "updated_at": manager._now(), "result": None, "error": "restart", "logs": [],
    }
    submitted = []
    monkeypatch.setattr(manager._executor, "submit", lambda fn, job_id: submitted.append(job_id))
    assert manager.resume_interrupted() == 1
    assert submitted == ["job_interrupted"]
    assert manager.get("job_interrupted")["status"] == "queued"
