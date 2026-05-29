import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/obs")

OVERLAY_PATH = Path(__file__).parent / "overlay.html"


@router.get("/overlay", response_class=HTMLResponse)
async def serve_overlay():
    if not OVERLAY_PATH.exists():
        raise HTTPException(404, "Overlay file not found")
    return OVERLAY_PATH.read_text(encoding="utf-8")


@router.get("/overlay/widget")
async def overlay_widget():
    return {
        "type": "browser_source",
        "url": "/obs/overlay",
        "width": 420,
        "height": 320,
        "fps": 30,
        "css": "",
        "render": "transparent",
    }
