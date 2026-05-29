import asyncio
from typing import Optional
from src.config import config


class RedditScraper:
    def __init__(self):
        self.client_id = config.reddit.client_id
        self.client_secret = config.reddit.client_secret
        self.user_agent = config.reddit.user_agent
        self.subreddits = config.reddit.subreddits
        self._reddit = None

    async def _get_client(self):
        if self._reddit is None:
            import asyncpraw

            self._reddit = asyncpraw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
        return self._reddit

    async def search_game_tips(self, game: str, topic: str, limit: int = 10) -> list[dict]:
        reddit = await self._get_client()
        results = []

        query = f"{game} {topic}"

        for subreddit_name in self.subreddits:
            try:
                subreddit = await reddit.subreddit(subreddit_name)
                async for submission in subreddit.search(query, limit=limit // len(self.subreddits)):
                    results.append({
                        "title": submission.title,
                        "text": submission.selftext[:500] if submission.selftext else "",
                        "url": f"https://reddit.com{submission.permalink}",
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "subreddit": subreddit_name,
                        "source": "reddit",
                    })
                await asyncio.sleep(0.3)
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def search_walkthrough_posts(self, game: str, topic: str) -> list[dict]:
        reddit = await self._get_client()
        results = []

        specific_subs = ["walkthrough", "gameguides", "gamingsuggestions"]
        for sub in specific_subs:
            try:
                subreddit = await reddit.subreddit(sub)
                query = f"{game} {topic}"
                async for post in subreddit.search(query, limit=5, sort="relevance"):
                    results.append({
                        "title": post.title,
                        "text": post.selftext[:500] if post.selftext else "",
                        "url": f"https://reddit.com{post.permalink}",
                        "score": post.score,
                        "source": "reddit_walkthrough",
                    })
            except Exception:
                continue

        return results
