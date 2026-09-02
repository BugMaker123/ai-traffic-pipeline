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

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging
from audio.tts_engine import TTSEngine
from config.settings import DEFAULT_TTS_PITCH, DEFAULT_TTS_VOICE, DRAFTS_OUTPUT_DIR, MAX_SCENES, OUTPUT_DIR, PEXELS_API_KEY, VOICE_PRESETS
from core.state import SceneItem, VideoProjectScript
from core.logging_config import configure_logging
from core.output_cleanup import cleanup_expired_outputs
from crawlers.hot_topics import CATEGORY_NAMES, HotTopicCrawler
from web_studio.job_manager import job_manager
from writers.script_generator import DURATION_PRESETS, ScriptGenerator

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(cleanup_expired_outputs, dry_run=False)
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
    source_content: str = Field(default="", max_length=4000)
    source_platform: str = Field(default="", max_length=80)
    captured_at: str = Field(default="", max_length=40)


class VideoExtractRequest(StrictModel):
    url_or_text: str = Field(min_length=1, max_length=2000)


class RefScriptRequest(StrictModel):
    ref_title: str = Field(min_length=1, max_length=200)
    ref_transcript: str = Field(min_length=1, max_length=8000)
    style: Literal["干货科普", "幽默反转", "情感共鸣", "商业认知"] = "干货科普"
    duration_tier: Literal[tuple(DURATION_PRESETS.keys())] = "deep_60s"
    source_platform: str = Field(default="短视频提取", max_length=80)


class AIImageRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    scene_index: int = Field(default=1, ge=1, le=MAX_SCENES)


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
    image_prompt: str | None = Field(default="", max_length=500)
    transition: Literal["fade", "zoom_in", "slide_left"] = "zoom_in"


class RenderRequest(StrictModel):
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    scenes: list[RenderSceneRequest] = Field(min_length=1, max_length=MAX_SCENES)
    voice: VoiceId = DEFAULT_TTS_VOICE
    bgm_type: BgmType = "energetic"
    video_layout: Literal["impact", "split_screen", "card_quote"] = "impact"
    enable_karaoke: bool = True
    tts_rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    tts_pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")

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


@app.get("/tasks", response_class=HTMLResponse)
async def serve_tasks() -> str:
    path = TEMPLATES_DIR / "tasks.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="tasks.html not found")
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


@app.post("/api/extract_video_content")
async def extract_video_content(req: VideoExtractRequest):
    """解析短视频链接并自动提取/转写文本"""
    from crawlers.video_extractor import VideoExtractor
    from audio.transcriber import AudioTranscriber

    try:
        info = await asyncio.to_thread(VideoExtractor.extract_video_info_and_audio, req.url_or_text)
        transcript = ""
        if info.get("audio_path"):
            transcript = await asyncio.to_thread(AudioTranscriber.transcribe, info["audio_path"])
        
        if not transcript:
            transcript = info.get("description") or info.get("title", "")

        return {
            "success": True,
            "title": info.get("title", "已提取视频"),
            "author": info.get("author", "未知作者"),
            "platform": info.get("platform", "短视频"),
            "duration": info.get("duration", 0),
            "transcript": transcript,
            "description": info.get("description", ""),
        }
    except Exception as e:
        logger.exception("提取视频文案失败")
        raise HTTPException(status_code=400, detail=f"视频解析失败: {e}")


@app.post("/api/generate_script_from_ref")
async def generate_script_from_ref(req: RefScriptRequest):
    """基于原片提取文案重构原创分镜"""
    generator = ScriptGenerator()
    script = await asyncio.to_thread(
        generator.generate_script_from_reference,
        req.ref_title,
        req.ref_transcript,
        req.style,
        req.duration_tier,
        None,
        req.source_platform,
    )
    return {"success": True, "script": script.model_dump()}


@app.post("/api/generate_ai_image")
async def generate_ai_image(req: AIImageRequest):
    """单独为某个分镜 Prompt 触发 AI 生图预览"""
    from media.ai_image_gen import AIImageGenerator
    gen = AIImageGenerator()
    proj_id = req.project_id or f"proj_{uuid.uuid4().hex[:8]}"
    img_path = await asyncio.to_thread(gen.generate_image, req.prompt, proj_id, req.scene_index)
    if img_path and Path(img_path).exists():
        rel_path = Path(img_path).name
        return {"success": True, "image_url": f"/output/video_assets/{rel_path}", "local_path": img_path}
    raise HTTPException(status_code=500, detail="AI生图未成功生成文件")


@app.post("/api/generate_script")
async def generate_script(req: ScriptRequest):
    generator = ScriptGenerator()
    script = await asyncio.to_thread(
        generator.generate_script, req.topic, req.style, req.duration_tier, None,
        req.source_content, req.source_platform, req.captured_at,
    )
    return {"success": True, "script": script.model_dump()}


@app.post("/api/preview_tts")
async def preview_tts(req: TTSPreviewRequest):
    engine = TTSEngine(voice=req.voice, rate=req.rate, pitch=req.pitch)
    filename = f"preview_{uuid.uuid4().hex[:12]}.mp3"
    result = await engine.generate_speech_with_timestamps(req.text, filename)
    return {"success": True, "audio_url": f"/output/audio/{filename}", "duration": result["duration"]}


@app.get("/api/media/status")
async def media_status():
    return {"success": True, "pexels_configured": bool(PEXELS_API_KEY), "fallback": "Unsplash curated photography & AI Image Generation"}


@app.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_render_job(req: RenderRequest):
    project_id = req.project_id or f"proj_{uuid.uuid4().hex[:8]}"
    scenes = [SceneItem(**scene.model_dump()).model_dump() for scene in req.scenes]
    script = VideoProjectScript(project_id=project_id, title=req.title, topic_summary=req.title, bgm_type=req.bgm_type, scenes=scenes)
    job = job_manager.create({
        "project_id": project_id,
        "script_data": script.model_dump(),
        "voice": req.voice,
        "bgm_type": req.bgm_type,
        "video_layout": req.video_layout,
        "enable_karaoke": req.enable_karaoke,
        "tts_rate": req.tts_rate,
        "tts_pitch": req.tts_pitch,
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
async def list_render_jobs(status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=50, ge=1, le=200)):
    allowed = {"queued", "running", "cancelling", "succeeded", "failed", "cancelled", "interrupted"}
    if status_filter and status_filter not in allowed:
        raise HTTPException(status_code=422, detail="未知任务状态")
    jobs = job_manager.list(status=status_filter, limit=limit)
    summary = {key: 0 for key in allowed}
    for job in job_manager.list(limit=200):
        summary[job.get("status", "failed")] = summary.get(job.get("status", "failed"), 0) + 1
    return {"success": True, "jobs": jobs, "summary": summary}


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
