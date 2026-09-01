# 全自动爆款挖掘与短视频生成流水线系统 (AI Traffic Pipeline)
## 详细功能规格与接口规范 (Functional Specification & API Contracts)

---

## 1. 业务流程与状态机规范 (Pipeline State Spec)

流水线采用 **LangGraph** 进行确定性状态机管理。状态在整个流水线中流动，支持失败节点局部重试与人机审核打断。

### 1.1 状态模型定义 (`PipelineState`)
```python
from typing import TypedDict, List, Optional, Dict, Any

class PipelineState(TypedDict):
    # 输入与挖掘阶段
    topic_query: Optional[str]
    raw_topic: Optional[Dict[str, Any]]
    
    # 脚本与分镜创作阶段
    script_data: Optional[Dict[str, Any]]
    
    # 音频与字幕资产阶段
    audio_path: Optional[str]
    audio_duration: Optional[float]
    subtitles_path: Optional[str]
    word_timestamps: Optional[List[Dict[str, Any]]]
    
    # 视觉素材阶段
    scene_assets: Optional[List[Dict[str, Any]]]  # 每个分镜对应的本地视频/图片路径
    bgm_path: Optional[str]
    
    # 合成与输出阶段
    final_video_path: Optional[str]
    jianying_draft_path: Optional[str]
    error_message: Optional[str]
    status: str  # "init" | "scripted" | "asset_ready" | "rendered" | "failed"
```

---

## 2. 各模块详细功能规格

### 2.1 模块 1：爆款文案重塑与结构化分镜 (LLM Script Engine)

#### 爆款文案经典结构套路库
1. **反直觉震撼型 (Hook)**：“90% 的人都以为 xxx，其实从第一步就全错了！”
2. **痛点扎心型**：“为什么你每天累死累活，还是存不下钱？核心原因只有这 3 点。”
3. **沉浸故事型**：“如果时光倒流 5 年，我绝不会碰这 3 样东西。”

#### LLM 输出约束（JSON Schema）
- 必须严格拆解为 3~6 个分镜（每分镜口播时长约 3~6 秒，总时长控制在 30~60 秒爆款黄金区间）。
- 每个分镜必须附带 `visual_keywords`（英文关键词，便于在国际免版权图库检索）。

---

### 2.2 模块 2：TTS 语音与字级时间戳对齐 (Voice & Subtitle Engine)

#### 支持的 TTS 方案
- **Edge-TTS (默认内置)**:
  - 推荐音色：`zh-CN-YunxiNeural` (充满活力解说风)、`zh-CN-YunjianNeural` (稳重大气沉浸风)、`zh-CN-XiaoxiaoNeural` (亲切知性女性风)。
  - 参数支持：`rate="+15%"`（短视频通常加速 1.1x~1.2x 以提高完播率）。
- **时间戳对齐算法**:
  - 利用 Edge-TTS WebSocket 协议直接抓取 `WordBoundary` 事件的时间偏置（毫秒级）。
  - 输出标准 ASS / SRT 格式，以及字级高亮坐标数据，供视频渲染器做动态弹跳字效。

---

### 2.3 模块 3：素材自动匹配与 BGM 智能混音 (Asset & Audio Matcher)

#### 智能素材检索策略
1. **视频优先策略**：调用 Pexels Video Search API (`orientation=portrait`, `size=medium`)。
2. **素材时长对齐**：若素材时长短于分镜语音时长，自动进行无缝慢速回放或倒放循环。
3. **BGM 智能 Ducking（闪避效果）**：
   - 基础 BGM 音量维持在 `-22dB`。
   - 旁白间隙时平滑淡入提升到 `-14dB`，极大提升短视频听觉节奏感。

---

### 2.4 模块 4：视频合成双引擎规格 (Compositor Specifications)

#### 方案 A：MoviePy / FFmpeg 核心参数
- **画布规格**：1080 x 1920 (9:16 竖屏，30 FPS)。
- **视觉特效**：
  - 静态图自动添加慢镜头推近（Ken Burns Zoom 1.0 -> 1.15）。
  - 横屏素材自动上下添加高斯模糊毛玻璃背景垫底。
- **花字排版**：
  - 顶部常驻爆款吸睛大标题（黄色加粗黑描边）。
  - 中下方动态双行居中字幕（当前发音词高亮亮黄色）。

#### 方案 B：剪映工程草稿化 (pyJianYing)
- 生成剪映本地识别的 `draft_content.json` 与 `draft_meta_info.json`。
- 自动写入：
  - 视频轨（带出入场动画、运镜）。
  - 音频轨（人声音轨 + BGM 音轨 + 转场 Whoosh 音效）。
  - 文本轨（套用剪映内置爆款花字模板样式、气泡）。

---

## 3. 环境配置与启动规范

### 3.1 依赖配置文件示例 (`requirements.txt`)
```text
# 核心大模型与编排
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
pydantic>=2.7.0

# 语音合成与音视频处理
edge-tts>=6.1.12
moviepy>=2.0.0.dev2
pillow>=10.0.0
requests>=2.31.0
numpy>=1.24.0

# 数据采集与工具
playwright>=1.40.0
beautifulsoup4>=4.12.0
rich>=13.0.0
python-dotenv>=1.0.0
```

### 3.2 环境变量配置 (`.env.example`)
```bash
# 大模型配置
OPENAI_API_KEY="your-llm-api-key"
OPENAI_BASE_URL="https://api.openai.com/v1"
LLM_MODEL="deepseek-chat"

# 素材库 API
PEXELS_API_KEY="your-pexels-api-key"

# 默认音色配置
DEFAULT_TTS_VOICE="zh-CN-YunxiNeural"
TTS_RATE="+15%"
```
