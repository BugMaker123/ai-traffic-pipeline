"""AI Traffic Pipeline Web Studio API。"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from audio.tts_engine import TTSEngine
from config.settings import ASSETS_OUTPUT_DIR, DEFAULT_TTS_PITCH, DEFAULT_TTS_VOICE, DRAFTS_OUTPUT_DIR, MAX_SCENES, OUTPUT_DIR, PEXELS_API_KEY, VOICE_PRESETS
from core.state import SceneItem, VideoProjectScript
from core.logging_config import configure_logging
from core.output_cleanup import cleanup_expired_outputs, cleanup_incomplete_outputs
from crawlers.hot_topics import CATEGORY_NAMES, HotTopicCrawler
from media.pexels_client import PexelsMediaClient
from web_studio.job_manager import job_manager
from writers.script_generator import DURATION_PRESETS, ScriptGenerator

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(cleanup_expired_outputs, dry_run=False)
    await asyncio.to_thread(cleanup_incomplete_outputs)
    job_manager.resume_interrupted()
    yield


app = FastAPI(title="AI Traffic Pipeline Web Studio", version="3.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PROJECT_ID_RE = re.compile(r"^(?:proj|test)_[a-zA-Z0-9_-]{1,48}$")
VoiceId = Literal[tuple(VOICE_PRESETS.values())]
BgmType = Literal["energetic", "suspense", "emotional", "chill"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScriptRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=500)
    style: Literal["干货科普", "幽默反转", "情感共鸣", "商业认知"] = "干货科普"
    duration_tier: Literal[tuple(DURATION_PRESETS.keys())] = "deep_60s"
    variants: int = Field(default=1, ge=1, le=3)


class RewriteSceneRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=1000)
    style: Literal["干货科普", "幽默反转", "情感共鸣", "商业认知"] = "干货科普"


class TTSPreviewRequest(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    voice: VoiceId = DEFAULT_TTS_VOICE
    rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")


class RenderSceneRequest(StrictModel):
    scene_index: int = Field(ge=1, le=MAX_SCENES)
    voiceover_text: str = Field(min_length=1, max_length=1000)
    visual_keywords: list[str] = Field(default_factory=list, max_length=8)
    caption_highlight: list[str] = Field(default_factory=list, max_length=12)
    transition: Literal["fade", "zoom_in", "slide_left"] = "zoom_in"
    asset_file: str | None = None
    asset_type: Literal["video", "image"] | None = None
    asset_locked: bool = False
    trim_start: float = Field(default=0, ge=0, le=600)
    playback_speed: float = Field(default=1, ge=0.25, le=4)
    crop_x: float = Field(default=0.5, ge=0, le=1)
    crop_y: float = Field(default=0.5, ge=0, le=1)


class RenderRequest(StrictModel):
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    scenes: list[RenderSceneRequest] = Field(min_length=1, max_length=MAX_SCENES)
    voice: VoiceId = DEFAULT_TTS_VOICE
    bgm_type: BgmType = "energetic"
    tts_rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    tts_pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")
    caption_template: Literal["impact", "clean", "news", "warm"] = "impact"

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str | None) -> str | None:
        if value is not None and not PROJECT_ID_RE.fullmatch(value):
            raise ValueError("project_id 格式无效")
        return value


@app.get("/", response_class=HTMLResponse)
async def serve_index() -> str:
    path = TEMPLATES_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="index.html not found")
    return path.read_text(encoding="utf-8")


@app.get("/api/trends")
async def get_trends(category: str = Query(default="all")):
    if category not in CATEGORY_NAMES:
        raise HTTPException(status_code=422, detail="未知热点分类")
    trends = await asyncio.to_thread(HotTopicCrawler.get_categorized_trends, category=category, limit=15)
    return {"success": True, "category": category, "trends": [item.model_dump() for item in trends]}


@app.get("/api/voices")
async def get_voices():
    return {"success": True, "voices": [{"id": value, "name": key} for key, value in VOICE_PRESETS.items()]}


@app.post("/api/generate_script")
async def generate_script(req: ScriptRequest):
    generator = ScriptGenerator()
    scripts = []
    for _ in range(req.variants):
        script = await asyncio.to_thread(generator.generate_script, req.topic, req.style, req.duration_tier)
        scripts.append(script.model_dump())
    return {"success": True, "script": scripts[0], "variants": scripts}


@app.post("/api/rewrite_scene")
async def rewrite_scene(req: RewriteSceneRequest):
    generator = ScriptGenerator()
    prompt = f"{req.topic}。只重写这一镜，保持含义但提升前三秒吸引力和口语节奏：{req.text}"
    script = await asyncio.to_thread(generator.generate_script, prompt, req.style, "quick_30s")
    scene = script.scenes[0].model_dump()
    return {"success": True, "scene": scene}


def _safe_asset_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).resolve()
    root = ASSETS_OUTPUT_DIR.resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=422, detail="素材路径无效")
    return str(path)


@app.post("/api/projects/{project_id}/scenes/{scene_index}/asset")
async def upload_scene_asset(
    project_id: str,
    scene_index: int,
    filename: str = Query(min_length=1, max_length=120),
    content: bytes = Body(media_type="application/octet-stream"),
):
    if not PROJECT_ID_RE.fullmatch(project_id) or not 1 <= scene_index <= MAX_SCENES:
        raise HTTPException(status_code=422, detail="项目或分镜编号无效")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=415, detail="仅支持常见图片和视频格式")
    if not content or len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="素材不能为空且不能超过 100MB")
    path = ASSETS_OUTPUT_DIR / f"{project_id}_upload_scene_{scene_index}_{uuid.uuid4().hex[:6]}{suffix}"
    await asyncio.to_thread(path.write_bytes, content)
    return {"success": True, "asset_file": str(path.resolve()), "asset_url": f"/output/video_assets/{path.name}", "asset_type": "video" if suffix in {".mp4", ".mov", ".webm"} else "image"}


@app.post("/api/projects/{project_id}/scenes/{scene_index}/refresh-asset")
async def refresh_scene_asset(project_id: str, scene_index: int, keywords: str = Query(min_length=1, max_length=300)):
    if not PROJECT_ID_RE.fullmatch(project_id) or not 1 <= scene_index <= MAX_SCENES:
        raise HTTPException(status_code=422, detail="项目或分镜编号无效")
    scene = {"scene_index": scene_index, "visual_keywords": [part.strip() for part in keywords.split(",") if part.strip()]}
    result = await asyncio.to_thread(PexelsMediaClient().fetch_scene_asset, scene["visual_keywords"], scene_index, project_id)
    path = Path(result["asset_file"])
    return {"success": True, "scene": result, "asset_url": f"/output/video_assets/{path.name}"}


@app.post("/api/preview_tts")
async def preview_tts(req: TTSPreviewRequest):
    engine = TTSEngine(voice=req.voice, rate=req.rate, pitch=req.pitch)
    filename = f"preview_{uuid.uuid4().hex[:12]}.mp3"
    result = await engine.generate_speech_with_timestamps(req.text, filename)
    return {"success": True, "audio_url": f"/output/audio/{filename}", "duration": result["duration"]}


@app.get("/api/media/status")
async def media_status():
    return {"success": True, "pexels_configured": bool(PEXELS_API_KEY), "fallback": "Unsplash curated photography"}


@app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_render_job(req: RenderRequest):
    project_id = req.project_id or f"proj_{uuid.uuid4().hex[:8]}"
    raw_scenes = []
    for scene in req.scenes:
        data = scene.model_dump()
        data["asset_file"] = _safe_asset_path(data.get("asset_file"))
        raw_scenes.append(data)
    scenes = [SceneItem(**scene).model_dump() for scene in raw_scenes]
    script = VideoProjectScript(project_id=project_id, title=req.title, topic_summary=req.title, bgm_type=req.bgm_type, scenes=scenes)
    job = job_manager.create({
        "project_id": project_id,
        "script_data": script.model_dump(),
        "voice": req.voice,
        "bgm_type": req.bgm_type,
        "tts_rate": req.tts_rate,
        "tts_pitch": req.tts_pitch,
        "caption_template": req.caption_template,
    })
    return {"success": True, "job": job}


@app.get("/api/jobs/{job_id}")
async def get_render_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.get("result") and job["result"].get("final_video_path"):
        job["video_url"] = f"/output/final/{Path(job['result']['final_video_path']).name}"
    return {"success": True, "job": job}


@app.get("/api/jobs")
async def list_render_jobs(limit: int = Query(default=30, ge=1, le=100)):
    return {"success": True, "jobs": job_manager.list(limit)}


@app.post("/api/jobs/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_render_job(job_id: str):
    job = job_manager.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "job": job}


@app.post("/api/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_render_job(job_id: str):
    job = job_manager.retry(job_id)
    if not job:
        raise HTTPException(status_code=409, detail="任务不存在或当前状态不可重试")
    return {"success": True, "job": job}


@app.post("/api/jobs/{job_id}/restart", status_code=status.HTTP_202_ACCEPTED)
async def restart_render_job(job_id: str):
    job = job_manager.restart(job_id)
    if not job:
        raise HTTPException(status_code=409, detail="任务不存在或当前状态不可重新开始")
    return {"success": True, "job": job}


@app.post("/api/projects/{project_id}/open-draft")
async def open_draft_folder(project_id: str):
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise HTTPException(status_code=422, detail="project_id 格式无效")
    root = DRAFTS_OUTPUT_DIR.resolve()
    draft = (root / f"{project_id}_jianying_draft").resolve()
    if root not in draft.parents or not draft.is_dir():
        raise HTTPException(status_code=404, detail="草稿目录不存在")
    if sys.platform != "win32":
        raise HTTPException(status_code=501, detail="当前平台不支持打开文件管理器")
    os.startfile(str(draft))
    return {"success": True, "message": "已打开剪映工程目录"}


@app.post("/api/render_video", status_code=status.HTTP_202_ACCEPTED, deprecated=True)
async def legacy_render_video(req: RenderRequest):
    return await create_render_job(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
