"""持久化、限流且可取消的视频渲染任务管理器。"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config.settings import MAX_RENDER_JOBS, OUTPUT_DIR
from core.orchestrator import PipelineCancelled, VideoPipelineRunner

logger = logging.getLogger(__name__)
TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


class JobManager:
    def __init__(self, jobs_dir: Path | None = None, max_workers: int = MAX_RENDER_JOBS):
        self.jobs_dir = jobs_dir or (OUTPUT_DIR / "jobs")
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="render-job")
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._load_jobs()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _persist(self, job: Dict[str, Any]) -> None:
        path = self._job_path(job["job_id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _load_jobs(self) -> None:
        for path in self.jobs_dir.glob("job_*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("status") in {"queued", "running", "cancelling"}:
                    job["status"] = "interrupted"
                    job["error"] = "服务重启中断，可调用 retry 恢复任务"
                    job["updated_at"] = self._now()
                    self._persist(job)
                self._jobs[job["job_id"]] = job
            except (OSError, ValueError, KeyError):
                logger.exception("无法读取任务文件 %s", path)

    def create(self, payload: Dict[str, Any], checkpoint: Dict[str, Any] | None = None) -> Dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = self._now()
        job = {
            "job_id": job_id,
            "project_id": payload["project_id"],
            "status": "queued",
            "stage": "queued",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
            "result": None,
            "error": None,
            "logs": [],
            "checkpoint": checkpoint,
        }
        with self._lock:
            self._jobs[job_id] = job
            self._cancel_events[job_id] = threading.Event()
            self._persist(job)
        self._executor.submit(self._run, job_id)
        return self.public(job)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(changes)
            job["updated_at"] = self._now()
            self._persist(job)

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        event = self._cancel_events.setdefault(job_id, threading.Event())
        if event.is_set():
            self._update(job_id, status="cancelled", stage="cancelled")
            return
        self._update(job_id, status="running", stage="starting", error=None)

        def progress(stage: str) -> None:
            self._update(job_id, stage=stage)

        def checkpoint(state: Dict[str, Any]) -> None:
            serializable = {key: value for key, value in state.items() if key not in {"progress_callback", "cancel_event"}}
            self._update(job_id, checkpoint=serializable, logs=serializable.get("logs", []))

        payload = job["payload"]
        try:
            result = VideoPipelineRunner.run(
                script_data=payload["script_data"],
                voice=payload["voice"],
                bgm_type=payload["bgm_type"],
                tts_rate=payload.get("tts_rate"),
                tts_pitch=payload.get("tts_pitch"),
                project_id=payload["project_id"],
                progress_callback=progress,
                cancel_event=event,
                resume_state=job.get("checkpoint"),
                checkpoint_callback=checkpoint,
            )
            if event.is_set():
                raise PipelineCancelled("任务已取消")
            public_result = {
                "final_video_path": result.get("final_video_path"),
                "jianying_draft_path": result.get("jianying_draft_path"),
            }
            self._update(job_id, status="succeeded", stage="completed", result=public_result, logs=result.get("logs", []))
        except PipelineCancelled as exc:
            self._update(job_id, status="cancelled", stage="cancelled", error=str(exc))
        except Exception as exc:
            logger.exception("渲染任务 %s 失败", job_id)
            self._update(job_id, status="failed", stage="failed", error=str(exc))

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return self.public(job) if job else None

    def cancel(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job["status"] not in TERMINAL_STATES:
                self._cancel_events.setdefault(job_id, threading.Event()).set()
                job["status"] = "cancelling"
                job["updated_at"] = self._now()
                self._persist(job)
            return self.public(job)

    def retry(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old or old["status"] not in {"failed", "cancelled", "interrupted"}:
                return None
            payload = old["payload"]
            checkpoint = old.get("checkpoint")
        return self.create(payload, checkpoint=checkpoint)

    @staticmethod
    def public(job: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in job.items() if key not in {"payload", "checkpoint"}}


job_manager = JobManager()
