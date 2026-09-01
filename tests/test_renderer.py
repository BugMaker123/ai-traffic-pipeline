import numpy as np
import pytest
from moviepy import ImageClip

from compositors.moviepy_renderer import MoviePyRenderer


def test_cover_clip_preserves_aspect_and_fills_frame():
    renderer = MoviePyRenderer(width=108, height=192, fps=1)
    clip = ImageClip(np.zeros((90, 160, 3), dtype=np.uint8)).with_duration(0.1)
    covered = renderer._cover_clip(clip)
    try:
        assert tuple(covered.size) == (108, 192)
    finally:
        covered.close()
        clip.close()


def test_validate_output_rejects_incomplete_file(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"partial")
    with pytest.raises(RuntimeError, match="不完整"):
        MoviePyRenderer.validate_output(broken)
