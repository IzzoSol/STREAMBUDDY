import asyncio
import uvicorn
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import config, validate_config
from src.api.routes import router
from src.api.middleware import setup_middleware
from src.database.db import db
from src.obs.overlay_server import router as obs_router
from src.analytics import analytics

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

_auto_start_tasks = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting STREAMBUDDY server...")
    await db.connect()
    logger.info(f"Database initialized at {config.data_dir}/game_assist.db")

    config_warnings = validate_config()
    if config_warnings:
        logger.warning("Configuration warnings:")
        for w in config_warnings:
            logger.warning(f"  - {w}")
            await analytics.log_alert("warning", "config", w)

    analytics_task = asyncio.create_task(analytics.start_hourly_rollup())
    logger.info("Analytics engine started")

    # Auto-start integrations based on config
    if config.twitch.enabled and config.twitch.client_id and config.twitch.client_secret:
        try:
            from src.twitch import TwitchStreamIntegration
            tw = TwitchStreamIntegration(config.twitch.client_id, config.twitch.client_secret)
            twitch_task = asyncio.create_task(tw.monitor_chat(config.twitch.channel))
            _auto_start_tasks.append(twitch_task)
            await analytics.log_alert("info", "twitch", f"Auto-started Twitch monitor for {config.twitch.channel}")
            logger.info(f"Auto-started Twitch integration: {config.twitch.channel}")
            await analytics.update_platform_status("twitch", True)
        except Exception as e:
            logger.warning(f"Twitch auto-start failed: {e}")

    if config.discord.enabled and config.discord.token:
        try:
            from src.discord_bot.bot import DiscordBotIntegration
            bot = DiscordBotIntegration(token=config.discord.token)
            discord_task = asyncio.create_task(bot.start())
            _auto_start_tasks.append(discord_task)
            await analytics.log_alert("info", "discord", "Auto-started Discord bot")
            logger.info("Auto-started Discord bot")
            await analytics.update_platform_status("discord", True)
        except Exception as e:
            logger.warning(f"Discord auto-start failed: {e}")

    if config.youtube.enabled and config.youtube.api_key:
        logger.info("YouTube auto-start: waiting for video_id (set via API)")
        await analytics.update_platform_status("youtube", True)

    await analytics.update_platform_status("obs", config.obs.overlay_enabled)

    yield

    analytics.stop()
    for t in _auto_start_tasks:
        t.cancel()
    for t in _auto_start_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    await db.close()
    logger.info("Server shut down")


app = FastAPI(
    title="STREAMBUDDY",
    description="AI game assistant — voice, gameplay, and internet scan for walkthrough help. Twitch + OBS + YouTube + Discord + Strategy Swarm.",
    version="2.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = setup_middleware(app, debug=config.debug)
app.include_router(router)
app.include_router(obs_router)

static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Serving static files from {static_dir}")


@app.get("/health")
async def health():
    summary = await analytics.get_summary()
    return {
        "status": "ok",
        "service": "streambuddy",
        "version": "2.3.0",
        "twitch_connected": config.twitch.enabled,
        "discord_connected": config.discord.enabled,
        "youtube_connected": config.youtube.enabled,
        "obs_overlay": "/obs/overlay",
        "admin_dashboard": "/api/v1/admin",
        "total_queries": summary.get("total_queries", 0),
        "games_detected": summary.get("games_detected", 0),
    }


def run():
    uvicorn.run(
        "src.api.server:app",
        host=config.api.host,
        port=config.api.port,
        workers=config.api.workers,
        log_level=config.log_level.lower(),
    )
