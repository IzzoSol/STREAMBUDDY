import pytest
import numpy as np
from src.gameplay import ScreenCapture, VisionAnalyzer


class TestScreenCapture:
    @pytest.mark.asyncio
    async def test_capture_frame_pil(self):
        screen = ScreenCapture()
        screen.capture_driver = "pil"
        screen.region = (0, 0, 100, 100)
        frame = await screen.capture_frame()
        assert frame is not None
        assert frame.shape == (100, 100, 3)
