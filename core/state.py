"""
核心状态定义与数据协议模块
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class SceneItem(BaseModel):
    """单个视频分镜数据结构"""
    scene_index: int = Field(description="分镜序号，从 1 开始")
    voiceover_text: str = Field(min_length=1, max_length=1000, description="该分镜旁白台词")
    visual_keywords: List[str] = Field(default_factory=list, max_length=8, description="用于免版权图库检索的英文关键词")
    image_prompt: Optional[str] = Field(default="", description="若使用 AI 生图时的详细 Prompt")
    caption_highlight: Optional[List[str]] = Field(default_factory=list, description="需要特别高亮着色的核心词")
    transition: str = Field(default="fade", description="转场动效: fade, zoom_in, slide_left, etc.")
    
    # 运行时资产回填字段
    audio_file: Optional[str] = None
    duration: Optional[float] = None
    asset_file: Optional[str] = None
    asset_type: Optional[str] = None  # "video" | "image"

class VideoProjectScript(BaseModel):
    """完整的视频结构化剧本"""
    project_id: str
    title: str = Field(min_length=1, max_length=120, description="视频主标题（爆款 Hook 标题）")
    topic_summary: str = Field(min_length=1, max_length=1000, description="主题概要")
    tone_style: str = Field(default="干货科普", description="风格定位：干货科普、幽默反转、情感共鸣、商业思维等")
    bgm_type: str = Field(default="energetic", description="推荐 BGM 情绪类型: energetic, suspense, emotional, chill")
    scenes: List[SceneItem] = Field(description="分镜列表")
    tags: List[str] = Field(default_factory=list, description="短视频标签 Tag")
    grounding_status: str = Field(default="topic_only", description="事实时效状态")
    freshness_note: str = Field(default="", description="时效与事实边界说明")

class RawTopicItem(BaseModel):
    """原始采集的热点/爆款数据 (支持垂直分类与多平台共振登顶)"""
    id: str
    source_platform: str  # "douyin", "weibo", "bilibili", "baidu", "cross_platform"
    title: str
    raw_content: str
    category: str = "social"  # "resonance", "tech", "finance", "social", "entertainment", "growth"
    category_name: str = "社会民生"
    is_resonance: bool = False  # 是否为多平台共振登顶爆款
    resonating_platforms: List[str] = Field(default_factory=list)  # 如 ["douyin", "weibo"]
    video_url: Optional[str] = None
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hot_score: float = 0.0
    editorial_score: float = 0.0
    trend_reason: str = ""
    captured_at: Optional[str] = None

class PipelineState(TypedDict, total=False):
    """LangGraph 管道运行时的全生命周期上下文状态"""
    project_id: str
    topic_query: Optional[str]
    voice: Optional[str]
    tts_rate: Optional[str]
    tts_pitch: Optional[str]
    bgm_type: Optional[str]
    video_layout: Optional[str]
    enable_karaoke: Optional[bool]
    raw_topic: Optional[Dict[str, Any]]
    
    # 脚本创作输出
    script_data: Optional[Dict[str, Any]]
    
    # 音频与字幕输出
    audio_path: Optional[str]
    audio_duration: Optional[float]
    srt_path: Optional[str]
    subtitles: Optional[List[Dict[str, Any]]]
    
    # 视觉与配乐资产
    scene_assets: Optional[List[Dict[str, Any]]]
    bgm_path: Optional[str]
    
    # 最终视频渲染输出
    final_video_path: Optional[str]
    jianying_draft_path: Optional[str]
    
    # 运行监控
    logs: List[str]
    error_message: Optional[str]
    status: str
    progress_callback: Any
    cancel_event: Any
