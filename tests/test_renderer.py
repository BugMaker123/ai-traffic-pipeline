import numpy as np
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
