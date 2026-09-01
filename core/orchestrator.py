"""
LangGraph 流水线编排引擎 (Pipeline Orchestrator)
异步安全 + 线程池隔离，支持 CLI 与 FastAPI 异步 Web Studio 零阻塞并发
"""
import uuid
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END
from core.state import PipelineState
from crawlers.hot_topics import HotTopicCrawler
from writers.script_generator import ScriptGenerator
from audio.tts_engine import TTSEngine
from audio.srt_aligner import SubtitleAligner
from media.pexels_client import PexelsMediaClient
from media.bgm_manager import BGMManager
from compositors.moviepy_renderer import MoviePyRenderer
from compositors.jianying_draft import JianYingDraftGenerator
from config.settings import AUDIO_OUTPUT_DIR, DEFAULT_TTS_PITCH, DEFAULT_TTS_RATE, DEFAULT_TTS_VOICE

class PipelineCancelled(RuntimeError):
    """由后台任务发出的协作式取消信号。"""


def _enter_stage(state: PipelineState, stage: str) -> None:
    cancel_event = state.get("cancel_event")
    if cancel_event is not None and cancel_event.is_set():
        raise PipelineCancelled("任务已取消")
    callback = state.get("progress_callback")
    if callback:
        callback(stage)

def node_topic_mining(state: PipelineState) -> Dict[str, Any]:
    """节点 1：选题挖掘与热点确认"""
    _enter_stage(state, "topic_mining")
    logs = state.get("logs", [])
    script_data = state.get("script_data")
    
    if script_data and script_data.get("scenes"):
        title = script_data.get("title", "自定分镜短视频")
        logs.append(f"🎯 使用工作台定制分镜: 《{title}》 (共 {len(script_data['scenes'])} 分镜)")
        return {
            "topic_query": title,
            "raw_topic": {"title": title, "source_platform": "custom"},
            "logs": logs,
            "status": "topic_ready"
        }
        
    topic_query = state.get("topic_query")
    if not topic_query:
        top_trends = HotTopicCrawler.get_top_trending(limit=1)
        chosen = top_trends[0] if top_trends else HotTopicCrawler.get_preset_growth_topics()[0]
        topic_query = chosen.title
        raw_topic = chosen.model_dump()
        logs.append(f"🔍 自动捕获全网爆款选题: 《{topic_query}》 (爆发指数: {chosen.hot_score})")
    else:
        raw_topic = {"title": topic_query, "source_platform": "custom"}
        logs.append(f"🎯 确认创作选题: 《{topic_query}》")
        
    return {
        "topic_query": topic_query,
        "raw_topic": raw_topic,
        "logs": logs,
        "status": "topic_ready"
    }

def node_script_writing(state: PipelineState) -> Dict[str, Any]:
    """节点 2：LLM 爆款文案重塑与结构化分镜拆解"""
    _enter_stage(state, "script_writing")
    logs = state.get("logs", [])
    script_data = state.get("script_data")
    
    if script_data and script_data.get("scenes") and len(script_data["scenes"]) > 0:
        logs.append(f"✍️ 已载入 {len(script_data['scenes'])} 个分镜脚本，进入音频合成...")
        return {
            "script_data": script_data,
            "logs": logs,
            "status": "scripted"
        }
        
    topic = state.get("topic_query", "自律与认知觉醒")
    project_id = state.get("project_id", f"proj_{uuid.uuid4().hex[:8]}")
    
    logs.append(f"✍️ 正在调用 DeepSeek 深度创作爆款分镜脚本 (黄金3秒Hook + 痛点展开 + 底层机制 + CTA)...")
    generator = ScriptGenerator()
    script = generator.generate_script(topic_or_content=topic, project_id=project_id, duration_tier="deep_60s")
    
    logs.append(f"✅ 分镜剧本生成完毕，共 {len(script.scenes)} 个分镜，爆款标题: 《{script.title}》")
    return {
        "script_data": script.model_dump(),
        "logs": logs,
        "status": "scripted"
    }

def node_audio_and_subtitles(state: PipelineState) -> Dict[str, Any]:
    """节点 3：TTS 旁白流式生成与毫秒字级字幕对齐 (事件循环安全适配)"""
    _enter_stage(state, "audio_and_subtitles")
    logs = state.get("logs", [])
    script_data = state.get("script_data", {})
    project_id = state.get("project_id", "proj_demo")
    scenes = script_data.get("scenes", [])
    voice = state.get("voice") or DEFAULT_TTS_VOICE
    rate = state.get("tts_rate") or DEFAULT_TTS_RATE
    pitch = state.get("tts_pitch") or DEFAULT_TTS_PITCH
    
    logs.append(f"🎙️ 正在调用 Edge-TTS 合成高拟真旁白音轨 ({voice}) 并计算精确词时间戳...")
    tts_engine = TTSEngine(voice=voice, rate=rate, pitch=pitch)
    
    def _run_tts_sync():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(tts_engine.generate_scenes_speech(scenes, project_id))
        finally:
            new_loop.close()
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        enriched_scenes = pool.submit(_run_tts_sync).result()

    fallback_count = sum(1 for scene in enriched_scenes if scene.get("tts_fallback"))
    if fallback_count:
        logs.append(f"⚠️ Edge-TTS 暂时不可达，已为 {fallback_count} 个分镜生成静音占位音轨并使用估算字幕时间轴继续渲染。")
    
    global_subtitles = []
    current_time_offset = 0.0
    for sc in enriched_scenes:
        chunks = SubtitleAligner.chunk_scene_subtitles(sc, start_offset=current_time_offset)
        global_subtitles.extend(chunks)
        current_time_offset += sc.get("duration", 3.0)
        
    srt_path = AUDIO_OUTPUT_DIR / f"{project_id}_subtitles.srt"
    SubtitleAligner.export_srt(global_subtitles, srt_path)
    
    logs.append(f"✅ 音频与字幕生成完成，视频总时长: {current_time_offset:.1f}s (共 {len(global_subtitles)} 句高光字幕)")
    
    script_data["scenes"] = enriched_scenes
    return {
        "script_data": script_data,
        "subtitles": global_subtitles,
        "srt_path": str(srt_path),
        "audio_duration": current_time_offset,
        "logs": logs,
        "status": "audio_ready"
    }

def node_media_sourcing(state: PipelineState) -> Dict[str, Any]:
    """节点 4：9:16 动态视觉素材检索与 BGM 准备"""
    _enter_stage(state, "media_sourcing")
    logs = state.get("logs", [])
    script_data = state.get("script_data", {})
    project_id = state.get("project_id", "proj_demo")
    scenes = script_data.get("scenes", [])
    bgm_type = state.get("bgm_type", "energetic")
    
    logs.append("🎬 正在准备 9:16 沉浸式动态视觉画面与氛围背景音乐...")
    media_client = PexelsMediaClient()
    updated_scenes = media_client.fetch_scene_assets(scenes, project_id=project_id)
    source_counts: Dict[str, int] = {}
    for scene in updated_scenes:
        source = scene.get("asset_source", "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    
    bgm_mgr = BGMManager()
    bgm_path = bgm_mgr.get_bgm(bgm_type=bgm_type)
    
    script_data["scenes"] = updated_scenes
    source_summary = "、".join(f"{name} × {count}" for name, count in source_counts.items())
    logs.append(f"✅ 视觉素材就绪：{source_summary}；背景音乐: {bgm_type}")
    
    return {
        "script_data": script_data,
        "scene_assets": updated_scenes,
        "bgm_path": bgm_path,
        "logs": logs,
        "status": "media_ready"
    }

def node_video_compositing(state: PipelineState) -> Dict[str, Any]:
    """节点 5：工业级 1080x1920 视频渲染合成与剪映工程导出"""
    _enter_stage(state, "video_compositing")
    logs = state.get("logs", [])
    project_id = state.get("project_id", "proj_demo")
    script_data = state.get("script_data", {})
    title = script_data.get("title", "爆款短视频")
    scenes = script_data.get("scenes", [])
    subtitles = state.get("subtitles", [])
    bgm_path = state.get("bgm_path")
    
    logs.append("🚀 正在调用工业级渲染引擎合成 1080x1920 竖屏短视频 (含转场音效与大标题)...")
    renderer = MoviePyRenderer()
    final_video = renderer.render_project(
        project_id=project_id,
        title=title,
        scenes=scenes,
        subtitles=subtitles,
        bgm_path=bgm_path
    )
    logs.append(f"🎉 短视频成品渲染成功: {final_video}")
    
    draft_dir = JianYingDraftGenerator.generate_draft(
        project_id=project_id,
        title=title,
        scenes=scenes,
        subtitles=subtitles,
        bgm_path=bgm_path
    )
    logs.append(f"📂 剪映 Draft 工程同步生成: {draft_dir}")
    
    return {
        "final_video_path": final_video,
        "jianying_draft_path": draft_dir,
        "logs": logs,
        "status": "rendered"
    }

def build_traffic_pipeline():
    builder = StateGraph(PipelineState)
    builder.add_node("topic_mining", node_topic_mining)
    builder.add_node("script_writing", node_script_writing)
    builder.add_node("audio_and_subtitles", node_audio_and_subtitles)
    builder.add_node("media_sourcing", node_media_sourcing)
    builder.add_node("video_compositing", node_video_compositing)
    
    builder.set_entry_point("topic_mining")
    builder.add_edge("topic_mining", "script_writing")
    builder.add_edge("script_writing", "audio_and_subtitles")
    builder.add_edge("audio_and_subtitles", "media_sourcing")
    builder.add_edge("media_sourcing", "video_compositing")
    builder.add_edge("video_compositing", END)
    
    return builder.compile()

class VideoPipelineRunner:
    @staticmethod
    def run(
        topic: str = "",
        script_data: Optional[Dict[str, Any]] = None,
        voice: Optional[str] = None,
        bgm_type: Optional[str] = "energetic",
        project_id: str = "",
        progress_callback=None,
        cancel_event=None,
        resume_state: Optional[Dict[str, Any]] = None,
        checkpoint_callback=None,
        tts_rate: Optional[str] = None,
        tts_pitch: Optional[str] = None,
    ) -> PipelineState:
        proj_id = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        initial_state: PipelineState = {
            "project_id": proj_id,
            "topic_query": topic if topic else None,
            "script_data": script_data,
            "voice": voice,
            "bgm_type": bgm_type,
            "logs": [],
            "status": "init"
            , "progress_callback": progress_callback
            , "cancel_event": cancel_event
            , "tts_rate": tts_rate
            , "tts_pitch": tts_pitch
        }
        if resume_state:
            initial_state.update(resume_state)
            initial_state["progress_callback"] = progress_callback
            initial_state["cancel_event"] = cancel_event

        # 顺序执行并在每个阶段完成后保存完整状态，使失败/重启可从最近检查点继续。
        stages = [
            ("topic_ready", node_topic_mining),
            ("scripted", node_script_writing),
            ("audio_ready", node_audio_and_subtitles),
            ("media_ready", node_media_sourcing),
            ("rendered", node_video_compositing),
        ]
        completed = {name for name, _ in stages}
        state: PipelineState = initial_state
        resume_status = state.get("status")
        skip = resume_status in completed
        for target_status, node in stages:
            if skip:
                if target_status == resume_status:
                    skip = False
                continue
            state.update(node(state))
            if checkpoint_callback:
                checkpoint_callback(dict(state))
        return state
