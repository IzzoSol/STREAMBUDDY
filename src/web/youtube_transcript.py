import asyncio
import json
import logging
import re
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class YouTubeTranscriptFinder:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def search_guides(self, game: str, query: str = "", max_results: int = 5) -> list[dict]:
        await self._ensure_session()
        search_query = f"{game} {query} walkthrough guide tips" if query else f"{game} walkthrough guide"
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": search_query,
            "type": "video",
            "maxResults": max_results,
            "key": self.api_key,
            "relevanceLanguage": "en",
        }
        try:
            async with self._session.get(url, params=params) as resp:
                data = await resp.json()
                items = data.get("items", [])
                results = []
                for item in items:
                    video_id = item["id"]["videoId"]
                    snippet = item["snippet"]
                    results.append({
                        "video_id": video_id,
                        "title": snippet["title"],
                        "channel": snippet["channelTitle"],
                        "description": snippet["description"][:200],
                        "thumbnail": snippet["thumbnails"].get("high", {}).get("url", ""),
                        "published_at": snippet["publishedAt"],
                        "url": f"https://youtube.com/watch?v={video_id}",
                    })
                return results
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return []

    async def get_transcript(self, video_id: str) -> Optional[list[dict]]:
        try:
            import youtube_transcript_api
            transcript_list = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: youtube_transcript_api.get_transcript(video_id, languages=["en"]),
            )
            return transcript_list
        except ImportError:
            logger.warning("youtube_transcript_api not installed")
            return None
        except Exception as e:
            logger.warning(f"Transcript fetch error for {video_id}: {e}")
            return None

    def extract_guide_content(self, transcript: list[dict], keywords: list[str] = None) -> str:
        if not transcript:
            return ""
        if not keywords:
            return " ".join(entry["text"] for entry in transcript[:500])

        relevant_snippets = []
        for entry in transcript:
            text = entry["text"].lower()
            if any(kw.lower() in text for kw in keywords):
                relevant_snippets.append(entry["text"])

        return " ".join(relevant_snippets[:50]) if relevant_snippets else ""

    async def find_guide_for_boss(self, game: str, boss: str) -> Optional[dict]:
        guides = await self.search_guides(game, f"{boss} boss fight how to beat", max_results=3)
        if not guides:
            return None

        best = guides[0]
        transcript = await self.get_transcript(best["video_id"])
        if transcript:
            boss_keywords = [boss, "phase", "attack", "weakness", "strategy", "beat", "defeat", "dodge"]
            guide_text = self.extract_guide_content(transcript, boss_keywords)
            if guide_text:
                best["guide_snippets"] = guide_text[:1500]
            else:
                best["guide_snippets"] = ""
        else:
            best["guide_snippets"] = ""
        return best
