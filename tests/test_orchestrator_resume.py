from core import orchestrator


def test_runner_resumes_after_script_checkpoint(monkeypatch):
    called = []

    def node(name, status):
        def run(state):
            called.append(name)
            return {"status": status}
        return run

    monkeypatch.setattr(orchestrator, "node_topic_mining", node("topic", "topic_ready"))
    monkeypatch.setattr(orchestrator, "node_script_writing", node("script", "scripted"))
    monkeypatch.setattr(orchestrator, "node_audio_and_subtitles", node("audio", "audio_ready"))
    monkeypatch.setattr(orchestrator, "node_media_sourcing", node("media", "media_ready"))
    monkeypatch.setattr(orchestrator, "node_video_compositing", node("video", "rendered"))

    checkpoints = []
    result = orchestrator.VideoPipelineRunner.run(
        resume_state={"project_id": "proj_test", "status": "scripted", "logs": []},
        checkpoint_callback=lambda state: checkpoints.append(state["status"]),
    )

    assert called == ["audio", "media", "video"]
    assert checkpoints == ["audio_ready", "media_ready", "rendered"]
    assert result["status"] == "rendered"
