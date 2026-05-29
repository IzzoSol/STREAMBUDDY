# STREAMBUDDY - AI Game Assistant

Real-time game assistant that scans **voice**, **gameplay**, and **internet posts** for walkthrough help. Built for streamers, with Twitch + OBS integration.

## Features

- **Voice Detection** — Captures mic/stream audio, transcribes with Whisper/OpenAI, detects help requests
- **Gameplay Vision** — Analyzes screen via GPT-4o/Claude/Ollama — identifies game, scene, objectives, UI elements
- **Web Search** — Scans Google, Bing, Reddit, game wikis for guides and walkthroughs
- **Twitch Integration** — Monitors chat for help questions, auto-replies with answers
- **OBS Overlay** — Built-in browser source overlay showing help cards on stream
- **AI Orchestrator** — Combines all inputs into clear, contextual answers
- **Session History** — SQLite-backed with caching, per-session context
- **API Key Auth** — Multi-tier rate limiting (free/pro/enterprise)
- **Web Dashboard** — Built-in UI at `/api/v1/webui`
- **WebSocket Streaming** — Real-time answers via SSE or WebSocket

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python main.py            # Interactive CLI
python main.py --api      # HTTP API on port 8080
```

## API Keys Needed

| Service | Required For | Get It |
|---------|-------------|--------|
| OpenAI | STT + Vision + AI answers | platform.openai.com |
| Google Custom Search | Web walkthrough search | programmablesearchengine.google.com |
| Twitch | Chat monitoring | dev.twitch.tv/console |
| Reddit | Community tips | reddit.com/prefs/apps |

## API Usage

```bash
# Generate API key
curl http://localhost:8080/api/v1/generate-key?label=myapp&tier=pro

# Query
curl -X POST http://localhost:8080/api/v1/query \
  -H "X-API-Key: ga_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"query": "how do I beat Malenia in Elden Ring"}'

# Stream response
curl http://localhost:8080/api/v1/stream/default?query=how%20do%20I%20beat%20Malenia

# Web UI
open http://localhost:8080/api/v1/webui

# OBS Overlay (add as Browser Source in OBS)
http://localhost:8080/obs/overlay
```

## Architecture

```
src/
├── config.py           # Central config + .env auto-loading
├── orchestrator.py     # AI coordinator — ties all scanners together
├── voice/
│   ├── audio_capture.py   # Mic/stream audio capture
│   └── speech_to_text.py  # Whisper/OpenAI/Google STT
├── gameplay/
│   ├── screen_capture.py  # DXcam/MSS/PIL screen grab
│   └── vision_analyzer.py # GPT-4o/Claude/Ollama vision
├── web/
│   ├── search_engine.py   # Google/Bing/SearXNG search
│   ├── reddit_scraper.py  # Reddit tip scraping
│   └── wiki_scraper.py    # Fextralife/Fandom/IGN wikis
├── twitch/
│   └── stream_integration.py  # Twitch EventSub + chat monitor
├── obs/
│   ├── overlay.html      # OBS browser source overlay
│   └── overlay_server.py # Overlay serving
├── database/
│   ├── db.py             # SQLite async DB + caching
│   └── models.py         # Schema
├── api/
│   ├── server.py         # FastAPI server
│   ├── routes.py         # REST + WebSocket + Web UI
│   └── middleware.py      # Auth + rate limiting + logging
├── main.py              # Entry point (CLI + API)
└── tests/               # Pytest suite
```

## Tiers

| Feature | Free | Pro | Enterprise |
|---------|------|-----|-----------|
| Rate limit | 10/min | 60/min | 300/min |
| Queries/day | 100 | 1,000 | 10,000 |
| Sources/query | 3 | 10 | 25 |
| Vision analysis | No | Yes | Yes |
| Voice input | No | Yes | Yes |
| Twitch integration | No | Yes | Yes |
| API key | Required | Required | Required |

## OBS Setup

1. Run STREAMBUDDY: `python main.py --api`
2. In OBS, add a **Browser Source**
3. URL: `http://localhost:8080/obs/overlay`
4. Width: 420, Height: 320
5. Check "Refresh browser when scene becomes active"
6. Enable Twitch: Set `TWITCH_ENABLED=true` in `.env` and configure credentials
7. Start Twitch monitor: `POST /api/v1/twitch/start` with your channel name

Help cards appear automatically when viewers ask questions in chat.
