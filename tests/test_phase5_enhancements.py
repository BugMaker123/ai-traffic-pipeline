"""
Phase 5 进阶增强功能单元测试套件
涵盖：文案合规风控审查与自动平替、全局艺术风格一致性、本土实体映射、卡点微弹跳与硬件编码探测。
"""
from __future__ import annotations

from safety.compliance_guard import compliance_guard
from media.style_presets import style_manager, STYLE_PROFILES
from writers.script_generator import ScriptGenerator
from compositors.moviepy_renderer import MoviePyRenderer


def test_compliance_guard_detection_and_sanitize():
    """测试广告法极限词、自媒体暴富诱导词扫描与智能平替"""
    dirty_text = "这是全网最好用的赚钱神器，稳赚不赔，让你轻松躺赚，绝对有效！"
    res = compliance_guard.scan(dirty_text)

    assert not res.is_compliant
    assert res.risk_level == "high"
    assert res.total_issues >= 4
    words = [m.word for m in res.matches]
    assert "全网最好" in words or "最好" in words
    assert "稳赚不赔" in words
    assert "躺赚" in words
    assert "绝对有效" in words or "绝对" in words

    # 验证平替后已无高危词
    clean_text = res.sanitized_text
    assert "全网最好" not in clean_text
    assert "稳赚不赔" not in clean_text
    assert "躺赚" not in clean_text
    assert "绝对有效" not in clean_text

    # 再次扫描平替后的文本应为合规
    res2 = compliance_guard.scan(clean_text)
    assert res2.is_compliant


def test_style_preset_manager_profiles():
    """测试 6 大电影级艺术风格预设及提示词增强"""
    styles = style_manager.list_styles()
    assert len(styles) == 6
    style_ids = [s["id"] for s in styles]
    assert "cinematic_dark" in style_ids
    assert "cyberpunk_neon" in style_ids
    assert "minimalist_tech" in style_ids
    assert "vintage_retro" in style_ids
    assert "anime_shinkai" in style_ids
    assert "chinese_traditional" in style_ids

    # 测试提示词增强与 9:16 注入
    enhanced = style_manager.enhance_prompt("a man thinking in cafe", style_id="cyberpunk_neon")
    assert "9:16 vertical composition" in enhanced
    assert "Blade Runner" in enhanced or "neon glow" in enhanced


def test_localized_entity_mapping():
    """测试中式本土特色实体映射为国际化图库精准检索词"""
    map_res1 = style_manager.map_localized_keywords("外卖骑手下雨天工作")
    assert map_res1 is not None
    assert "delivery courier" in map_res1 or "scooter" in map_res1

    map_res2 = style_manager.map_localized_keywords("大学门口的烧烤摊")
    assert map_res2 is not None
    assert "barbecue" in map_res2 or "street food" in map_res2


def test_script_generator_with_art_style_and_compliance():
    """测试剧本生成器注入全局艺术风格并自动执行合规风控"""
    gen = ScriptGenerator(api_key="")  # 使用 fallback 模式
    script = gen.generate_script(
        topic_or_content="自律改变生活，全网最好的绝密指南",
        style="干货科普",
        art_style="anime_shinkai",
    )

    assert script.project_id is not None
    assert len(script.scenes) >= 4
    # 标题中的“全网最好”应已被合规平替
    assert "全网最好" not in script.title

    # 分镜中的 image_prompt 均注入了新海诚动漫风格
    for sc in script.scenes:
        assert "anime" in sc.image_prompt.lower() or "shinkai" in sc.image_prompt.lower() or "9:16" in sc.image_prompt


def test_moviepy_renderer_hwaccel_and_camera_motion():
    """测试硬件编码器自动探测机制与运镜函数兼容性"""
    codec = MoviePyRenderer.detect_hwaccel_codec()
    assert codec in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_mf")

    # 验证带 punch_in 的相机动态推拉
    renderer = MoviePyRenderer()
    import inspect
    sig = inspect.signature(renderer._add_camera_motion)
    assert "enable_punch_in" in sig.parameters
    assert sig.parameters["enable_punch_in"].default is True


def test_phase5_api_endpoints():
    """测试 Web Studio 阶段五新增加的 API 路由"""
    from fastapi.testclient import TestClient
    from web_studio.server import app

    client = TestClient(app)

    # 1. GET /api/art_styles
    r = client.get("/api/art_styles")
    assert r.status_code == 200
    styles = r.json().get("styles", [])
    assert len(styles) == 6

    # 2. POST /api/compliance/scan
    r = client.post("/api/compliance/scan", json={"text": "这套投资方法稳赚不赔，百分之百实现财务自由！"})
    assert r.status_code == 200
    data = r.json()
    assert not data["is_compliant"]
    assert data["risk_level"] == "high"
    assert "稳赚不赔" in [m["word"] for m in data["matches"]]

    # 3. POST /api/compliance/sanitize
    r = client.post("/api/compliance/sanitize", json={"text": "这套投资方法稳赚不赔，百分之百实现财务自由！"})
    assert r.status_code == 200
    clean = r.json().get("sanitized_text", "")
    assert "稳赚不赔" not in clean
    assert "百分之百" not in clean
