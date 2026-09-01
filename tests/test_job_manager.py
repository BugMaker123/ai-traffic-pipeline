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
