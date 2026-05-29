import asyncio
import json
from typing import Optional
import numpy as np
from src.config import config


class SpeechToText:
    def __init__(self):
        self.provider = config.stt.provider
        self.model_name = config.stt.model
        self.api_key = config.stt.api_key
        self._whisper_model = None
        self._client = None

    async def transcribe(self, audio: np.ndarray, language: Optional[str] = None) -> str:
        if self.provider == "whisper":
            return await self._transcribe_whisper(audio, language)
        elif self.provider == "openai":
            return await self._transcribe_openai(audio, language)
        elif self.provider == "google":
            return await self._transcribe_google(audio, language)
        else:
            raise ValueError(f"Unknown STT provider: {self.provider}")

    async def _transcribe_whisper(self, audio: np.ndarray, language: Optional[str] = None) -> str:
        try:
            import whisper
        except ImportError:
            raise ImportError(
                "openai-whisper not installed. Run: pip install openai-whisper"
            )

        if self._whisper_model is None:
            self._whisper_model = await asyncio.get_event_loop().run_in_executor(
                None, whisper.load_model, self.model_name
            )

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._whisper_model.transcribe(
                audio,
                language=language or config.stt.language,
                fp16=False,
            ),
        )
        return result["text"].strip()

    async def _transcribe_openai(self, audio: np.ndarray, language: Optional[str] = None) -> str:
        import tempfile
        import soundfile as sf
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(api_key=self.api_key or config.vision.api_key)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, config.audio.sample_rate)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcript = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language=language or config.stt.language,
                    ),
                )
            return transcript.text.strip()
        finally:
            import os
            os.unlink(tmp_path)

    async def _transcribe_google(self, audio: np.ndarray, language: Optional[str] = None) -> str:
        from google.cloud.speech import SpeechClient, RecognitionConfig, RecognitionAudio

        client = SpeechClient()
        audio_bytes = (audio * 32768.0).astype(np.int16).tobytes()

        config_obj = RecognitionConfig(
            encoding=RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=config.audio.sample_rate,
            language_code=language or "en-US",
        )
        audio_obj = RecognitionAudio(content=audio_bytes)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.recognize(config=config_obj, audio=audio_obj),
        )

        return " ".join(r.alternatives[0].transcript for r in response.results).strip()

    async def detect_help_request(self, text: str) -> tuple[bool, str]:
        keywords = [
            "how do i", "how to", "where is", "what is",
            "help", "stuck", "can't find", "need help",
            "walkthrough", "guide", "tutorial", "what do i do",
            "where do i go", "how do i beat", "how do i get",
            "strategy", "tips", "advice", "recommendation",
            "best way", "what should i", "i'm stuck",
        ]

        text_lower = text.lower()
        for kw in keywords:
            if kw in text_lower:
                return True, kw

        return False, ""

    async def extract_game_context(self, text: str) -> dict:
        contexts = {
            "combat": ["boss", "enemy", "fight", "attack", "damage", "kill", "defeat", "battle"],
            "exploration": ["where", "find", "location", "area", "map", "hidden", "secret"],
            "quest": ["quest", "mission", "objective", "task", "side quest"],
            "crafting": ["craft", "crafting", "build", "create", "make", "recipe"],
            "loot": ["loot", "item", "weapon", "armor", "gear", "equipment", "drop"],
            "puzzle": ["puzzle", "riddle", "solve", "solution", "code", "lock"],
            "skill": ["skill", "ability", "upgrade", "level", "perk", "talent"],
            "navigation": ["path", "door", "entrance", "exit", "stuck", "blocked"],
        }

        text_lower = text.lower()
        detected = []
        for category, keywords in contexts.items():
            if any(kw in text_lower for kw in keywords):
                detected.append(category)

        return {
            "categories": detected,
            "is_help_request": any(
                kw in text_lower
                for kw in ["how", "help", "stuck", "what", "where", "guide", "walkthrough"]
            ),
        }
