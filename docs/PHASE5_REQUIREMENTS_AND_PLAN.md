# Phase 5（进阶进化）：视听大片感、全局风格一致性与合规风控安全闭环

本文档为 AI Traffic Pipeline 系统的阶段五进阶需求与技术实现设计书。

---

## 一、 核心痛点与本阶段解决方案

| 维度 | 当前痛点 | 本阶段解决方案 |
| :--- | :--- | :--- |
| **文案与安全风控** | 1. 存在广告法违禁词（“最、第一、唯一”）风险<br>2. 平台敏感词容易引发限流或下架 | **违禁词检测与大模型语义合规平替引擎 (`safety/compliance_guard.py`)**：<br>实时扫描高危词，一键自动平替为合规用语，前端可视化标红合规检查。 |
| **视觉与生图质感** | 1. 各分镜 AI 配图风格割裂（写实/动漫/3D混杂）<br>2. 本土意象在海外图库中容易检索失真 | **全局视觉艺术风格一致性系统 (`media/style_presets.py`)**：<br>引入 6 大电影级风格预设（暗黑胶片/赛博霓虹/现代极简/新海诚动漫/新中式国潮/复古港风），整片统一色彩与材质种子；针对本土名词智能翻译映射。 |
| **剪辑节奏与渲染** | 1. 静态图运镜缺乏卡点冲击力<br>2. CPU 软解渲染长视频耗时较长 | **重音卡点运镜微震动 + 硬件加速编码 (`compositors/moviepy_renderer.py`)**：<br>在关键词与镜头开头注入微缩放快回弹（Punch-in Bounce 1.05x）；智能探测 NVENC/QSV 硬件加速，大幅缩短导出耗时。 |

---

## 二、 详细实施计划与模块拆解

### 任务 1：合规风控审查与敏感词语义平替系统 (Milestone 5.1)
- **新建模块 `safety/compliance_guard.py`**：
  - 构建多级风控词典：
    - `ad_law`: 广告法高危绝对化用语（“最、第一、顶级、唯一、极致、绝对”等）；
    - `platform_sensitive`: 抖音/微信/小红书容易被判定夸大诱导词（“必赚、稳赚、暴富、内部绝密、躺赚、100%”等）；
    - `vulgar_misleading`: 低俗/引发焦虑过度营销词。
  - 核心方法：
    - `ComplianceGuard.scan(text: str) -> ComplianceScanResult`：返回命中词列表、风险等级（高/中/低）及位置索引；
    - `ComplianceGuard.auto_sanitize(text: str) -> str`：调用启发式映射或大模型，将违规用语智能无缝平替为平台合规表述（例如将“这是全网最好用的方法”平替为“这是被很多人验证过的实用方法”）。
  - **API 与前端打通**：
    - 新增 `POST /api/compliance/scan` 与 `POST /api/compliance/sanitize`；
    - 在脚本生成后自动触发合规扫描，并在前端文案编辑框中高亮显示合规状态徽章。

---

### 任务 2：全局电影级视觉风格一致性引擎 (Milestone 5.2)
- **新建模块 `media/style_presets.py`**：
  - 定义 6 种工业级短视频视觉风格 Profile：
    1. **`cinematic_dark` (暗黑电影胶片)**：`Kodak Vision3 500T, 35mm film grain, moody cinematic lighting, shallow depth of field, anamorphic lens`；
    2. **`cyberpunk_neon` (赛博朋克霓虹)**：`Blade Runner aesthetics, vibrant magenta and cyan neon glow, wet asphalt reflections, futuristic`；
    3. **`minimalist_tech` (极简商业科技)**：`Apple commercial style, clean studio lighting, soft natural diffusion, premium minimalist interior`；
    4. **`vintage_retro` (复古港风胶片)**：`90s Hong Kong movie aesthetic, warm nostalgic color grading, soft vintage bloom, Kodak Portra 400`；
    5. **`anime_shinkai` (唯美新海诚风)**：`Makoto Shinkai anime style, vibrant dramatic clouds, golden hour sunset, hyper-detailed painterly`；
    6. **`chinese_traditional` (新中式国潮风)**：`Modern neo-Chinese aesthetics, Song dynasty subtle elegance, minimalist ink wash textures, zen atmospheric lighting`。
- **改造 `writers/prompts.py` 与 `media/ai_image_gen.py`**：
  - 脚本生成时，根据用户选定的全局视觉风格，统一下发到每一个分镜的 `image_prompt`；
  - AI 生图时动态注入该风格的基准负向提示词与采样修饰词，保证整部视频所有画面的光影、色调、材质完全统一；
  - 增加本土实体意象中英智能映射器（如“外卖骑手”映射为 `food delivery courier riding electric scooter in rain`）。

---

### 任务 3：卡点运镜微弹跳与硬件加速渲染 (Milestone 5.3)
- **升级 `compositors/moviepy_renderer.py`**：
  - **卡点微弹跳 (Punch-in Bounce)**：
    - 在分镜开头 0.3 秒内施加 1.0 ➔ 1.06 ➔ 1.02 的弹性缩放回弹微动效，配合转场 Whoosh 音效形成短视频卡点爆破感；
  - **硬件加速探测 (Hardware Accelerated Encoding)**：
    - 运行时自动检测 FFmpeg 是否支持 `h264_nvenc`（NVIDIA显卡）或 `h264_qsv`（Intel核显）；
    - 若支持硬件编码，渲染参数自动切换为硬件编码流，导出速度提升 3~5 倍；若为纯 CPU 环境，自动优化线程池与 `-preset veryfast`。
- **前端工作台联动**：
  - 在版式与渲染配置栏新增“视觉风格 (Art Style)”下拉选择器与“导出编码加速模式”切换。

---

## 三、 实施阶段编排 (Execution Steps)

1. **Step 1**: 实现 `safety/compliance_guard.py`，建立风控词库、合规扫描器与自动平替器，编写单元测试 `tests/test_compliance_guard.py`；
2. **Step 2**: 实现 `media/style_presets.py`，升级 `ai_image_gen.py` 与 `script_generator.py` 的全局美术风格注入；
3. **Step 3**: 升级 `compositors/moviepy_renderer.py` 实现卡点弹性运镜与硬件加速兼容；
4. **Step 4**: 升级 `web_studio/server.py` 与 `web_studio/templates/index.html`，接入合规检测按钮、艺术风格下拉框与卡点动效开关；
5. **Step 5**: 编写回归测试套件 `tests/test_phase5_enhancements.py`，执行 `ruff check` 与全量测试验证，并交付提交。
