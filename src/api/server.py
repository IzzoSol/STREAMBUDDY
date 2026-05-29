import uvicorn
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import config
from src.api.routes import router
from src.api.middleware import setup_middleware
from src.database.db import db
from src.obs.overlay_server import router as obs_router

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting STREAMBUDDY server...")
    await db.connect()
    logger.info(f"Database initialized at {config.data_dir}/game_assist.db")
    yield
    await db.close()
    logger.info("Server shut down")


app = FastAPI(
    title="STREAMBUDDY",
    description="AI game assistant — voice, gameplay, and internet scan for walkthrough help. Twitch + OBS ready.",
    version="2.0.0",
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "streambuddy",
        "version": "2.0.0",
        "twitch_connected": config.twitch.enabled,
        "obs_overlay": "/obs/overlay",
    }


def run():
    uvicorn.run(
        "src.api.server:app",
        host=config.api.host,
        port=config.api.port,
        workers=config.api.workers,
        log_level=config.log_level.lower(),
    )
