import asyncio
import re
from typing import Optional
from src.config import config


class WikiScraper:
    def __init__(self):
        self.enabled_sources = config.wiki.enabled_sources

    async def search_wiki(self, game: str, topic: str) -> list[dict]:
        tasks = []
        if "fextralife" in self.enabled_sources:
            tasks.append(self._search_fextralife(game, topic))
        if "fandom" in self.enabled_sources:
            tasks.append(self._search_fandom(game, topic))
        if "ign_wikis" in self.enabled_sources:
            tasks.append(self._search_ign(game, topic))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_results = []
        for r in results:
            if isinstance(r, list):
                all_results.extend(r)

        return all_results

    async def _search_fextralife(self, game: str, topic: str) -> list[dict]:
        import aiohttp

        game_slug = game.lower().replace(" ", "-").replace(":", "").replace("'", "")
        url = f"https://{game_slug}.wiki.fextralife.com"
        search_url = f"https://www.fextralife.com/?s={topic}+{game}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url, timeout=10) as resp:
                    if resp.status != 200:
                        return []
                    html = await resp.text()

                links = re.findall(r'href="(https?://[^"]*fextralife[^"]*)"', html)
                results = []
                for link in links[:5]:
                    results.append({
                        "title": "Fextralife Wiki",
                        "link": link,
                        "snippet": f"{game} - {topic} guide",
                        "source": "fextralife",
                    })
                return results
            except Exception:
                return []

    async def _search_fandom(self, game: str, topic: str) -> list[dict]:
        import aiohttp

        game_slug = game.lower().replace(" ", "").replace(":", "").replace("'", "")
        api_url = f"https://{game_slug}.fandom.com/api.php"

        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{topic} walkthrough guide",
            "format": "json",
            "srlimit": 5,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

                results = []
                for item in data.get("query", {}).get("search", []):
                    title = item.get("title", "")
                    page_id = item.get("pageid", "")
                    results.append({
                        "title": title,
                        "link": f"https://{game_slug}.fandom.com/wiki/{title.replace(' ', '_')}",
                        "snippet": item.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", ""),
                        "source": "fandom",
                    })
                return results
            except Exception:
                return []

    async def _search_ign(self, game: str, topic: str) -> list[dict]:
        import aiohttp

        search_url = "https://www.ign.com/search"
        params = {"q": f"{game} {topic} walkthrough", "count": 5}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        return []
                    html = await resp.text()

                links = re.findall(r'href="(https?://www\.ign\.com/wikis/[^"]*)"', html)
                results = []
                for link in links[:5]:
                    results.append({
                        "title": "IGN Wiki",
                        "link": link,
                        "snippet": f"{game} - {topic} walkthrough",
                        "source": "ign",
                    })
                return results
            except Exception:
                return []
