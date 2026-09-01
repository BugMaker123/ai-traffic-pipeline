import pytest
from pydantic import ValidationError

from core.state import SceneItem, VideoProjectScript
from web_studio.server import RenderRequest


def test_scene_rejects_empty_voiceover():
    with pytest.raises(ValidationError):
        SceneItem(scene_index=1, voiceover_text="", visual_keywords=[])


def test_render_request_rejects_unknown_fields_and_invalid_project_id():
    with pytest.raises(ValidationError):
        RenderRequest(
            project_id="../../unsafe",
            title="测试",
            scenes=[{"scene_index": 1, "voiceover_text": "台词", "unknown": True}],
        )


def test_video_project_round_trip():
    project = VideoProjectScript(
        project_id="proj_test",
        title="标题",
        topic_summary="概要",
        scenes=[{"scene_index": 1, "voiceover_text": "台词", "visual_keywords": []}],
    )
    assert VideoProjectScript.model_validate(project.model_dump()) == project
