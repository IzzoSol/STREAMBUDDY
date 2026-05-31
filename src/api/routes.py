import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from src.orchestrator import GameAssistOrchestrator, AssistResult
from src.database.db import db
from src.config import config, TIERS, validate_config
from src.analytics import analytics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

orchestrator_registry: dict[str, GameAssistOrchestrator] = {}


def _get_orchestrator(session_id: str = "default") -> GameAssistOrchestrator:
    if session_id not in orchestrator_registry:
        orchestrator_registry[session_id] = GameAssistOrchestrator()
    return orchestrator_registry[session_id]


class QueryRequest(BaseModel):
    query: str
    game: str = ""
    session_id: str = "default"


class QueryResponse(BaseModel):
    query: str
    game: str
    topic: str
    voice_text: str = ""
    answer: str
    confidence: float
    sources: list[str]
    processing_time_ms: float
    vision_analysis: dict = {}
    web_results: list = []
    reddit_results: list = []
    wiki_results: list = []
    session_id: str = "default"


def _result_to_response(result: AssistResult, session_id: str = "default") -> QueryResponse:
    return QueryResponse(
        query=result.query,
        game=result.game,
        topic=result.topic,
        voice_text=result.voice_text,
        answer=result.answer,
        confidence=result.confidence,
        sources=result.sources,
        processing_time_ms=result.processing_time_ms,
        vision_analysis=result.vision_analysis,
        web_results=result.web_results[:5],
        reddit_results=result.reddit_results[:5],
        wiki_results=result.wiki_results[:5],
        session_id=session_id,
    )


@router.post("/query", response_model=QueryResponse)
async def text_query(req: QueryRequest):
    start = time.time()
    await db.get_or_create_session(req.session_id)

    cache_key = f"query:{req.game}:{req.query}"
    cached = await db.get_cached(cache_key)
    if cached:
        elapsed = (time.time() - start) * 1000
        cached_data = json.loads(cached)
        cached_data["processing_time_ms"] = elapsed
        return QueryResponse(**cached_data)

    orch = _get_orchestrator(req.session_id)
    orch.detect_player_language(req.query)
    if req.game:
        orch.current_game = req.game

    result = await orch.process_text_query(req.query)

    elapsed_ms = (time.time() - start) * 1000
    is_error = not result.answer or result.confidence < 0.1

    await db.save_query(req.session_id, {
        "query": result.query,
        "game": result.game,
        "topic": result.topic,
        "answer": result.answer,
        "confidence": result.confidence,
        "sources": result.sources,
        "processing_time_ms": result.processing_time_ms,
        "vision_analysis": result.vision_analysis,
        "web_results": result.web_results[:5],
        "reddit_results": result.reddit_results[:5],
        "wiki_results": result.wiki_results[:5],
    })

    await analytics.record_query(req.session_id, result.game, "api", elapsed_ms, is_error)

    if result.confidence > 0.5 and result.answer:
        await db.set_cache(cache_key, json.dumps(_result_to_response(result, req.session_id).model_dump()))

    return _result_to_response(result, req.session_id)


@router.post("/voice", response_model=QueryResponse)
async def voice_query(
    duration: float = Form(5.0),
    session_id: str = Form("default"),
):
    await db.get_or_create_session(session_id)
    orch = _get_orchestrator(session_id)
    result = await orch.process_voice_command(duration=duration)

    await db.save_query(session_id, {
        "query": result.query,
        "game": result.game,
        "topic": result.topic,
        "voice_text": result.voice_text,
        "answer": result.answer,
        "confidence": result.confidence,
        "sources": result.sources,
        "processing_time_ms": result.processing_time_ms,
        "vision_analysis": result.vision_analysis,
        "web_results": result.web_results[:5],
        "reddit_results": result.reddit_results[:5],
        "wiki_results": result.wiki_results[:5],
    })

    return _result_to_response(result, session_id)


@router.post("/query-with-screenshot")
async def query_with_screenshot(
    query: str = Form(...),
    game: str = Form(""),
    session_id: str = Form("default"),
    screenshot: UploadFile = File(None),
):
    await db.get_or_create_session(session_id)
    orch = _get_orchestrator(session_id)
    if game:
        orch.current_game = game

    result = await orch.process_text_query(query)

    await db.save_query(session_id, {
        "query": result.query,
        "game": result.game,
        "topic": result.topic,
        "answer": result.answer,
        "confidence": result.confidence,
        "sources": result.sources,
        "processing_time_ms": result.processing_time_ms,
        "vision_analysis": result.vision_analysis,
    })

    return _result_to_response(result, session_id)


@router.get("/stream/{session_id}")
async def stream_answers(session_id: str, query: str = Query(...), game: str = Query("")):
    async def event_stream():
        orch = _get_orchestrator(session_id)
        if game:
            orch.current_game = game

        yield f"data: {json.dumps({'type': 'start', 'query': query, 'session_id': session_id})}\n\n"

        result = await orch.process_text_query(query)

        yield f"data: {json.dumps({'type': 'result', 'query': result.query, 'game': result.game, 'topic': result.topic, 'confidence': result.confidence})}\n\n"

        if result.answer:
            words = result.answer.split(" ")
            chunk_size = 3
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size])
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk + ' '})}\n\n"
                await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'type': 'done', 'sources': result.sources, 'processing_time_ms': result.processing_time_ms})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    session = await db.get_or_create_session(session_id)
    history = await db.get_session_history(session_id, limit=5)
    return {
        "session_id": session_id,
        "game": session.get("game", ""),
        "query_count": session.get("query_count", 0),
        "recent_queries": [
            {
                "query": h["query"],
                "game": h["game"],
                "answer_preview": h["answer"][:100] if h["answer"] else "",
                "created_at": h["created_at"],
            }
            for h in history
        ],
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    history = await db.get_session_history(session_id, limit=limit)
    return [
        {
            "query": h["query"],
            "game": h["game"],
            "topic": h["topic"],
            "answer": h["answer"][:200] if h["answer"] else "",
            "confidence": h["confidence"],
            "processing_time_ms": h["processing_time_ms"],
            "created_at": h["created_at"],
        }
        for h in history
    ]


@router.post("/session/{session_id}/game")
async def set_game(session_id: str, game: str = Form(...)):
    orch = _get_orchestrator(session_id)
    orch.current_game = game
    await db.save_game_context(session_id, game)
    return {"status": "ok", "session_id": session_id, "game": game}


@router.get("/webui", response_class=HTMLResponse)
async def webui():
    return UI_HTML


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    orch = _get_orchestrator(session_id)
    logger.info(f"WebSocket connected: session={session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            start = time.time()

            if msg_type == "query":
                game = data.get("game", "")
                query_text = data.get("query", "")
                if game:
                    orch.current_game = game
                result = await orch.process_text_query(query_text)

                await db.save_query(session_id, {
                    "query": result.query,
                    "game": result.game,
                    "topic": result.topic,
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "sources": result.sources,
                    "processing_time_ms": result.processing_time_ms,
                })

                await websocket.send_json({
                    "type": "result",
                    "query": result.query,
                    "game": result.game,
                    "topic": result.topic,
                    "answer": result.answer,
                    "confidence": result.confidence,
                    "sources": result.sources,
                    "processing_time_ms": result.processing_time_ms,
                })

            elif msg_type == "voice":
                duration = data.get("duration", 5.0)
                result = await orch.process_voice_command(duration=duration)
                if result.voice_text:
                    await db.save_query(session_id, {
                        "query": result.query,
                        "game": result.game,
                        "voice_text": result.voice_text,
                        "answer": result.answer,
                    })

                await websocket.send_json({
                    "type": "voice_result",
                    "query": result.query,
                    "voice_text": result.voice_text,
                    "game": result.game,
                    "answer": result.answer or "No help request detected",
                    "confidence": result.confidence,
                    "sources": result.sources,
                    "processing_time_ms": result.processing_time_ms,
                })

            elif msg_type == "set_game":
                orch.current_game = data["game"]
                await db.save_game_context(session_id, data["game"])
                await websocket.send_json({"type": "game_set", "game": orch.current_game})

            elif msg_type == "history":
                history = await db.get_session_history(session_id, limit=20)
                await websocket.send_json({"type": "history", "history": [dict(h) for h in history]})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")


#
# Strategy Endpoints
#

class StrategyRequest(BaseModel):
    boss: str
    game: str = ""


@router.post("/strategy/boss")
async def boss_strategy(req: StrategyRequest, session_id: str = "default"):
    orch = _get_orchestrator(session_id)
    swarm = orch.analyze_boss_strategy(req.boss, req.game)
    if not swarm:
        boss_info = orch.get_boss_info(req.boss)
        if boss_info:
            return {
                "found": True,
                "boss": req.boss,
                "game": boss_info.game,
                "weaknesses": boss_info.weaknesses,
                "resistances": boss_info.resistances,
                "recommended_level": boss_info.recommended_level,
                "key_moves": boss_info.key_moves,
                "loadout_tips": boss_info.loadout_tips,
                "phase_strategies": boss_info.phase_strategies,
                "swarm_available": False,
            }
        return {"found": False, "boss": req.boss, "swarm_available": False}

    return {
        "found": True,
        "boss": swarm.boss,
        "game": swarm.game,
        "swarm_confidence": swarm.swarm_confidence,
        "agreement_level": swarm.agreement_level,
        "recommended_approach": swarm.recommended_approach,
        "top_recommendations": swarm.top_recommendations,
        "consensus_loadout": swarm.consensus_loadout,
        "votes": [
            {
                "agent": v.agent_name,
                "focus": v.agent_focus,
                "confidence": v.confidence,
                "key_advice": v.key_advice,
            }
            for v in swarm.votes
        ],
        "swarm_available": True,
    }


@router.get("/strategy/bosses")
async def list_bosses(session_id: str = "default"):
    orch = _get_orchestrator(session_id)
    return {"bosses": orch.list_known_bosses(), "count": len(orch.list_known_bosses())}


@router.get("/strategy/agents")
async def list_agents():
    from src.strategy.strategies import STRATEGY_AGENTS
    return {"agents": STRATEGY_AGENTS}


#
# YouTube Guide Endpoints
#

@router.post("/youtube/guide")
async def youtube_guide(
    boss: str = Form(...),
    game: str = Form(""),
    session_id: str = Form("default"),
):
    orch = _get_orchestrator(session_id)
    guide = await orch.find_youtube_guide(boss, game)
    if guide:
        return {"found": True, "guide": guide}
    return {"found": False, "message": "No YouTube guide found"}


#
# i18n Endpoints
#

@router.get("/i18n/languages")
async def get_languages():
    from src.i18n.lang import HELP_KEYWORDS
    return {"languages": list(HELP_KEYWORDS.keys())}


@router.post("/i18n/detect")
async def detect_language_from_text(text: str = Form(...)):
    from src.i18n.lang import detect_language
    lang = detect_language(text)
    return {"language": lang, "text_preview": text[:50]}


#
# Webhook Endpoints
#

@router.post("/webhook/register")
async def register_webhook(
    name: str = Form(...),
    url: str = Form(...),
    session_id: str = Form("default"),
):
    orch = _get_orchestrator(session_id)
    from src.notifications.webhook import WebhookNotifier
    notifier = WebhookNotifier()
    notifier.register_webhook(name, url)
    await db._conn.execute(
        "INSERT OR REPLACE INTO webhooks (name, url, provider, created_at) VALUES (?, ?, ?, ?)",
        (name, url, "discord" if "discord" in url else "generic", datetime.utcnow().isoformat()),
    )
    await db._conn.commit()
    return {"status": "registered", "name": name, "url": url}


@router.get("/webhook/list")
async def list_webhooks():
    await db.connect()
    cursor = await db._conn.execute("SELECT name, url, provider, is_active, created_at FROM webhooks ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    return {"webhooks": [dict(r) for r in rows]}


@router.post("/webhook/test")
async def test_webhook(name: str = Form(...), session_id: str = Form("default")):
    await db.connect()
    cursor = await db._conn.execute("SELECT url, provider FROM webhooks WHERE name = ? AND is_active = 1", (name,))
    row = await cursor.fetchone()
    if not row:
        return {"status": "error", "message": f"Webhook '{name}' not found"}
    from src.notifications.webhook import WebhookNotifier
    notifier = WebhookNotifier()
    success = await notifier.send_discord(row["url"], "STREAMBUDDY test notification", "Test")
    return {"status": "sent" if success else "failed", "name": name}


UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Assist AI</title>
<style>
  :root {
    --bg: #0f0f1a;
    --surface: #1a1a2e;
    --surface2: #16213e;
    --accent: #00d4ff;
    --accent2: #7c3aed;
    --text: #e0e0e0;
    --text2: #94a3b8;
    --success: #22c55e;
    --border: #2a2a4a;
    --danger: #ef4444;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .header h1 { font-size: 18px; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .header .badge { font-size: 11px; background: var(--accent2); color: white; padding: 2px 8px; border-radius: 10px; -webkit-text-fill-color: white; margin-left: 8px; }
  .session-info { font-size: 12px; color: var(--text2); }
  .main { flex: 1; display: flex; max-width: 1200px; width: 100%; margin: 0 auto; padding: 16px; gap: 16px; }
  .sidebar { width: 280px; flex-shrink: 0; }
  .content { flex: 1; display: flex; flex-direction: column; }
  .card { background: var(--surface); border-radius: 12px; border: 1px solid var(--border); padding: 16px; margin-bottom: 12px; }
  .card-title { font-size: 13px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .game-input { width: 100%; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; color: var(--text); font-size: 13px; }
  .game-input:focus { outline: none; border-color: var(--accent); }
  .chat-area { flex: 1; overflow-y: auto; max-height: 60vh; padding: 4px; }
  .msg { padding: 10px 14px; border-radius: 12px; margin-bottom: 8px; font-size: 14px; line-height: 1.5; animation: fadeIn 0.3s; }
  @keyframes fadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
  .msg.user { background: var(--accent2); color: white; margin-left: 40px; border-bottom-right-radius: 4px; }
  .msg.assistant { background: var(--surface2); border: 1px solid var(--border); margin-right: 40px; border-bottom-left-radius: 4px; }
  .msg.system { background: transparent; text-align: center; font-size: 12px; color: var(--text2); }
  .msg .sources { margin-top: 8px; font-size: 12px; }
  .msg .sources a { color: var(--accent); text-decoration: none; display: inline-block; margin-right: 8px; }
  .msg .sources a:hover { text-decoration: underline; }
  .msg .meta { font-size: 11px; color: var(--text2); margin-top: 6px; }
  .input-area { display: flex; gap: 8px; }
  .input-area input { flex: 1; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 14px; }
  .input-area input:focus { outline: none; border-color: var(--accent); }
  .btn { background: var(--accent2); color: white; border: none; border-radius: 8px; padding: 10px 18px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
  .btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn.secondary { background: var(--surface2); border: 1px solid var(--border); }
  .btn.danger { background: var(--danger); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
  .voice-btn { background: var(--accent); color: var(--bg); }
  .voice-btn.recording { background: var(--danger); animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.7; } }
  .typing { display: inline-flex; gap: 3px; }
  .typing span { width: 6px; height: 6px; background: var(--accent); border-radius: 50%; animation: bounce 1.4s infinite; }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce { 0%,80%,100% { transform:translateY(0); } 40% { transform:translateY(-6px); } }
  .empty-state { text-align: center; padding: 40px 20px; color: var(--text2); }
  .empty-state h3 { font-size: 18px; margin-bottom: 8px; color: var(--text); }
  .empty-state p { font-size: 13px; }
  .history-item { padding: 8px 0; border-bottom: 1px solid var(--border); cursor: pointer; }
  .history-item:last-child { border: none; }
  .history-item .q { font-size: 13px; }
  .history-item .q small { color: var(--text2); font-size: 11px; }
  .history-item:hover .q { color: var(--accent); }
  .status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; }
  .status-dot.online { background: var(--success); }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="header">
  <div><h1>Game Assist AI <span class="badge">v2.3</span></h1></div>
  <div class="session-info"><span class="status-dot online"></span>Session: <span id="sessionDisplay">default</span></div>
</div>
<div class="main">
  <div class="sidebar">
    <div class="card">
      <div class="card-title">Current Game</div>
      <input class="game-input" id="gameInput" placeholder="Auto-detect or type game name..." />
      <button class="btn secondary" style="width:100%;margin-top:8px" onclick="setGame()">Set Game</button>
    </div>
    <div class="card">
      <div class="card-title">Recent Queries</div>
      <div id="historyList">
        <div style="color:var(--text2);font-size:12px">No queries yet</div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Status</div>
      <div style="font-size:12px;color:var(--text2)">
        <div id="statusText">Ready</div>
        <div style="margin-top:4px">Queries: <span id="queryCount">0</span></div>
      </div>
    </div>
  </div>
  <div class="content">
    <div class="card" style="flex:1;display:flex;flex-direction:column">
      <div class="chat-area" id="chatArea">
        <div class="empty-state" id="emptyState">
          <h3>How can I help you?</h3>
          <p>Ask about a game walkthrough, boss strategy, hidden item location, or any gameplay question.</p>
          <p style="margin-top:8px;font-size:12px">Example: "How do I beat Malenia in Elden Ring?"</p>
        </div>
      </div>
      <div class="input-area" style="margin-top:12px">
        <input id="queryInput" placeholder="Ask about any game..." onkeydown="if(event.key==='Enter')sendQuery()" autofocus />
        <button class="btn voice-btn" id="voiceBtn" onclick="startVoice()">🎤</button>
        <button class="btn" onclick="sendQuery()">Send</button>
      </div>
    </div>
  </div>
</div>

<script>
let sessionId = 'default';
let ws = null;
let isRecording = false;
let queryCount = 0;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/api/v1/ws/' + sessionId);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWSMessage(data);
  };

  ws.onclose = () => { setTimeout(connectWS, 2000); };
  ws.onerror = () => { ws.close(); };
}

function handleWSMessage(data) {
  switch (data.type) {
    case 'result':
    case 'voice_result':
      removeTyping();
      addMessage(data.answer || data.query, 'assistant', data);
      if (data.game) document.getElementById('gameInput').value = data.game;
      queryCount++;
      document.getElementById('queryCount').textContent = queryCount;
      loadHistory();
      break;
    case 'game_set':
      setStatus('Game set to: ' + data.game);
      break;
    case 'history':
      renderHistory(data.history);
      break;
  }
}

function sendQuery() {
  const input = document.getElementById('queryInput');
  const query = input.value.trim();
  if (!query) return;

  const game = document.getElementById('gameInput').value.trim();
  addMessage(query, 'user');
  addTyping();
  input.value = '';
  setStatus('Searching...');

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'query', query, game }));
  } else {
    fetch('/api/v1/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, game, session_id: sessionId }),
    })
    .then(r => r.json())
    .then(data => {
      removeTyping();
      addMessage(data.answer, 'assistant', data);
      if (data.game) document.getElementById('gameInput').value = data.game;
      queryCount++;
      document.getElementById('queryCount').textContent = queryCount;
      loadHistory();
    })
    .catch(() => {
      removeTyping();
      addMessage('Error: Could not reach server', 'system');
    });
  }
}

function startVoice() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    addMessage('Voice not supported in this browser', 'system');
    return;
  }
  if (isRecording) return;
  isRecording = true;
  const btn = document.getElementById('voiceBtn');
  btn.classList.add('recording');
  btn.textContent = '⏺';
  setStatus('Recording... speak now');

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const mediaRecorder = new MediaRecorder(stream);
      const chunks = [];
      mediaRecorder.ondataavailable = e => chunks.push(e.data);
      mediaRecorder.onstop = () => {
        btn.classList.remove('recording');
        btn.textContent = '🎤';
        isRecording = false;
        stream.getTracks().forEach(t => t.stop());

        if (ws && ws.readyState === WebSocket.OPEN) {
          setStatus('Processing voice...');
          ws.send(JSON.stringify({ type: 'voice', duration: 5.0 }));
        } else {
          setStatus('Voice requires WebSocket - reconnecting...');
        }
      };
      mediaRecorder.start();
      setTimeout(() => mediaRecorder.stop(), 5000);
    })
    .catch(err => {
      btn.classList.remove('recording');
      btn.textContent = '🎤';
      isRecording = false;
      addMessage('Mic error: ' + err.message, 'system');
    });
}

function setGame() {
  const game = document.getElementById('gameInput').value.trim();
  if (!game) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'set_game', game }));
  } else {
    const form = new FormData();
    form.append('game', game);
    fetch('/api/v1/session/' + sessionId + '/game', { method: 'POST', body: form });
  }
  setStatus('Game set to: ' + game);
}

function addMessage(text, type, data = null) {
  const area = document.getElementById('chatArea');
  const empty = document.getElementById('emptyState');
  if (empty) empty.style.display = 'none';

  const div = document.createElement('div');
  div.className = 'msg ' + type;
  div.textContent = text;

  if (data && data.sources && data.sources.length > 0) {
    const srcDiv = document.createElement('div');
    srcDiv.className = 'sources';
    srcDiv.innerHTML = '<strong>Sources:</strong> ' + data.sources.slice(0, 5).map(s =>
      '<a href="' + s + '" target="_blank">Link</a>'
    ).join('');
    div.appendChild(srcDiv);
  }

  if (data && data.processing_time_ms) {
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = (data.processing_time_ms / 1000).toFixed(1) + 's | ' + Math.round(data.confidence * 100) + '% confidence';
    div.appendChild(meta);
  }

  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
}

function addTyping() {
  const area = document.getElementById('chatArea');
  const div = document.createElement('div');
  div.className = 'msg assistant';
  div.id = 'typingIndicator';
  div.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  area.appendChild(div);
  area.scrollTop = area.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.remove();
}

function setStatus(text) {
  document.getElementById('statusText').textContent = text;
}

function loadHistory() {
  fetch('/api/v1/history/' + sessionId + '?limit=10')
    .then(r => r.json())
    .then(data => renderHistory(data));
}

function renderHistory(data) {
  const list = document.getElementById('historyList');
  if (!data || data.length === 0) {
    list.innerHTML = '<div style="color:var(--text2);font-size:12px">No queries yet</div>';
    return;
  }
  list.innerHTML = data.slice(0, 10).map(h =>
    '<div class="history-item" onclick="replayQuery(\'' + h.query.replace(/'/g, "\\'") + '\')">' +
    '<div class="q">' + h.query + '<br><small>' + (h.game || 'unknown') + ' &middot; ' + (h.created_at || '').slice(0, 10) + '</small></div></div>'
  ).join('');
}

function replayQuery(query) {
  document.getElementById('queryInput').value = query;
  sendQuery();
}

connectWS();
loadHistory();
</script>
</body>
</html>"""


@router.get("/generate-key")
async def generate_api_key(label: str = "default", tier: str = "free"):
    valid_tiers = list(TIERS.keys())
    if tier not in valid_tiers:
        raise HTTPException(400, f"Invalid tier. Choose from: {valid_tiers}")
    key = await db.create_api_key(label, tier)
    tier_info = TIERS[tier]
    return {
        "api_key": key,
        "tier": tier,
        "label": label,
        "limits": {
            "rate_per_min": tier_info.rate_limit_per_min,
            "queries_per_day": tier_info.max_queries_per_day,
            "max_sources": tier_info.max_sources,
            "allow_vision": tier_info.allow_vision,
            "allow_voice": tier_info.allow_voice,
            "allow_twitch": tier_info.allow_twitch,
        },
        "note": "Save this key - it will not be shown again",
    }


@router.post("/twitch/start")
async def start_twitch(
    channel: str = Form(...),
    session_id: str = Form("default"),
):
    from src.twitch import TwitchStreamIntegration

    if not config.twitch.client_id or not config.twitch.client_secret:
        await analytics.log_alert("error", "twitch", "Twitch start failed: missing credentials")
        raise HTTPException(400, "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be configured")

    twitch = TwitchStreamIntegration(
        client_id=config.twitch.client_id,
        client_secret=config.twitch.client_secret,
    )
    twitch.orch = _get_orchestrator(session_id)
    await analytics.update_platform_status("twitch", True)
    await analytics.log_alert("info", "twitch", f"Twitch integration started for channel: {channel}")
    asyncio.create_task(twitch.monitor_chat(channel))
    return {"status": "started", "channel": channel, "session_id": session_id}


@router.post("/twitch/stop")
async def stop_twitch():
    await analytics.update_platform_status("twitch", False)
    await analytics.log_alert("info", "twitch", "Twitch integration stopped")
    return {"status": "stopped"}


@router.post("/youtube/start")
async def start_youtube(
    video_id: str = Form(...),
    session_id: str = Form("default"),
):
    from src.youtube.integration import YouTubeStreamIntegration

    if not config.youtube.api_key:
        await analytics.log_alert("error", "youtube", "YouTube start failed: missing API key")
        raise HTTPException(400, "YOUTUBE_API_KEY must be configured")

    yt = YouTubeStreamIntegration(api_key=config.youtube.api_key)
    yt.orch = _get_orchestrator(session_id)
    await analytics.update_platform_status("youtube", True)
    await analytics.log_alert("info", "youtube", f"YouTube integration started for video: {video_id}")
    asyncio.create_task(yt.monitor_chat(video_id))
    return {"status": "started", "video_id": video_id, "session_id": session_id}


@router.post("/youtube/stop")
async def stop_youtube():
    await analytics.update_platform_status("youtube", False)
    await analytics.log_alert("info", "youtube", "YouTube integration stopped")
    return {"status": "stopped"}


@router.post("/discord/start")
async def start_discord(session_id: str = Form("default")):
    from src.discord_bot.bot import DiscordBotIntegration

    if not config.discord.token:
        await analytics.log_alert("error", "discord", "Discord start failed: missing token")
        raise HTTPException(400, "DISCORD_TOKEN must be configured")

    bot = DiscordBotIntegration(token=config.discord.token)
    bot.orch = _get_orchestrator(session_id)
    await analytics.update_platform_status("discord", True)
    await analytics.log_alert("info", "discord", "Discord bot started")
    asyncio.create_task(bot.start())
    return {"status": "started", "session_id": session_id}


@router.post("/discord/stop")
async def stop_discord():
    await analytics.update_platform_status("discord", False)
    await analytics.log_alert("info", "discord", "Discord bot stopped")
    return {"status": "stopped"}


#
# Analytics Endpoints
#

@router.get("/analytics/summary")
async def analytics_summary():
    return await analytics.get_summary()


@router.get("/analytics/popular-games")
async def analytics_popular_games(days: int = 7, limit: int = 20):
    return await analytics.get_popular_games(days=days, limit=limit)


@router.get("/analytics/daily")
async def analytics_daily(days: int = 14):
    return await analytics.get_daily_stats(days=days)


@router.get("/analytics/platforms")
async def analytics_platforms():
    return await analytics.get_platform_stats()


@router.get("/analytics/top-queries")
async def analytics_top_queries(days: int = 7, limit: int = 20):
    return await analytics.get_top_queries(days=days, limit=limit)


@router.get("/analytics/trend")
async def analytics_trend(hours: int = 24):
    return await analytics.get_hourly_trend(hours=hours)


@router.get("/analytics/alerts")
async def analytics_alerts(limit: int = 50, unread: bool = False):
    return await analytics.get_alerts(limit=limit, unread_only=unread)


@router.post("/analytics/alerts/read")
async def analytics_alerts_read(alert_ids: list[int] = None):
    await analytics.mark_alerts_read(alert_ids)
    return {"status": "ok"}


#
# Admin Dashboard
#

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STREAMBUDDY Admin</title>
<style>
  :root {
    --bg: #0b0b1a;
    --surface: #14142a;
    --surface2: #1c1c3a;
    --accent: #00d4ff;
    --accent2: #7c3aed;
    --text: #e0e0e0;
    --text2: #8899bb;
    --success: #22c55e;
    --warning: #eab308;
    --danger: #ef4444;
    --border: #2a2a4a;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-height: 100vh; }
  .topbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }
  .topbar h1 { font-size: 16px; font-weight: 700; }
  .topbar h1 span { color: var(--accent2); }
  .topbar .nav { display: flex; gap: 16px; }
  .topbar .nav a { color: var(--text2); text-decoration: none; font-size: 13px; cursor: pointer; padding: 4px 12px; border-radius: 6px; }
  .topbar .nav a:hover, .topbar .nav a.active { color: var(--accent); background: var(--surface2); }
  .main { max-width: 1400px; margin: 0 auto; padding: 20px; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  .stat-card .label { font-size: 11px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .stat-card .sub { font-size: 12px; color: var(--text2); margin-top: 2px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-bottom: 12px; }
  .card h3 { font-size: 14px; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .card h3 .count { font-size: 11px; color: var(--text2); font-weight: 400; }
  .card table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .card th { text-align: left; color: var(--text2); font-weight: 600; font-size: 11px; text-transform: uppercase; padding: 8px 4px; border-bottom: 1px solid var(--border); }
  .card td { padding: 8px 4px; border-bottom: 1px solid var(--border); }
  .card tr:last-child td { border: none; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
  .badge.online { background: rgba(34,197,94,0.15); color: var(--success); }
  .badge.offline { background: rgba(239,68,68,0.15); color: var(--danger); }
  .badge.info { background: rgba(0,212,255,0.15); color: var(--accent); }
  .badge.warn { background: rgba(234,179,8,0.15); color: var(--warning); }
  .badge.err { background: rgba(239,68,68,0.15); color: var(--danger); }
  .btn { background: var(--accent2); color: white; border: none; border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer; }
  .btn:hover { filter: brightness(1.15); }
  .btn.sm { padding: 4px 10px; font-size: 11px; }
  .btn.success { background: var(--success); }
  .btn.danger { background: var(--danger); }
  .btn.warning { background: var(--warning); color: #000; }
  .btn.outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 4px; background: var(--surface2); margin: 2px; }
  .platform-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }
  .platform-row:last-child { border: none; }
  .platform-row .info { display: flex; align-items: center; gap: 12px; }
  .platform-row .info .name { font-size: 14px; font-weight: 600; }
  .platform-row .info .desc { font-size: 12px; color: var(--text2); }
  .chart-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
  .chart-bar .bar { height: 20px; border-radius: 4px; background: linear-gradient(90deg, var(--accent2), var(--accent)); min-width: 4px; transition: width 0.5s; }
  .chart-bar .bar-label { font-size: 12px; min-width: 120px; }
  .chart-bar .bar-val { font-size: 12px; color: var(--text2); min-width: 40px; text-align: right; }
  .trend-line { display: flex; align-items: flex-end; gap: 2px; height: 80px; padding: 8px 0; }
  .trend-bar { width: 100%; border-radius: 3px 3px 0 0; background: var(--accent2); min-height: 2px; transition: height 0.5s; }
  .trend-bar:hover { opacity: 0.8; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  @media (max-width: 768px) { .grid { grid-template-columns: 1fr 1fr; } }
  @keyframes fadeIn { from { opacity:0; } to { opacity:1; } }
  .fade-in { animation: fadeIn 0.3s; }
  .spinner { width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="topbar">
  <h1>SHADDAI <span>STREAMBUDDY</span> Admin</h1>
  <div class="nav">
    <a class="active" onclick="switchTab('overview',this)">Overview</a>
    <a onclick="switchTab('platforms',this)">Platforms</a>
    <a onclick="switchTab('analytics',this)">Analytics</a>
    <a onclick="switchTab('alerts',this)">Alerts</a>
    <a onclick="switchTab('config',this)">Config</a>
    <a href="/api/v1/webui" target="_blank" style="color:var(--accent)">Chat</a>
  </div>
</div>
<div class="main">

<!-- Overview Tab -->
<div id="tab-overview" class="tab-content active">
  <div class="grid" id="statsGrid">
    <div class="stat-card"><div class="label">Total Queries</div><div class="value" id="stat-queries">-</div></div>
    <div class="stat-card"><div class="label">Active Sessions</div><div class="value" id="stat-sessions">-</div></div>
    <div class="stat-card"><div class="label">Games Detected</div><div class="value" id="stat-games">-</div></div>
    <div class="stat-card"><div class="label">Avg Response</div><div class="value" id="stat-response">-</div><div class="sub">milliseconds</div></div>
  </div>

  <div class="grid" style="grid-template-columns:1fr 1fr">
    <div class="card" id="popularGamesCard">
      <h3>Popular Games <span class="count">(7d)</span></h3>
      <div id="popularGamesList"><div class="spinner"></div></div>
    </div>
    <div class="card" id="topQueriesCard">
      <h3>Top Queries <span class="count">(7d)</span></h3>
      <div id="topQueriesList"><div class="spinner"></div></div>
    </div>
  </div>

  <div class="card">
    <h3>Daily Trend</h3>
    <div id="dailyTrend"><div class="spinner"></div></div>
  </div>
</div>

<!-- Platforms Tab -->
<div id="tab-platforms" class="tab-content">
  <div class="card">
    <h3>Integration Status</h3>
    <div id="platformList"><div class="spinner"></div></div>
  </div>
  <div class="card">
    <h3>Start Platform</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn" onclick="startPlatform('twitch')">Start Twitch</button>
      <button class="btn" onclick="startPlatform('youtube')">Start YouTube</button>
      <button class="btn success" onclick="startPlatform('discord')">Start Discord</button>
    </div>
    <div style="margin-top:8px">
      <input id="twitchChannel" placeholder="Twitch channel name" style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);width:200px;font-size:13px">
      <input id="youtubeVideo" placeholder="YouTube video ID" style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);width:200px;font-size:13px;margin-left:4px">
    </div>
    <div id="platformResult" style="margin-top:8px;font-size:13px;color:var(--text2)"></div>
  </div>
</div>

<!-- Analytics Tab -->
<div id="tab-analytics" class="tab-content">
  <div class="card">
    <h3>Platform Breakdown <span class="count">(30d)</span></h3>
    <div id="platformBreakdown"><div class="spinner"></div></div>
  </div>
  <div class="card">
    <h3>Hourly Trend <span class="count">(24h)</span></h3>
    <div id="hourlyTrend"><div class="spinner"></div></div>
  </div>
</div>

<!-- Alerts Tab -->
<div id="tab-alerts" class="tab-content">
  <div class="card">
    <h3>System Alerts <button class="btn sm outline" onclick="clearAlerts()" style="margin-left:auto">Mark All Read</button></h3>
    <div id="alertsList"><div class="spinner"></div></div>
  </div>
</div>

<!-- Config Tab -->
<div id="tab-config" class="tab-content">
  <div class="card">
    <h3>Configuration Validation</h3>
    <div id="configCheck"><div class="spinner"></div></div>
  </div>
  <div class="card">
    <h3>API Key Generator</h3>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <input id="keyLabel" placeholder="Label" value="admin-key" style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:13px">
      <select id="keyTier" style="background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:13px">
        <option value="free">Free</option>
        <option value="pro" selected>Pro</option>
        <option value="enterprise">Enterprise</option>
      </select>
      <button class="btn" onclick="generateKey()">Generate Key</button>
    </div>
    <div id="keyResult" style="margin-top:8px"></div>
  </div>
</div>

</div>

<script>
let refreshTimer = null;

function switchTab(name, el) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (el) el.classList.add('active');
  refreshTab(name);
}

function refreshTab(name) {
  if (name === 'overview') { loadOverview(); loadDailyTrend(); }
  if (name === 'platforms') loadPlatforms();
  if (name === 'analytics') { loadPlatformBreakdown(); loadHourlyTrend(); }
  if (name === 'alerts') loadAlerts();
  if (name === 'config') loadConfig();
}

// Load functions
async function loadOverview() {
  try {
    const r = await fetch('/api/v1/analytics/summary');
    const d = await r.json();
    document.getElementById('stat-queries').textContent = d.total_queries || 0;
    document.getElementById('stat-sessions').textContent = d.total_sessions || 0;
    document.getElementById('stat-games').textContent = d.games_detected || 0;
    document.getElementById('stat-response').textContent = d.avg_response_ms ? d.avg_response_ms + 'ms' : '-';
  } catch(e) {}

  try {
    const r = await fetch('/api/v1/analytics/popular-games?days=7&limit=10');
    const games = await r.json();
    const list = document.getElementById('popularGamesList');
    if (!games || games.length === 0) { list.innerHTML = '<div style="color:var(--text2);font-size:13px">No data yet</div>'; return; }
    const maxQ = Math.max(...games.map(g => g.total_queries));
    list.innerHTML = games.map(g =>
      '<div class="chart-bar fade-in"><span class="bar-label">' + escapeHtml(g.game) + '</span><div class="bar" style="width:' + ((g.total_queries / maxQ) * 100) + '%"></div><span class="bar-val">' + g.total_queries + '</span></div>'
    ).join('');
  } catch(e) {}

  try {
    const r = await fetch('/api/v1/analytics/top-queries?days=7&limit=10');
    const qs = await r.json();
    const list = document.getElementById('topQueriesList');
    if (!qs || qs.length === 0) { list.innerHTML = '<div style="color:var(--text2);font-size:13px">No data yet</div>'; return; }
    list.innerHTML = '<table><tr><th>Query</th><th>Game</th><th>Freq</th></tr>' +
      qs.map(q => '<tr class="fade-in"><td>' + escapeHtml(q.query && q.query.length > 50 ? q.query.slice(0,50)+'...' : (q.query||'')) + '</td><td>' + escapeHtml(q.game||'-') + '</td><td>' + q.frequency + '</td></tr>').join('') +
      '</table>';
  } catch(e) {}
}

async function loadDailyTrend() {
  try {
    const r = await fetch('/api/v1/analytics/daily?days=14');
    const days = await r.json();
    const el = document.getElementById('dailyTrend');
    if (!days || days.length === 0) { el.innerHTML = '<div style="color:var(--text2);font-size:13px">No data yet</div>'; return; }
    const maxQ = Math.max(...days.map(d => d.total_queries));
    el.innerHTML = '<div class="trend-line">' +
      days.map(d => {
        const h = maxQ > 0 ? (d.total_queries / maxQ) * 100 : 2;
        const dateLabel = d.date ? d.date.slice(5) : '';
        return '<div style="flex:1;display:flex;flex-direction:column;align-items:center"><div class="trend-bar" style="height:' + Math.max(h,2) + '%" title="' + d.date + ': ' + d.total_queries + ' queries, ' + (d.avg_ms||0).toFixed(0) + 'ms"></div><span style="font-size:9px;color:var(--text2);margin-top:4px">' + dateLabel + '</span></div>';
      }).join('') +
      '</div>';
  } catch(e) {}
}

async function loadPlatforms() {
  try {
    const r = await fetch('/api/v1/analytics/summary');
    const d = await r.json();
    const platforms = d.platforms || {};
    const el = document.getElementById('platformList');
    const names = {twitch:'Twitch',youtube:'YouTube',discord:'Discord',obs:'OBS Overlay'};
    el.innerHTML = Object.entries(names).map(([key,label]) =>
      '<div class="platform-row fade-in"><div class="info"><span class="badge ' + (platforms[key] ? 'online' : 'offline') + '">' + (platforms[key] ? 'ON' : 'OFF') + '</span><span class="name">' + label + '</span></div></div>'
    ).join('');
  } catch(e) {}
}

async function loadPlatformBreakdown() {
  try {
    const r = await fetch('/api/v1/analytics/platforms');
    const data = await r.json();
    const el = document.getElementById('platformBreakdown');
    if (!data || Object.keys(data).length === 0) { el.innerHTML = '<div style="color:var(--text2);font-size:13px">No data yet</div>'; return; }
    const maxQ = Math.max(...Object.values(data).map(p => p.total_queries||0));
    el.innerHTML = Object.entries(data).map(([plat, stats]) =>
      '<div class="chart-bar fade-in"><span class="bar-label">' + plat + '</span><div class="bar" style="width:' + ((stats.total_queries / maxQ) * 100) + '%"></div><span class="bar-val">' + stats.total_queries + ' queries, ' + (stats.avg_ms||0).toFixed(0) + 'ms</span></div>'
    ).join('');
  } catch(e) {}
}

async function loadHourlyTrend() {
  try {
    const r = await fetch('/api/v1/analytics/trend?hours=24');
    const hours = await r.json();
    const el = document.getElementById('hourlyTrend');
    if (!hours || hours.length === 0) { el.innerHTML = '<div style="color:var(--text2);font-size:13px">No data yet</div>'; return; }
    const maxQ = Math.max(...hours.map(h => h.queries));
    el.innerHTML = '<div class="trend-line">' +
      hours.map(h => {
        const pct = maxQ > 0 ? (h.queries / maxQ) * 100 : 2;
        const label = h.hour ? h.hour.slice(11,16) : '';
        return '<div style="flex:1;display:flex;flex-direction:column;align-items:center"><div class="trend-bar" style="height:' + Math.max(pct,2) + '%;background:var(--accent)" title="' + h.hour + ': ' + h.queries + ' queries"></div><span style="font-size:9px;color:var(--text2);margin-top:4px">' + label + '</span></div>';
      }).join('') +
      '</div>';
  } catch(e) {}
}

async function loadAlerts() {
  try {
    const r = await fetch('/api/v1/analytics/alerts?limit=50');
    const alerts = await r.json();
    const el = document.getElementById('alertsList');
    if (!alerts || alerts.length === 0) { el.innerHTML = '<div style="color:var(--text2);font-size:13px">No alerts</div>'; return; }
    el.innerHTML = '<table><tr><th>Level</th><th>Source</th><th>Message</th><th>Time</th></tr>' +
      alerts.map(a =>
        '<tr class="fade-in"><td><span class="badge ' + (a.level==='error'?'err':a.level==='warning'?'warn':'info') + '">' + a.level + '</span></td><td>' + escapeHtml(a.source) + '</td><td>' + escapeHtml(a.message) + '</td><td>' + (a.created_at ? a.created_at.slice(11,19) : '') + '</td></tr>'
      ).join('') +
      '</table>';
  } catch(e) {}
}

async function loadConfig() {
  try {
    const r = await fetch('/api/v1/config/validate');
    const d = await r.json();
    const el = document.getElementById('configCheck');
    if (d.warnings && d.warnings.length > 0) {
      el.innerHTML = '<div style="color:var(--warning)">' + d.warnings.length + ' warnings</div>' +
        d.warnings.map(w => '<div class="fade-in" style="padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">' + escapeHtml(w) + '</div>').join('');
    } else {
      el.innerHTML = '<div style="color:var(--success);font-size:14px">All config checks passed</div>';
    }
  } catch(e) {
    document.getElementById('configCheck').innerHTML = '<div style="color:var(--danger)">Could not load config</div>';
  }
}

// Actions
async function startPlatform(platform) {
  const result = document.getElementById('platformResult');
  result.innerHTML = '<span class="spinner"></span> Starting...';
  try {
    let body;
    if (platform === 'twitch') {
      const channel = document.getElementById('twitchChannel').value.trim();
      if (!channel) { result.innerHTML = '<span style="color:var(--warning)">Enter a Twitch channel name</span>'; return; }
      body = new URLSearchParams({channel, session_id: 'admin'});
    } else if (platform === 'youtube') {
      const videoId = document.getElementById('youtubeVideo').value.trim();
      if (!videoId) { result.innerHTML = '<span style="color:var(--warning)">Enter a YouTube video ID</span>'; return; }
      body = new URLSearchParams({video_id: videoId, session_id: 'admin'});
    } else {
      body = new URLSearchParams({session_id: 'admin'});
    }
    const r = await fetch('/api/v1/' + platform + '/start', { method: 'POST', body, headers: {'Content-Type':'application/x-www-form-urlencoded'} });
    const d = await r.json();
    result.innerHTML = '<span style="color:var(--success)">' + (d.status || 'Started') + '</span>';
    setTimeout(() => loadPlatforms(), 1000);
  } catch(e) {
    result.innerHTML = '<span style="color:var(--danger)">Error: ' + e.message + '</span>';
  }
}

async function clearAlerts() {
  await fetch('/api/v1/analytics/alerts/read', { method: 'POST' });
  loadAlerts();
}

async function generateKey() {
  const label = document.getElementById('keyLabel').value.trim() || 'admin-key';
  const tier = document.getElementById('keyTier').value;
  try {
    const r = await fetch('/api/v1/generate-key?label=' + encodeURIComponent(label) + '&tier=' + tier);
    const d = await r.json();
    const el = document.getElementById('keyResult');
    el.innerHTML = '<div style="background:var(--surface2);border:1px solid var(--success);border-radius:6px;padding:10px;font-size:13px">' +
      '<div style="color:var(--success);font-weight:600;margin-bottom:4px">Key Generated (' + d.tier + ')</div>' +
      '<code style="word-break:break-all;background:var(--bg);padding:6px;border-radius:4px;display:block">' + d.api_key + '</code>' +
      '<div style="color:var(--warning);margin-top:4px;font-size:12px">Save this key - it will not be shown again</div></div>';
  } catch(e) {
    document.getElementById('keyResult').innerHTML = '<span style="color:var(--danger)">Error generating key</span>';
  }
}

function escapeHtml(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// Auto-refresh overview every 10s
setInterval(() => {
  const active = document.querySelector('.tab-content.active');
  if (active) refreshTab(active.id.replace('tab-',''));
}, 10000);

// Init
loadOverview();
loadDailyTrend();
</script>
</body>
</html>"""


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard():
    return ADMIN_HTML


#
# Config Validation
#

@router.get("/config/validate")
async def check_config():
    warnings = validate_config()
    return {"status": "ok" if not warnings else "warnings", "warnings": warnings}


#
# Platform Status Endpoints
#

@router.get("/platforms")
async def get_platforms():
    await db.connect()
    cursor = await db._conn.execute("SELECT platform, is_active, started_at, error_message FROM platform_status")
    rows = await cursor.fetchall()
    platform_info = {r["platform"]: dict(r) for r in rows}

    return {
        "twitch": {
            "enabled": config.twitch.enabled,
            "channel": config.twitch.channel or "",
            "active": platform_info.get("twitch", {}).get("is_active", False),
        },
        "youtube": {
            "enabled": config.youtube.enabled,
            "active": platform_info.get("youtube", {}).get("is_active", False),
        },
        "discord": {
            "enabled": config.discord.enabled,
            "active": platform_info.get("discord", {}).get("is_active", False),
        },
        "obs_overlay": {
            "url": "/obs/overlay",
            "active": config.obs.overlay_enabled,
        },
    }
