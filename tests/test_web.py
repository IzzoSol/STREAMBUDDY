import pytest
from src.web import WebSearch, RedditScraper, WikiScraper


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_search_walkthrough_no_api_key(self):
        search = WebSearch()
        results = await search.search_walkthrough("Elden Ring", "how to beat Malenia")
        assert isinstance(results, list)
