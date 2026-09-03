# AI Traffic Pipeline 待开发功能全景规划与落地路线图

本文档基于系统整体架构设计规范（`docs/DESIGN_AND_DEVELOPMENT.md`）与功能规格书（`docs/FUNCTIONAL_SPEC.md`），全面盘点系统功能差距，并制定分阶段实施计划。

---

## 一、 功能现状与差距全景矩阵

| 序号 | 业务阶段 | 规划目标 | 当前状态 | 差距与待实现功能 | 优先级 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **视频渲染合成** | 视听质感拉满，电影级推拉、转场与自适应排版 | ✅ **已全面完成** (`commit 356961c`) | BGM 智能让音、分镜平滑转场、横屏毛玻璃垫底、剪映 `draft_meta_info.json` 索引已全部落地 | **P0 (已完成)** |
| **2** | **音频与混音** | 专业播客/短视频级人声突出，BGM自适应让音 | ✅ **已全面完成** (`commit ab83c83`) | BGM Sidechain Ducking 动态闪避、CosyVoice 声音克隆适配器与 Edge-TTS 离线平滑降级已全部落地 | **P0 / P2 (已完成)** |
| **3** | **批量化与生产力** | 无人值守多任务夜间跑批 | ✅ **已全面完成** (`commit 6fd6a41`) | Batch Job 批量队列、多选热点一键生成、批量排队与取消管理已全部落地 | **P1 (已完成)** |
| **4** | **爆款挖掘与解析** | 全网平台深度爬取与爆发指数模型 | ✅ **已全面完成** (`commit ab83c83`) | 社媒短视频链接解析提取、Whisper/离线文本反推、大模型重塑原创分镜已全部落地 | **P2 (已完成)** |
| **5** | **发布与分发闭环** | 一键定时多平台自动化发布 | ✅ **已全面完成** (`commit c846af7`) | 抖音/B站/小红书/视频号矩阵发布器、视频抗查重微混淆引擎（裁切/微变速/色彩微调/打散MD5）已全部落地 | **P3 (已完成)** |

---

## 二、 详细实施阶段规划与交付记录

### 第一阶段（Phase 1 - P0）：视频渲染与音效质感核心突破（已交付）
- **交付内容**：`compositors/moviepy_renderer.py` BGM 智能动态让音、分镜转场过渡、横屏素材高斯模糊毛玻璃居中、`compositors/jianying_draft.py` 剪映 `draft_meta_info.json` 元数据索引。
- **验证结果**：单测 12 项全部通过，Git commit `356961c`。

---

### 第二阶段（Phase 2 - P1）：批量化无人值守流水线 (Batch Mode)（已交付）
- **交付内容**：`core/orchestrator.py` 单主题免交互流水线、`web_studio/job_manager.py` 批次持久化管理、FastAPI 批量接口 (`/api/batch_jobs`、`/api/batches/{id}`)、Web Studio 前端热榜批量勾选与任务监控看板。
- **验证结果**：单测 `tests/test_batch_jobs.py` 4 项全绿，Git commit `6fd6a41`。

---

### 第三阶段（Phase 3 - P2）：声音克隆与社媒短视频解构工坊（已交付）
- **交付内容**：`audio/adapters.py`（EdgeTTSAdapter 与 CosyVoice 声音克隆适配器）、`audio/voice_manager.py`（音色持久化中心与平滑降级）、`extractors/video_extractor.py`（社媒原片文案提取）、Web Studio 声音克隆中心与视频解构工坊。
- **验证结果**：单测 `tests/test_phase3_voice_and_extractor.py` 5 项全绿，Git commit `ab83c83`。

---

### 第四阶段（Phase 4 - P3）：多平台矩阵自动发布与去重微混淆（已交付）
- **交付内容**：
  - `compositors/anti_duplicate.py`：视频抗查重微混淆引擎（1%~2% 中心微裁切、0.99x~1.01x 速度扰动、画面明度对比度抖动、编码元数据清洗打散）；
  - `publishers/`：抖音、B站、小红书、微信视频号四大自媒体发布适配器及 `PublishManager` 调度管理器；
  - Web Studio 多平台矩阵分发模态窗、发布历史记录与抗查重开关。
- **验证结果**：单测 `tests/test_phase4_publishing.py` 4 项全绿，全量 31 项测试全部通过，Git commit `c846af7`。
