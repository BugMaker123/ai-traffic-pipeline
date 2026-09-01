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


def test_list_jobs_is_sorted_and_exposes_progress(tmp_path):
    manager = JobManager(tmp_path, max_workers=1)
    for index, stage in enumerate(("queued", "media_sourcing")):
        job = {
            "job_id": f"job_test{index}", "project_id": f"proj_{index}", "status": "running",
            "stage": stage, "created_at": f"2026-01-0{index + 1}T00:00:00+00:00",
            "updated_at": manager._now(), "payload": {}, "result": None, "error": None, "logs": [],
        }
        manager._jobs[job["job_id"]] = job
    jobs = manager.list(limit=10)
    assert jobs[0]["job_id"] == "job_test1"
    assert jobs[0]["progress"] == 62
