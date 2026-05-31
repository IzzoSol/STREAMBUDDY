import json
import logging
import asyncio
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class WebhookNotifier:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.webhooks: dict[str, str] = {}

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    def register_webhook(self, name: str, url: str):
        self.webhooks[name] = url
        logger.info(f"Registered webhook '{name}': {url}")

    def remove_webhook(self, name: str):
        self.webhooks.pop(name, None)
        logger.info(f"Removed webhook '{name}'")

    async def send_discord(self, webhook_url: str, content: str, title: str = "") -> bool:
        await self._ensure_session()
        payload = {"content": f"**{title}**\n{content}"[:2000]}
        try:
            async with self._session.post(webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    logger.warning(f"Discord webhook returned {resp.status}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")
            return False

    async def send_slack(self, webhook_url: str, text: str) -> bool:
        await self._ensure_session()
        payload = {"text": text[:4000]}
        try:
            async with self._session.post(webhook_url, json=payload) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.error(f"Slack webhook error: {e}")
            return False

    async def send_generic(self, webhook_url: str, payload: dict) -> bool:
        await self._ensure_session()
        try:
            async with self._session.post(webhook_url, json=payload) as resp:
                return resp.status in (200, 204)
        except Exception as e:
            logger.error(f"Generic webhook error: {e}")
            return False

    async def broadcast(self, message: str, title: str = "", source: str = "") -> dict[str, bool]:
        results = {}
        for name, url in self.webhooks.items():
            if "discord" in url or "discordapp" in url:
                results[name] = await self.send_discord(url, message, title)
            elif "slack" in url or "hooks.slack" in url:
                results[name] = await self.send_slack(url, f"*{title}*\n{message}")
            else:
                results[name] = await self.send_generic(url, {
                    "title": title,
                    "message": message,
                    "source": source,
                    "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
                })
        return results

    def stop(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
