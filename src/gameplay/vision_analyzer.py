import asyncio
import json
import base64
from typing import Optional
import numpy as np
from src.config import config


class VisionAnalyzer:
    def __init__(self):
        self.provider = config.vision.provider
        self.model = config.vision.model
        self.api_key = config.vision.api_key
        self._client = None

    async def analyze_frame(self, frame: np.ndarray, context: Optional[str] = None) -> dict:
        if self.provider == "openai":
            return await self._analyze_openai(frame, context)
        elif self.provider == "anthropic":
            return await self._analyze_anthropic(frame, context)
        elif self.provider == "ollama":
            return await self._analyze_ollama(frame, context)
        else:
            raise ValueError(f"Unknown vision provider: {self.provider}")

    def _encode_frame(self, frame: np.ndarray) -> str:
        from PIL import Image
        import io

        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    async def _analyze_openai(self, frame: np.ndarray, context: Optional[str] = None) -> dict:
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)

        b64 = self._encode_frame(frame)
        prompt = config.vision.prompt_template
        if context:
            prompt = f"{prompt}\n\nVoice context from player: {context}"

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
            ),
        )

        return json.loads(response.choices[0].message.content)

    async def _analyze_anthropic(self, frame: np.ndarray, context: Optional[str] = None) -> dict:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)

        b64 = self._encode_frame(frame)
        prompt = config.vision.prompt_template
        if context:
            prompt = f"{prompt}\n\nVoice context from player: {context}"

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                        ],
                    }
                ],
            ),
        )

        text = response.content[0].text
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {"raw_analysis": text}

    async def _analyze_ollama(self, frame: np.ndarray, context: Optional[str] = None) -> dict:
        import aiohttp

        b64 = self._encode_frame(frame)
        prompt = config.vision.prompt_template
        if context:
            prompt = f"{prompt}\n\nVoice context from player: {context}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model or "llava",
                    "prompt": prompt,
                    "images": [b64],
                    "stream": False,
                    "format": "json",
                },
            ) as resp:
                result = await resp.json()
                try:
                    return json.loads(result.get("response", "{}"))
                except json.JSONDecodeError:
                    return {"raw_analysis": result.get("response", "")}

    async def extract_game_title(self, frame: np.ndarray) -> str:
        import aiohttp

        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)

        b64 = self._encode_frame(frame)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "What video game is this? Return ONLY the game title "
                                    "as a plain string. No explanation. If you can't tell, "
                                    'return "unknown".'
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=50,
            ),
        )

        return response.choices[0].message.content.strip().strip('"').strip("'")
