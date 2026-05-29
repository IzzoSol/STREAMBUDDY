import asyncio
import logging
from typing import Optional

from src.orchestrator import GameAssistOrchestrator

logger = logging.getLogger(__name__)


class DiscordBotIntegration:
    def __init__(self, token: str = ""):
        self.token = token
        self.orch = GameAssistOrchestrator()
        self._running = False
        self._client = None

    async def start(self):
        import discord
        from discord import Intents
        from discord.ext import commands

        intents = Intents.default()
        intents.message_content = True

        bot = commands.Bot(command_prefix="!", intents=intents)
        self._client = bot

        @bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {bot.user}")

        @bot.event
        async def on_message(message):
            if message.author.bot:
                return

            if bot.user in message.mentions:
                query = message.content.replace(f"<@{bot.user.id}>", "").strip()
                if query:
                    async with message.channel.typing():
                        result = await self.orch.process_text_query(query)
                        answer = result.answer[:1500]
                        game = f"**{result.game}** - " if result.game else ""
                        await message.reply(f"{game}{answer}", mention_author=False)

            elif message.content.startswith("!game"):
                game = message.content[6:].strip()
                if game:
                    self.orch.current_game = game
                    await message.add_reaction("✅")

            elif message.content.startswith("!help") or message.content.startswith("!streambuddy"):
                query = message.content.split(maxsplit=1)
                if len(query) > 1:
                    async with message.channel.typing():
                        result = await self.orch.process_text_query(query[1])
                        await message.reply(result.answer[:1500], mention_author=False)
                else:
                    await message.channel.send(
                        "**STREAMBUDDY** — AI Game Assistant\n\n"
                        "Mention me with a question, or use:\n"
                        "`!help <question>` — Get walkthrough help\n"
                        "`!game <name>` — Set current game\n"
                        "`!stats` — Show session stats"
                    )

        self._running = True
        await bot.start(self.token)

    def stop(self):
        self._running = False
        logger.info("Discord bot stopped")
