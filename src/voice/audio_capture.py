import asyncio
import wave
import numpy as np
from pathlib import Path
from typing import Optional, AsyncGenerator
from src.config import config


class AudioCapture:
    def __init__(self):
        self.sample_rate = config.audio.sample_rate
        self.channels = config.audio.channels
        self.chunk_duration = config.audio.chunk_duration_sec
        self.recording = False
        self._stream = None
        self._p = None

    async def capture_from_mic(self, duration: Optional[float] = None) -> np.ndarray:
        import pyaudio as pa

        chunk_sec = duration or self.chunk_duration
        frames_per_buffer = int(self.sample_rate * chunk_sec)

        self._p = pa.PyAudio()
        stream = self._p.open(
            format=pa.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=frames_per_buffer,
        )

        self.recording = True
        frames = []

        num_chunks = 1
        for _ in range(num_chunks):
            data = await asyncio.get_event_loop().run_in_executor(
                None, stream.read, frames_per_buffer
            )
            frames.append(np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0)

        stream.stop_stream()
        stream.close()
        self._p.terminate()
        self.recording = False

        return np.concatenate(frames)

    async def capture_stream(self, stream_url: str) -> AsyncGenerator[np.ndarray, None]:
        import subprocess
        import tempfile

        cmd = [
            "ffmpeg", "-i", stream_url,
            "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1", "-",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        chunk_bytes = self.sample_rate * 2 * int(self.chunk_duration)

        while True:
            data = await proc.stdout.read(chunk_bytes)
            if not data:
                break
            yield np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    async def detect_speech(self, audio: np.ndarray) -> bool:
        return np.max(np.abs(audio)) > config.audio.silence_threshold

    async def save_audio(self, audio: np.ndarray, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        audio_int16 = (audio * 32768.0).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_int16.tobytes())
