import asyncio
import json
import logging
import re
from typing import Optional, Callable

import aiohttp

from src.orchestrator import GameAssistOrchestrator

logger = logging.getLogger(__name__)


class YouTubeStreamIntegration:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.orch = GameAssistOrchestrator()
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def get_live_streams(self, channel_id: str) -> list[dict]:
        await self._ensure_session()
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "eventType": "live",
            "type": "video",
            "key": self.api_key,
        }
        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("items", [])

    async def get_live_chat_messages(self, video_id: str, page_token: str = "") -> tuple[list[dict], str]:
        await self._ensure_session()
        url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
        params = {
            "part": "snippet,authorDetails",
            "liveChatId": video_id,
            "key": self.api_key,
            "maxResults": 200,
        }
        if page_token:
            params["pageToken"] = page_token

        async with self._session.get(url, params=params) as resp:
            data = await resp.json()
            items = data.get("items", [])
            next_token = data.get("nextPageToken", "")
            polling_msec = data.get("pollingIntervalMillis", 5000)

            parsed = []
            for item in items:
                parsed.append({
                    "author": item["authorDetails"]["displayName"],
                    "message": item["snippet"]["displayMessage"],
                    "published_at": item["snippet"]["publishedAt"],
                    "type": item["snippet"]["type"],
                })
            return parsed, next_token, polling_msec

    async def monitor_chat(self, video_id: str, callback: Optional[Callable] = None):
        self._running = True
        logger.info(f"Starting YouTube chat monitor for video {video_id}")

        next_page = ""
        polling = 5000

        while self._running:
            try:
                messages, next_page, polling = await self.get_live_chat_messages(video_id, next_page)

                for msg in messages:
                    if msg["type"] != "textMessage":
                        continue

                    text = msg["message"]
                    author = msg["author"]

                    if self._is_help_request(text):
                        logger.info(f"YouTube help from {author}: {text}")
                        result = await self.orch.process_text_query(text)

                        reply = f"@{author} {result.answer[:200]}"
                        if callback:
                            await callback(author, text, reply)

                await asyncio.sleep(polling / 1000)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"YouTube monitor error: {e}")
                await asyncio.sleep(10)

    def _is_help_request(self, message: str) -> bool:
        keywords = [
            "how do i", "how to", "where is", "help", "stuck",
            "walkthrough", "guide", "tips", "what do i do",
            "how do i beat", "strategy", "!help",
        ]
        msg = message.lower()
        return any(kw in msg for kw in keywords)

    def stop(self):
        self._running = False
        logger.info("YouTube monitor stopped")
