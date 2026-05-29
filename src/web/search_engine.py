import asyncio
import json
from typing import Optional
from src.config import config


class WebSearch:
    def __init__(self):
        self.provider = config.web_search.provider
        self.api_key = config.web_search.api_key
        self.search_engine_id = config.web_search.search_engine_id

    async def search(self, query: str, num_results: int = 5) -> list[dict]:
        if self.provider == "google":
            return await self._search_google(query, num_results)
        elif self.provider == "bing":
            return await self._search_bing(query, num_results)
        elif self.provider == "searxng":
            return await self._search_searxng(query, num_results)
        else:
            raise ValueError(f"Unknown search provider: {self.provider}")

    async def _search_google(self, query: str, num_results: int) -> list[dict]:
        import aiohttp

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": min(num_results, 10),
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return [{"error": f"Search failed: {resp.status}", "query": query}]
                data = await resp.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "google",
            })

        return results

    async def _search_bing(self, query: str, num_results: int) -> list[dict]:
        import aiohttp

        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": num_results, "mkt": "en-US"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return [{"error": f"Bing search failed: {resp.status}", "query": query}]
                data = await resp.json()

        results = []
        for item in data.get("webPages", {}).get("value", []):
            results.append({
                "title": item.get("name", ""),
                "link": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "source": "bing",
            })

        return results

    async def _search_searxng(self, query: str, num_results: int) -> list[dict]:
        import aiohttp

        url = f"{config.web_search.endpoint or 'http://localhost:8888'}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
            "pageno": 1,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return [{"error": f"SearXNG failed: {resp.status}", "query": query}]
                data = await resp.json()

        results = []
        for item in data.get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "link": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "searxng",
            })

        return results

    async def search_walkthrough(self, game: str, topic: str) -> list[dict]:
        queries = [
            f"{game} walkthrough {topic}",
            f"{game} guide {topic}",
            f"{game} how to {topic}",
            f"{game} tips {topic}",
            f"{game}攻略 {topic}" if any("\u4e00" <= c <= "\u9fff" for c in game) else None,
        ]
        queries = [q for q in queries if q]

        all_results = []
        for q in queries[:3]:
            results = await self.search(q)
            all_results.extend(results)
            await asyncio.sleep(0.5)

        seen = set()
        unique = []
        for r in all_results:
            if r["link"] not in seen:
                seen.add(r["link"])
                unique.append(r)

        return unique[:config.web_search.max_results]
