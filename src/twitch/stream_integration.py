import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

import aiohttp

from src.orchestrator import GameAssistOrchestrator

logger = logging.getLogger(__name__)


class TwitchStreamIntegration:
    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = ""
        self.token_expires_at = 0
        self.orch = GameAssistOrchestrator()
        self._running = False
        self._channel = ""
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _get_app_token(self) -> str:
        if self.access_token and datetime.utcnow().timestamp() < self.token_expires_at:
            return self.access_token

        await self._ensure_session()
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }

        async with self._session.post(url, params=params) as resp:
            data = await resp.json()
            self.access_token = data["access_token"]
            self.token_expires_at = datetime.utcnow().timestamp() + data.get("expires_in", 3600)
            return self.access_token

    async def _api_call(self, endpoint: str, params: dict = None) -> dict:
        await self._ensure_session()
        token = await self._get_app_token()
        url = f"https://api.twitch.tv/helix/{endpoint}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
        }

        async with self._session.get(url, headers=headers, params=params or {}) as resp:
            return await resp.json()

    async def get_channel_info(self, channel_name: str) -> dict:
        data = await self._api_call("search/channels", {"query": channel_name, "first": 1})
        channels = data.get("data", [])
        return channels[0] if channels else {}

    async def get_stream_info(self, channel_name: str) -> dict:
        data = await self._api_call("streams", {"user_login": channel_name})
        streams = data.get("data", [])
        return streams[0] if streams else {}

    async def get_game_info(self, game_id: str) -> dict:
        data = await self._api_call("games", {"id": game_id})
        games = data.get("data", [])
        return games[0] if games else {}

    async def get_channel_chatters(self, channel_name: str, moderator_id: str = "") -> list[str]:
        data = await self._api_call("chat/chatters", {
            "broadcaster_id": moderator_id or channel_name,
            "moderator_id": moderator_id or channel_name,
        })
        chatters = data.get("data", [])
        return [c.get("user_login", "") for c in chatters]

    async def monitor_chat(self, channel: str, callback=None):
        self._channel = channel
        self._running = True
        logger.info(f"Starting Twitch chat monitor for #{channel}")

        info = await self.get_channel_info(channel)
        game_name = info.get("game_name", "unknown")
        self.orch.current_game = game_name

        await self._ensure_session()
        ws_url = "wss://eventsub.wss.twitch.tv/ws"
        async with self._session.ws_connect(ws_url) as ws:
            welcome = await ws.receive_json()
            session_id = welcome.get("payload", {}).get("session", {}).get("id", "")

            stream_info = await self.get_channel_info(channel)
            broadcaster_id = stream_info.get("id", "")

            if broadcaster_id:
                await self._subscribe_event(session_id, "channel.chat.message", broadcaster_id)

            async for msg in ws:
                if not self._running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_event(data, callback)

    async def _subscribe_event(self, session_id: str, event_type: str, broadcaster_id: str):
        await self._ensure_session()
        token = await self._get_app_token()
        url = "https://api.twitch.tv/helix/eventsub/subscriptions"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            "type": event_type,
            "version": "1",
            "condition": {"broadcaster_user_id": broadcaster_id},
            "transport": {"method": "websocket", "session_id": session_id},
        }
        async with self._session.post(url, headers=headers, json=body) as resp:
            return await resp.json()

    async def _handle_event(self, event: dict, callback=None):
        payload = event.get("payload", {})
        event_type = payload.get("subscription", {}).get("type", "")

        if event_type == "channel.chat.message":
            event_data = payload.get("event", {})
            chatter = event_data.get("chatter_user_name", "unknown")
            message = event_data.get("message", {}).get("text", "")

            logger.info(f"[Twitch] {chatter}: {message}")

            if self._is_help_request(message):
                logger.info(f"Help request from {chatter}: {message}")
                result = await self.orch.process_text_query(message)
                reply = f"@{chatter} {result.answer[:300]}"

                if callback:
                    await callback(chatter, message, reply)

                logger.info(f"Reply to {chatter}: {reply[:100]}...")

    def _is_help_request(self, message: str) -> bool:
        keywords = [
            "how do i", "how to", "where is", "help", "stuck",
            "walkthrough", "guide", "tips", "what do i do",
            "where do i go", "how do i beat", "strategy",
        ]
        msg_lower = message.lower()
        for kw in keywords:
            if kw in msg_lower:
                return True
        return msg_lower.startswith("!")

    async def send_chat_message(self, channel: str, message: str):
        try:
            import requests as sync_requests
            token = self.access_token or await self._get_app_token()

            info = await self.get_channel_info(channel)
            broadcaster_id = info.get("id", "")

            url = f"https://api.twitch.tv/helix/chat/announcements"
            headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            async with self._session.post(url, headers=headers, json={
                "broadcaster_id": broadcaster_id,
                "moderator_id": broadcaster_id,
                "message": message,
            }) as resp:
                return resp.status
        except Exception as e:
            logger.error(f"Failed to send chat message: {e}")

    def stop(self):
        self._running = False
        logger.info("Twitch monitor stopped")
