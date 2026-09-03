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
STAGE_PROGRESS = {
    "queued": 0,
    "starting": 3,
    "topic_mining": 8,
    "script_writing": 18,
    "audio_and_subtitles": 38,
    "media_sourcing": 62,
    "video_compositing": 82,
    "completed": 100,
    "failed": 100,
    "cancelled": 100,
}


class JobManager:
    def __init__(self, jobs_dir: Path | None = None, max_workers: int = MAX_RENDER_JOBS):
        self.jobs_dir = jobs_dir or (OUTPUT_DIR / "jobs")
        self.batches_dir = self.jobs_dir / "batches"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.batches_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="render-job")
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._batches: Dict[str, Dict[str, Any]] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._load_jobs()
        self._load_batches()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _batch_path(self, batch_id: str) -> Path:
        return self.batches_dir / f"{batch_id}.json"

    def _persist(self, job: Dict[str, Any]) -> None:
        path = self._job_path(job["job_id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _persist_batch(self, batch: Dict[str, Any]) -> None:
        path = self._batch_path(batch["batch_id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
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

    def _load_batches(self) -> None:
        for path in self.batches_dir.glob("batch_*.json"):
            try:
                batch = json.loads(path.read_text(encoding="utf-8"))
                self._batches[batch["batch_id"]] = batch
            except (OSError, ValueError, KeyError):
                logger.exception("无法读取批次文件 %s", path)

    def create(
        self,
        payload: Dict[str, Any],
        checkpoint: Dict[str, Any] | None = None,
        batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = self._now()
        effective_batch_id = batch_id or payload.get("batch_id")
        topic_title = payload.get("topic") or (payload.get("script_data") or {}).get("title") or payload.get("project_id")
        job = {
            "job_id": job_id,
            "project_id": payload["project_id"],
            "title": topic_title,
            "batch_id": effective_batch_id,
            "status": "queued",
            "stage": "queued",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
            "result": None,
            "error": None,
            "logs": [],
            "stage_started_at": now,
            "stage_durations": {},
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
            if "stage" in changes and changes["stage"] != job.get("stage"):
                now_dt = datetime.now(timezone.utc)
                started = job.get("stage_started_at")
                if started:
                    try:
                        elapsed = max(0.0, (now_dt - datetime.fromisoformat(started)).total_seconds())
                        job.setdefault("stage_durations", {})[job.get("stage", "unknown")] = round(elapsed, 2)
                    except ValueError:
                        pass
                job["stage_started_at"] = now_dt.isoformat()
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
                topic=payload.get("topic", ""),
                script_data=payload.get("script_data"),
                voice=payload.get("voice"),
                bgm_type=payload.get("bgm_type", "energetic"),
                tts_rate=payload.get("tts_rate"),
                tts_pitch=payload.get("tts_pitch"),
                video_layout=payload.get("video_layout", "impact"),
                enable_karaoke=payload.get("enable_karaoke", True),
                subtitle_style=payload.get("subtitle_style", "impact_yellow"),
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
            final_title = (result.get("script_data") or {}).get("title")
            updates: Dict[str, Any] = {
                "status": "succeeded",
                "stage": "completed",
                "result": public_result,
                "logs": result.get("logs", []),
            }
            if final_title:
                updates["title"] = final_title
            self._update(job_id, **updates)
        except PipelineCancelled as exc:
            self._update(job_id, status="cancelled", stage="cancelled", error=str(exc))
        except Exception as exc:
            if "interpreter shutdown" not in str(exc).lower():
                logger.exception("渲染任务 %s 失败", job_id)
            try:
                self._update(job_id, status="failed", stage="failed", error=str(exc))
            except Exception:
                pass

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return self.public(job) if job else None

    def list(self, *, status: str | None = None, limit: int = 50) -> list[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
            if status:
                jobs = [job for job in jobs if job.get("status") == status]
            jobs.sort(key=lambda job: job.get("created_at", ""), reverse=True)
            return [self.public(job) for job in jobs[: max(1, min(limit, 200))]]

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

    def create_batch(
        self,
        items: list[Dict[str, Any]],
        common_options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """创建批量渲染任务并返回聚合批次信息"""
        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        now = self._now()
        job_ids = []

        for idx, item in enumerate(items):
            topic = str(item.get("topic", "")).strip()
            project_id = item.get("project_id") or f"proj_batch_{uuid.uuid4().hex[:6]}"
            payload = {
                "project_id": project_id,
                "topic": topic,
                "script_data": item.get("script_data"),
                "voice": common_options.get("voice"),
                "bgm_type": common_options.get("bgm_type", "energetic"),
                "video_layout": common_options.get("video_layout", "impact"),
                "enable_karaoke": common_options.get("enable_karaoke", True),
                "subtitle_style": common_options.get("subtitle_style", "impact_yellow"),
                "tts_rate": common_options.get("tts_rate"),
                "tts_pitch": common_options.get("tts_pitch"),
                "batch_id": batch_id,
                "batch_index": idx + 1,
            }
            job = self.create(payload, batch_id=batch_id)
            job_ids.append(job["job_id"])

        batch_info = {
            "batch_id": batch_id,
            "created_at": now,
            "updated_at": now,
            "total_count": len(items),
            "job_ids": job_ids,
            "common_options": common_options,
        }
        with self._lock:
            self._batches[batch_id] = batch_info
            self._persist_batch(batch_info)

        return self.public_batch(batch_info)

    def public_batch(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """计算并返回批次的聚合状态与子任务详情"""
        job_ids = batch.get("job_ids", [])
        jobs = []
        statuses = []
        total_progress = 0

        for jid in job_ids:
            job = self.get(jid)
            if job:
                jobs.append(job)
                statuses.append(job.get("status", "unknown"))
                total_progress += job.get("progress", 0)
            else:
                statuses.append("unknown")

        total = len(job_ids) or 1
        avg_progress = round(total_progress / total, 1)

        succeeded = statuses.count("succeeded")
        failed = statuses.count("failed")
        cancelled = statuses.count("cancelled") + statuses.count("cancelling")
        running = statuses.count("running")
        queued = statuses.count("queued") + statuses.count("interrupted")

        if succeeded == total:
            overall_status = "succeeded"
        elif cancelled == total:
            overall_status = "cancelled"
        elif succeeded + failed + cancelled == total:
            overall_status = "completed_with_errors" if failed > 0 else "succeeded"
        elif running > 0:
            overall_status = "running"
        else:
            overall_status = "queued"

        return {
            "batch_id": batch["batch_id"],
            "created_at": batch.get("created_at"),
            "updated_at": batch.get("updated_at"),
            "total_count": len(job_ids),
            "succeeded_count": succeeded,
            "failed_count": failed,
            "cancelled_count": cancelled,
            "running_count": running,
            "queued_count": queued,
            "status": overall_status,
            "progress": avg_progress,
            "jobs": jobs,
        }

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(batch_id)
            return self.public_batch(batch) if batch else None

    def list_batches(self, limit: int = 20) -> list[Dict[str, Any]]:
        with self._lock:
            batches = list(self._batches.values())
            batches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
            return [self.public_batch(b) for b in batches[: max(1, min(limit, 100))]]

    def cancel_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return None
            for jid in batch.get("job_ids", []):
                self.cancel(jid)
        return self.get_batch(batch_id)

    @staticmethod
    def public(job: Dict[str, Any]) -> Dict[str, Any]:
        result = {key: value for key, value in job.items() if key not in {"payload", "checkpoint"}}
        result["progress"] = STAGE_PROGRESS.get(str(job.get("stage")), 0)
        return result


job_manager = JobManager()
