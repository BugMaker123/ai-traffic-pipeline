"""AI Traffic Pipeline Web Studio API。"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import logging
from audio.tts_engine import TTSEngine
from config.settings import (
    ASSETS_OUTPUT_DIR,
    DEFAULT_TTS_PITCH,
    DEFAULT_TTS_VOICE,
    DRAFTS_OUTPUT_DIR,
    MAX_SCENES,
    OUTPUT_DIR,
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    VOICE_PRESETS,
    WEB_HOST,
    WEB_PORT,
)
from core.state import SceneItem, VideoProjectScript
from core.logging_config import configure_logging
from core.output_cleanup import cleanup_expired_outputs
from crawlers.hot_topics import CATEGORY_NAMES, HotTopicCrawler
from audio.voice_manager import voice_manager
from publishers.manager import publish_manager
from media.style_presets import style_manager
from safety.compliance_guard import compliance_guard
from web_studio.job_manager import job_manager
from writers.script_generator import DURATION_PRESETS, STYLE_PRESETS, ScriptGenerator

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
VoiceId = str
ScriptStyle = Literal[tuple(STYLE_PRESETS.keys())]
BgmType = Literal["energetic", "suspense", "emotional", "chill"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScriptRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=500)
    style: ScriptStyle = "干货科普"
    duration_tier: str = "deep_60s"
    source_content: str = Field(default="", max_length=4000)
    source_platform: str = Field(default="", max_length=80)
    captured_at: str = Field(default="", max_length=40)
    chosen_angle: str = Field(default="", max_length=500)
    art_style: str = Field(default="cinematic_dark", max_length=50)

    @field_validator("duration_tier", mode="before")
    @classmethod
    def normalize_duration(cls, v: str) -> str:
        if v in DURATION_PRESETS:
            return v
        if "30" in str(v) and "60" not in str(v):
            return "quick_30s"
        if "120" in str(v) or "long" in str(v):
            return "long_120s"
        return "deep_60s"


class AnglesRequest(StrictModel):
    topic: str = Field(min_length=1, max_length=500)
    raw_content: str = Field(default="", max_length=1000)
    category: str = Field(default="", max_length=50)


class VideoExtractRequest(StrictModel):
    url_or_text: str = Field(min_length=1, max_length=2000)


class RefScriptRequest(StrictModel):
    ref_title: str = Field(min_length=1, max_length=200)
    ref_transcript: str = Field(min_length=1, max_length=8000)
    style: ScriptStyle = "干货科普"
    duration_tier: str = "deep_60s"
    source_platform: str = Field(default="短视频提取", max_length=80)
    art_style: str = Field(default="cinematic_dark", max_length=50)

    @field_validator("duration_tier", mode="before")
    @classmethod
    def normalize_duration(cls, v: str) -> str:
        if v in DURATION_PRESETS:
            return v
        if "30" in str(v) and "60" not in str(v):
            return "quick_30s"
        if "120" in str(v) or "long" in str(v):
            return "long_120s"
        return "deep_60s"


class AIImageRequest(StrictModel):
    prompt: str = Field(min_length=1, max_length=500)
    project_id: str | None = None
    scene_index: int = Field(default=1, ge=1, le=MAX_SCENES)
    art_style: str = Field(default="cinematic_dark", max_length=50)


class ComplianceScanRequest(StrictModel):
    text: str = Field(min_length=1, max_length=10000)


class ComplianceSanitizeRequest(StrictModel):
    text: str = Field(min_length=1, max_length=10000)


class TTSPreviewRequest(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    voice: VoiceId = DEFAULT_TTS_VOICE
    rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")


class RenderSceneRequest(StrictModel):
    scene_index: int = Field(ge=1, le=MAX_SCENES)
    voiceover_text: str = Field(min_length=1, max_length=1000)
    scene_type: Literal["", "hook", "context", "evidence", "action", "turn", "outro"] = ""
    visual_keywords: list[str] = Field(default_factory=list, max_length=8)
    caption_highlight: list[str] = Field(default_factory=list, max_length=12)
    image_prompt: str | None = Field(default="", max_length=500)
    transition: Literal["fade", "zoom_in", "slide_left"] = "zoom_in"
    asset_file: str | None = Field(default=None, max_length=500)
    asset_type: Literal["image", "video"] = "image"
    img: str | None = Field(default=None, max_length=2000)


class RenderRequest(StrictModel):
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    scenes: list[RenderSceneRequest] = Field(min_length=1, max_length=MAX_SCENES)
    voice: VoiceId = DEFAULT_TTS_VOICE
    bgm_type: BgmType = "energetic"
    video_layout: Literal["impact", "split_screen", "card_quote"] = "impact"
    enable_karaoke: bool = True
    subtitle_style: Literal["impact_yellow", "cyber_neon", "variety_pop", "cinema_white", "minimal_capsule", "flame_gold"] = "impact_yellow"
    enable_punch_in: bool = True
    art_style: str = Field(default="cinematic_dark", max_length=50)
    tts_rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    tts_pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str | None) -> str | None:
        if value is not None and not PROJECT_ID_RE.fullmatch(value):
            raise ValueError("project_id 格式无效")
        return value


class BatchTopicItem(StrictModel):
    topic: str = Field(min_length=1, max_length=500)
    style: ScriptStyle = "干货科普"
    duration_tier: str = "deep_60s"
    source_content: str = Field(default="", max_length=4000)
    source_platform: str = Field(default="", max_length=80)


class BatchRenderRequest(StrictModel):
    topics: list[str] = Field(default_factory=list, max_length=50)
    items: list[BatchTopicItem] = Field(default_factory=list, max_length=50)
    voice: VoiceId = DEFAULT_TTS_VOICE
    bgm_type: BgmType = "energetic"
    video_layout: Literal["impact", "split_screen", "card_quote"] = "impact"
    enable_karaoke: bool = True
    subtitle_style: Literal["impact_yellow", "cyber_neon", "variety_pop", "cinema_white", "minimal_capsule", "flame_gold"] = "impact_yellow"
    tts_rate: str = Field(default="+0%", pattern=r"^[+-](?:100|[0-9]{1,2})%$")
    tts_pitch: str = Field(default=DEFAULT_TTS_PITCH, pattern=r"^[+-][0-9]{1,2}Hz$")


class MatrixPublishRequest(StrictModel):
    video_path: str = Field(min_length=1, max_length=500)
    platforms: list[str] = Field(min_length=1, max_length=10)
    title: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=2000)
    enable_anti_duplicate: bool = True
    cover_path: str | None = Field(default=None, max_length=500)
    schedule_time: str | None = Field(default=None, max_length=50)


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
async def get_trends(
    response: Response,
    category: str = Query(default="all"),
    signal: str = Query(default="all"),
    niche: str = Query(default="all"),
    platform: str = Query(default="all"),
    limit: int = Query(default=35),
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    trends = await asyncio.to_thread(
        HotTopicCrawler.get_categorized_trends,
        category=category,
        signal=signal,
        niche=niche,
        platform=platform,
        limit=limit,
    )
    return {
        "success": True,
        "fetched_at": time.strftime("%H:%M:%S"),
        "count": len(trends),
        "trends": [item.model_dump() for item in trends]
    }


@app.get("/api/voices")
async def get_voices():
    voices = [
        {
            "id": p.voice_id,
            "name": p.name,
            "gender": p.gender,
            "provider": p.provider,
            "description": p.description,
            "is_custom": p.is_custom,
            "reference_audio": p.reference_audio,
        }
        for p in voice_manager.list_voices()
    ]
    return {"success": True, "voices": voices}


@app.post("/api/voices/clone", status_code=status.HTTP_201_CREATED)
async def clone_custom_voice(
    name: str = Form(min_length=1, max_length=60),
    file: UploadFile = File(...),
    gender: Literal["male", "female"] = Form(default="male"),
    prompt_text: str = Form(default=""),
    fallback_voice: str = Form(default=DEFAULT_TTS_VOICE),
    description: str = Form(default=""),
):
    temp_dir = OUTPUT_DIR / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"
    content = await file.read()
    temp_path.write_bytes(content)
    try:
        profile = voice_manager.register_clone_voice(
            name=name,
            audio_source_path=temp_path,
            prompt_text=prompt_text,
            gender=gender,
            fallback_voice=fallback_voice,
            description=description,
        )
        return {"success": True, "voice": profile.model_dump()}
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@app.delete("/api/voices/{voice_id}")
async def delete_custom_voice(voice_id: str):
    success = voice_manager.delete_clone_voice(voice_id)
    if not success:
        raise HTTPException(status_code=404, detail="自定义音色不存在或预设音色不可删除")
    return {"success": True, "message": "音色已成功删除"}


@app.post("/api/extract_video_content")
@app.post("/api/extract_video")
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
    img_path = await asyncio.to_thread(gen.generate_image, req.prompt, proj_id, req.scene_index, None, req.art_style)
    if img_path and Path(img_path).exists():
        rel_path = Path(img_path).name
        return {"success": True, "image_url": f"/output/video_assets/{rel_path}", "local_path": img_path}
    raise HTTPException(status_code=500, detail="AI生图未成功生成文件")


@app.post("/api/generate_angles")
async def api_generate_angles(req: AnglesRequest):
    """根据原始热点/选题，调用大模型生成差异化爆款切口供用户挑选"""
    generator = ScriptGenerator()
    angles = await asyncio.to_thread(
        generator.generate_angles,
        topic=req.topic,
        raw_content=req.raw_content,
        category=req.category,
    )
    return {"success": True, "topic": req.topic, "angles": angles}


@app.post("/api/generate_script")
async def generate_script(req: ScriptRequest):
    generator = ScriptGenerator()
    script = await asyncio.to_thread(
        generator.generate_script,
        req.topic,
        req.style,
        req.duration_tier,
        None,
        req.source_content,
        req.source_platform,
        req.captured_at,
        req.chosen_angle,
        req.art_style,
    )
    return {"success": True, "script": script.model_dump()}


@app.post("/api/preview_tts")
async def preview_tts(req: TTSPreviewRequest):
    engine = TTSEngine(voice=req.voice, rate=req.rate, pitch=req.pitch)
    filename = f"preview_{uuid.uuid4().hex[:12]}.mp3"
    result = await engine.generate_speech_with_timestamps(req.text, filename)
    return {"success": True, "audio_url": f"/output/audio/{filename}", "duration": result["duration"]}


@app.post("/api/upload_asset")
async def upload_asset(
    file: UploadFile = File(...),
    scene_index: int = Form(default=1),
    project_id: str = Form(default="proj_custom"),
):
    ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持格式: JPG, PNG, WEBP, MP4, MOV, WEBM",
        )

    safe_project_id = re.sub(r"[^a-zA-Z0-9_-]", "", project_id) or "proj_custom"
    file_id = uuid.uuid4().hex[:8]
    filename = f"{safe_project_id}_custom_scene_{scene_index}_{file_id}{ext}"
    out_path = ASSETS_OUTPUT_DIR / filename

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="上传的文件为空")

    out_path.write_bytes(content)
    is_video = ext in {".mp4", ".mov", ".webm"}

    return {
        "success": True,
        "asset_url": f"/output/video_assets/{filename}",
        "local_path": str(out_path),
        "asset_type": "video" if is_video else "image",
        "filename": filename,
        "size_bytes": len(content),
    }


@app.get("/api/media/status")
async def media_status():
    return {
        "success": True,
        "pexels_configured": bool(PEXELS_API_KEY),
        "pixabay_configured": bool(PIXABAY_API_KEY),
        "fallback": "Unsplash & Pixabay Curated 4K/1080P Footage & Wikimedia Commons",
    }


@app.get("/api/art_styles")
async def get_art_styles():
    """获取支持的全局电影级视觉风格预设"""
    return {"success": True, "styles": style_manager.list_styles()}


@app.post("/api/compliance/scan")
async def scan_compliance(req: ComplianceScanRequest):
    """实时扫描文案中的广告法极限词与自媒体违禁词"""
    res = compliance_guard.scan(req.text)
    return {"success": True, **res.model_dump()}


@app.post("/api/compliance/sanitize")
async def sanitize_compliance(req: ComplianceSanitizeRequest):
    """一键将违禁词自动平替为平台合规表述"""
    clean = compliance_guard.auto_sanitize(req.text)
    return {"success": True, "sanitized_text": clean}


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
        "subtitle_style": req.subtitle_style,
        "enable_punch_in": req.enable_punch_in,
        "art_style": req.art_style,
        "tts_rate": req.tts_rate,
        "tts_pitch": req.tts_pitch,
    })
    return {"success": True, "job": job}


@app.post("/api/batch_jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_batch_jobs(req: BatchRenderRequest):
    items: list[dict[str, Any]] = []
    for t in req.topics:
        t_clean = t.strip()
        if t_clean:
            items.append({"topic": t_clean})
    for it in req.items:
        t_clean = it.topic.strip()
        if t_clean:
            items.append({
                "topic": t_clean,
                "style": it.style,
                "duration_tier": it.duration_tier,
                "source_content": it.source_content,
                "source_platform": it.source_platform,
            })
    if not items:
        raise HTTPException(status_code=400, detail="请提供至少一个待生成的选题")

    common_options = {
        "voice": req.voice,
        "bgm_type": req.bgm_type,
        "video_layout": req.video_layout,
        "enable_karaoke": req.enable_karaoke,
        "subtitle_style": req.subtitle_style,
        "tts_rate": req.tts_rate,
        "tts_pitch": req.tts_pitch,
    }
    batch = job_manager.create_batch(items, common_options)
    return {"success": True, "batch": batch}


@app.get("/api/batches/{batch_id}")
async def get_batch_status(batch_id: str):
    batch = job_manager.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    for j in batch.get("jobs", []):
        if j.get("result") and j["result"].get("final_video_path"):
            j["video_url"] = f"/output/final/{Path(j['result']['final_video_path']).name}"
    return {"success": True, "batch": batch}


@app.get("/api/batches")
async def list_batches(limit: int = Query(default=20, ge=1, le=100)):
    batches = job_manager.list_batches(limit=limit)
    return {"success": True, "batches": batches}


@app.post("/api/batches/{batch_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_batch(batch_id: str):
    batch = job_manager.cancel_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    return {"success": True, "batch": batch}


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


@app.get("/api/publish/platforms")
async def list_publish_platforms():
    return {"success": True, "platforms": publish_manager.list_supported_platforms()}


@app.get("/api/publish/history")
async def get_publish_history(limit: int = Query(default=50, ge=1, le=100)):
    return {"success": True, "history": publish_manager.get_history(limit=limit)}


@app.post("/api/publish", status_code=status.HTTP_200_OK)
async def publish_video_matrix(req: MatrixPublishRequest):
    raw_vpath = req.video_path.strip()
    if raw_vpath.startswith("/output/"):
        raw_vpath = raw_vpath[len("/output/"):]
    v_path = (OUTPUT_DIR / raw_vpath).resolve()
    if not v_path.is_file():
        direct_p = Path(req.video_path).resolve()
        if direct_p.is_file():
            v_path = direct_p
        else:
            raise HTTPException(status_code=404, detail=f"待发布视频文件未找到: {req.video_path}")

    c_path = None
    if req.cover_path:
        c_raw = req.cover_path.strip()
        if c_raw.startswith("/output/"):
            c_raw = c_raw[len("/output/"):]
        cand = (OUTPUT_DIR / c_raw).resolve()
        if cand.is_file():
            c_path = cand

    try:
        res = await publish_manager.publish_to_platforms(
            video_path=v_path,
            platforms=req.platforms,
            title=req.title,
            tags=req.tags,
            description=req.description,
            enable_anti_duplicate=req.enable_anti_duplicate,
            cover_path=c_path,
            schedule_time=req.schedule_time,
        )
        return {"success": True, "publish_record": res}
    except Exception as e:
        logger.exception("矩阵发布调度异常")
        raise HTTPException(status_code=500, detail=f"发布失败: {e}")


@app.post("/api/render_video", status_code=status.HTTP_202_ACCEPTED, deprecated=True)
async def legacy_render_video(req: RenderRequest):
    return await create_render_job(req)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
