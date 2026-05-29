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
from src.config import config, TIERS

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
    if req.game:
        orch.current_game = req.game

    result = await orch.process_text_query(req.query)

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
  <div><h1>Game Assist AI <span class="badge">v2.0</span></h1></div>
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

    twitch = TwitchStreamIntegration(
        client_id=config.twitch.client_id,
        client_secret=config.twitch.client_secret,
    )
    twitch.orch = _get_orchestrator(session_id)
    asyncio.create_task(twitch.monitor_chat(channel))
    return {"status": "started", "channel": channel, "session_id": session_id}


@router.post("/twitch/stop")
async def stop_twitch():
    return {"status": "stopped"}


@router.post("/youtube/start")
async def start_youtube(
    video_id: str = Form(...),
    session_id: str = Form("default"),
):
    from src.youtube.integration import YouTubeStreamIntegration

    yt = YouTubeStreamIntegration(api_key=config.youtube.api_key)
    yt.orch = _get_orchestrator(session_id)
    asyncio.create_task(yt.monitor_chat(video_id))
    return {"status": "started", "video_id": video_id, "session_id": session_id}


@router.post("/discord/start")
async def start_discord(session_id: str = Form("default")):
    from src.discord_bot.bot import DiscordBotIntegration

    bot = DiscordBotIntegration(token=config.discord.token)
    bot.orch = _get_orchestrator(session_id)
    asyncio.create_task(bot.start())
    return {"status": "started", "session_id": session_id}


@router.get("/platforms")
async def get_platforms():
    return {
        "twitch": {
            "enabled": config.twitch.enabled,
            "channel": config.twitch.channel or "",
        },
        "youtube": {
            "enabled": config.youtube.enabled,
        },
        "discord": {
            "enabled": config.discord.enabled,
        },
        "obs_overlay": {
            "url": "/obs/overlay",
        },
    }
