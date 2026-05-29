import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional, Callable

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
        self._reconnect_attempts = 0
        self._max_reconnect = 10

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _get_app_token(self) -> str:
        if self.access_token and datetime.utcnow().timestamp() < self.token_expires_at - 60:
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
            self._reconnect_attempts = 0
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
            data = await resp.json()
            if "error" in data and data.get("status") == 401:
                self.access_token = ""
                token = await self._get_app_token()
                headers["Authorization"] = f"Bearer {token}"
                async with self._session.get(url, headers=headers, params=params or {}) as retry:
                    return await retry.json()
            return data

    async def get_user_id(self, username: str) -> str:
        data = await self._api_call("users", {"login": username})
        users = data.get("data", [])
        return users[0]["id"] if users else ""

    async def get_stream_info(self, channel_name: str) -> dict:
        data = await self._api_call("streams", {"user_login": channel_name})
        streams = data.get("data", [])
        return streams[0] if streams else {}

    async def monitor_chat(self, channel: str, callback: Optional[Callable] = None):
        self._channel = channel
        self._running = True
        self._reconnect_attempts = 0
        logger.info(f"Starting Twitch monitor for #{channel}")

        await self._ensure_session()
        ws_url = "wss://eventsub.wss.twitch.tv/ws"

        while self._running and self._reconnect_attempts < self._max_reconnect:
            try:
                async with self._session.ws_connect(ws_url) as ws:
                    logger.info(f"Twitch WS connected for #{channel}")
                    self._reconnect_attempts = 0

                    welcome = await ws.receive_json()
                    session_id = welcome.get("payload", {}).get("session", {}).get("id", "")

                    broadcaster_id = await self.get_user_id(channel)
                    if broadcaster_id:
                        await self._subscribe_event(session_id, "channel.chat.message", broadcaster_id)
                        await self._subscribe_event(session_id, "channel.follow", broadcaster_id)
                        await self._subscribe_event(session_id, "channel.subscribe", broadcaster_id)

                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            await self._handle_event(data, callback)
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.warning("Twitch WS closed unexpectedly")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"Twitch WS error: {ws.exception()}")
                            break

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._reconnect_attempts += 1
                wait = min(2 ** self._reconnect_attempts, 60)
                logger.warning(f"Twitch disconnected (attempt {self._reconnect_attempts}/{self._max_reconnect}), reconnecting in {wait}s: {e}")
                await asyncio.sleep(wait)

        if self._reconnect_attempts >= self._max_reconnect:
            logger.error("Twitch max reconnect attempts reached")

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
            result = await resp.json()
            if resp.status == 409:
                logger.info(f"Subscription {event_type} already exists")
            elif resp.status not in (200, 202):
                logger.warning(f"Subscription {event_type} failed: {result}")
            return result

    async def _handle_event(self, event: dict, callback: Optional[Callable] = None):
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
                reply = f"@{chatter} {result.answer[:250]}"

                if callback:
                    await callback(chatter, message, reply, result)

                logger.info(f"Replied to {chatter}")

    def _is_help_request(self, message: str) -> bool:
        keywords = [
            "how do i", "how to", "where is", "help", "stuck",
            "walkthrough", "guide", "tips", "what do i do",
            "where do i go", "how do i beat", "strategy",
        ]
        msg = message.lower()
        return any(kw in msg for kw in keywords) or message.startswith("!")

    async def send_announcement(self, channel: str, message: str):
        try:
            token = await self._get_app_token()
            broadcaster_id = await self.get_user_id(channel)

            url = "https://api.twitch.tv/helix/chat/announcements"
            headers = {
                "Client-ID": self.client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            body = {
                "broadcaster_id": broadcaster_id,
                "moderator_id": broadcaster_id,
                "message": message,
            }

            async with self._session.post(url, headers=headers, json=body) as resp:
                return resp.status
        except Exception as e:
            logger.error(f"Failed to send Twitch announcement: {e}")

    def stop(self):
        self._running = False
        logger.info("Twitch monitor stopped")
