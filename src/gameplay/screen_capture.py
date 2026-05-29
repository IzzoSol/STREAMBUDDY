import asyncio
import numpy as np
from pathlib import Path
from typing import Optional, AsyncGenerator
from src.config import config


class ScreenCapture:
    def __init__(self):
        self.fps = config.screen.fps
        self.region = config.screen.region
        self.window_title = config.screen.window_title
        self.capture_driver = config.screen.capture_driver
        self._capturer = None

    async def capture_frame(self) -> np.ndarray:
        if self.capture_driver == "dxcam":
            return await self._capture_dxcam()
        elif self.capture_driver == "mss":
            return await self._capture_mss()
        elif self.capture_driver == "pil":
            return await self._capture_pil()
        else:
            raise ValueError(f"Unknown capture driver: {self.capture_driver}")

    async def _capture_dxcam(self) -> np.ndarray:
        import dxcam

        if self._capturer is None:
            self._capturer = dxcam.create(
                output_color="RGB",
                max_buffer_len=4,
            )
            if self.region:
                self._capturer.start(target_fps=self.fps, region=self.region)
            else:
                self._capturer.start(target_fps=self.fps)

        frame = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._capturer.get_latest_frame(),
        )

        if frame is None:
            frame = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._capturer.grab(self.region),
            )

        return frame

    async def _capture_mss(self) -> np.ndarray:
        import mss

        with mss.mss() as sct:
            monitor = self.region or sct.monitors[1]
            screenshot = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: sct.grab(monitor),
            )
            return np.array(screenshot)[:, :, :3]

    async def _capture_pil(self) -> np.ndarray:
        from PIL import ImageGrab

        bbox = self.region
        screenshot = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: ImageGrab.grab(bbox=bbox),
        )
        return np.array(screenshot)[:, :, :3]

    async def capture_frames_stream(self) -> AsyncGenerator[np.ndarray, None]:
        while True:
            frame = await self.capture_frame()
            if frame is not None:
                yield frame
            await asyncio.sleep(1.0 / self.fps)

    async def save_frame(self, frame: np.ndarray, path: str | Path):
        from PIL import Image

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.fromarray(frame)
        await asyncio.get_event_loop().run_in_executor(
            None, img.save, str(path)
        )
