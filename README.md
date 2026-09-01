# AI Traffic Pipeline

从热点或自定义主题生成分镜、语音、字幕、竖屏素材、MP4 和剪映草稿的 Python 工作流。

## 安全提醒

旧版 `.env.example` 曾包含疑似真实的 DeepSeek 与 Pexels 凭据。请在对应控制台立即撤销旧凭据并生成新 Key；修改本地文件不能撤销已经泄露的密钥。`.env` 仅供本机使用，禁止提交。

## 独立环境

需要 Python 3.11 和 FFmpeg。Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.lock
Copy-Item .env.example .env
```

填写 `.env` 后运行：

```powershell
.\.venv\Scripts\python main.py --help
.\.venv\Scripts\python main.py --web
```

Web 渲染采用后台任务：`POST /api/jobs` 创建任务，`GET /api/jobs/{job_id}` 查询进度，`POST /cancel` 协作式取消，失败或服务重启中断后可调用 `POST /retry` 恢复。任务状态保存在 `output/jobs`。

访问 `/tasks` 可查看跨项目任务历史、阶段耗时和完整日志。TTS 与素材抓取默认各 3 路并发，可通过 `TTS_CONCURRENCY`、`MEDIA_FETCH_CONCURRENCY` 调整；视频渲染本身仍由 `MAX_RENDER_JOBS` 控制，避免多个编码任务争抢 CPU。

## 真实素材与自然语音

每个分镜都保留可编辑的英文素材关键词。素材顺序为 Pexels 竖屏视频、Pexels 竖屏图片、精选 Unsplash 摄影图片，最后才是本地背景；任务日志会记录实际来源。要启用 Pexels，请将新 Key 写入本地 `.env` 的 `PEXELS_API_KEY`，页面顶部会显示连接状态。

默认语音改为自然语速 `+0%` 和轻微降调 `-2Hz`，工作台可选择舒缓、自然或轻快节奏。不要重新使用已经公开过的旧 Key。

## 验证

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
```

默认测试不访问外网；真实 LLM、Pexels、TTS 与视频渲染测试标记为 `integration`，需要显式执行 `pytest -m integration`。

## 产物管理

产物位于 `output`。服务启动时会删除超过 `OUTPUT_RETENTION_HOURS` 的媒体文件，但保留任务 JSON；默认保留 72 小时。草稿打开接口只允许后端推导出的 `output/drafts/{project_id}_jianying_draft` 路径。
