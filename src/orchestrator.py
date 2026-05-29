import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.voice import AudioCapture, SpeechToText
from src.gameplay import ScreenCapture, VisionAnalyzer
from src.web import WebSearch, RedditScraper, WikiScraper

logger = logging.getLogger(__name__)

KNOWN_GAMES = [
    "elden ring", "dark souls", "dark souls 2", "dark souls 3", "sekiro", "bloodborne",
    "demon's souls", "lies of p", "hollow knight", "zelda", "breath of the wild",
    "tears of the kingdom", "skyrim", "oblivion", "fallout", "fallout 4",
    "call of duty", "warzone", "fortnite", "minecraft", "terraria",
    "league of legends", "valorant", "csgo", "counter strike", "dota 2",
    "overwatch", "apex legends", "pubg", "rocket league", "grand theft auto",
    "gta", "red dead redemption", "rdr2", "witcher 3", "cyberpunk 2077",
    "god of war", "spider-man", "horizon", "final fantasy", "ff7",
    "baldur's gate 3", "baldurs gate 3", "bg3", "divinity", "world of warcraft", "wow",
    "diablo", "path of exile", "poe", "stardew valley", "factorio",
    "satisfactory", "subnautica", "resident evil", "silent hill",
    "dead by daylight", "dbd", "monster hunter", "mario", "pokemon",
    "starfield", "mass effect", "bioshock", "doom", "half-life",
    "portal", "destiny 2", "warframe", "rainbow six", "siege",
]

BOSS_KEYWORDS = [
    "malenia", "radahn", "godrick", "margit", "mohg", "maliketh",
    "godfrey", "hoarah loux", "rennala", "rykard", "fire giant",
    "midir", "nameless king", "sister friede", "orphan of kos",
    "isshin", "genichiro", "owl father", "demon of hatred",
]


@dataclass
class AssistResult:
    query: str = ""
    game: str = ""
    topic: str = ""
    voice_text: str = ""
    vision_analysis: dict = field(default_factory=dict)
    web_results: list = field(default_factory=list)
    reddit_results: list = field(default_factory=list)
    wiki_results: list = field(default_factory=list)
    answer: str = ""
    confidence: float = 0.0
    sources: list = field(default_factory=list)
    processing_time_ms: float = 0.0
    timestamp: str = ""


def extract_game_from_query(query: str) -> str:
    query_lower = query.lower()
    for game in KNOWN_GAMES:
        if game in query_lower:
            return game.title()
    for boss in BOSS_KEYWORDS:
        if boss in query_lower:
            return ""
    return ""


def extract_boss_from_query(query: str) -> str:
    query_lower = query.lower()
    for boss in BOSS_KEYWORDS:
        if boss in query_lower:
            return boss.title()
    return ""


def clean_url(url: str) -> bool:
    skip_patterns = [
        r'\.(woff2?|ttf|eot|svg|ico|png|jpg|jpeg|gif|css|js)(\?|$)',
        r'fonts\.googleapis',
        r'gravatar\.com',
        r'wp-content',
        r'static\d*\.',
    ]
    for pat in skip_patterns:
        if re.search(pat, url, re.I):
            return False
    return True


def filter_results(results: list) -> list:
    seen = set()
    filtered = []
    for r in results:
        url = r.get("link", "") if isinstance(r, dict) else ""
        if not url or not clean_url(url):
            continue
        if url in seen:
            continue
        snippet = r.get("snippet", "") if isinstance(r, dict) else ""
        title = r.get("title", "") if isinstance(r, dict) else ""
        if not snippet and not title:
            continue
        seen.add(url)
        filtered.append(r)
    return filtered


class GameAssistOrchestrator:
    def __init__(self):
        self.audio = AudioCapture()
        self.stt = SpeechToText()
        self.screen = ScreenCapture()
        self.vision = VisionAnalyzer()
        self.web = WebSearch()
        self.reddit = RedditScraper()
        self.wiki = WikiScraper()

        self.current_game = ""
        self.session_history: list[AssistResult] = []

    async def process_voice_command(self, duration: float = 5.0) -> AssistResult:
        start = datetime.now()

        logger.info("Capturing audio...")
        audio = await self.audio.capture_from_mic(duration=duration)

        logger.info("Transcribing...")
        text = await self.stt.transcribe(audio)

        if not text.strip():
            return AssistResult(processing_time_ms=0, timestamp=datetime.now().isoformat())

        is_help, keyword = await self.stt.detect_help_request(text)

        result = AssistResult(
            query=text,
            voice_text=text,
            timestamp=datetime.now().isoformat(),
        )

        if not is_help:
            result.answer = "No help request detected."
            result.processing_time_ms = (datetime.now() - start).total_seconds() * 1000
            return result

        context = await self.stt.extract_game_context(text)
        result.topic = ", ".join(context["categories"])
        result.game = self.current_game

        if not result.game:
            extracted = extract_game_from_query(text)
            if extracted:
                result.game = extracted
                self.current_game = extracted

        try:
            frame = await self.screen.capture_frame()
            if frame is not None:
                logger.info("Analyzing gameplay frame...")
                if not self.current_game:
                    self.current_game = await self.vision.extract_game_title(frame)
                result.game = self.current_game

                vision_data = await self.vision.analyze_frame(frame, context=text)
                result.vision_analysis = vision_data

                if not result.game and "game" in vision_data:
                    result.game = vision_data["game"]
        except Exception:
            pass

        logger.info(f"Searching web for: {result.game or text} - {text}")
        search_tasks = [
            self.web.search_walkthrough(result.game or text, text),
            self.reddit.search_game_tips(result.game or text, text),
            self.wiki.search_wiki(result.game or text, text),
        ]

        web_res, reddit_res, wiki_res = await asyncio.gather(*search_tasks, return_exceptions=True)

        result.web_results = filter_results(web_res) if isinstance(web_res, list) else []
        result.reddit_results = filter_results(reddit_res) if isinstance(reddit_res, list) else []
        result.wiki_results = filter_results(wiki_res) if isinstance(wiki_res, list) else []

        all_sources = result.web_results + result.reddit_results + result.wiki_results
        result.sources = [s.get("link", "") for s in all_sources if isinstance(s, dict)]
        result.confidence = min(1.0, len(all_sources) / 5)

        result.answer = await self._generate_answer(result)
        result.processing_time_ms = (datetime.now() - start).total_seconds() * 1000
        self.session_history.append(result)

        logger.info(f"Completed in {result.processing_time_ms:.0f}ms")
        return result

    async def process_text_query(self, query: str) -> AssistResult:
        start = datetime.now()

        result = AssistResult(
            query=query,
            voice_text=query,
            timestamp=datetime.now().isoformat(),
        )

        context = await self.stt.extract_game_context(query)
        result.topic = ", ".join(context["categories"])

        result.game = self.current_game
        if not result.game:
            extracted = extract_game_from_query(query)
            if extracted:
                result.game = extracted
                self.current_game = extracted

        boss = extract_boss_from_query(query)
        if boss:
            result.topic = f"boss: {boss}" + (", " + result.topic if result.topic else "")

        try:
            frame = await self.screen.capture_frame()
            if frame is not None:
                if not self.current_game:
                    self.current_game = await self.vision.extract_game_title(frame)
                result.game = self.current_game

                vision_data = await self.vision.analyze_frame(frame, context=query)
                result.vision_analysis = vision_data

                if not result.game and "game" in vision_data:
                    result.game = vision_data["game"]
        except Exception:
            pass

        logger.info(f"Searching for: {result.game or query} - {query}")
        search_tasks = [
            self.web.search_walkthrough(result.game or query, query),
            self.reddit.search_game_tips(result.game or query, query),
            self.wiki.search_wiki(result.game or query, query),
        ]

        web_res, reddit_res, wiki_res = await asyncio.gather(*search_tasks, return_exceptions=True)

        result.web_results = filter_results(web_res) if isinstance(web_res, list) else []
        result.reddit_results = filter_results(reddit_res) if isinstance(reddit_res, list) else []
        result.wiki_results = filter_results(wiki_res) if isinstance(wiki_res, list) else []

        all_sources = result.web_results + result.reddit_results + result.wiki_results
        result.sources = [s.get("link", "") for s in all_sources if isinstance(s, dict)]
        result.confidence = min(1.0, len(all_sources) / 5)

        result.answer = await self._generate_answer(result)
        result.processing_time_ms = (datetime.now() - start).total_seconds() * 1000
        self.session_history.append(result)

        return result

    async def _generate_answer(self, result: AssistResult) -> str:
        try:
            from openai import OpenAI
            client = OpenAI()

            context_parts = []
            if result.game:
                context_parts.append(f"Game: {result.game}")
            if result.topic:
                context_parts.append(f"Topic: {result.topic}")
            if result.vision_analysis:
                context_parts.append(f"Screen context: {json.dumps(result.vision_analysis)}")

            web_text = "\n".join(
                f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}"
                for r in (result.web_results + result.reddit_results + result.wiki_results)[:5]
            ) or "No web results found."

            prompt = (
                "You are a real-time game assistant. Answer the player's question concisely "
                "with specific, actionable advice. Use bullet points for steps. "
                "Keep it under 300 words.\n\n"
                f"Player: {result.query}\n\n"
                + ("\n".join(context_parts) + "\n\n" if context_parts else "") +
                f"Search results:\n{web_text}\n\n"
                "Answer:"
            )

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=600,
                    temperature=0.3,
                ),
            )

            ai_answer = response.choices[0].message.content.strip()
            return self._format_answer(ai_answer, result.web_results + result.reddit_results + result.wiki_results)

        except Exception as e:
            logger.warning(f"AI generation failed ({e}), using fallback")
            return self._build_fallback_answer(result)

    def _build_fallback_answer(self, result: AssistResult) -> str:
        parts = []
        game_line = result.game or "this game"
        topic_line = f" ({result.topic})" if result.topic else ""

        all_results = result.web_results + result.reddit_results + result.wiki_results
        if all_results:
            snippets = []
            for r in all_results[:3]:
                snippet = r.get("snippet", "") if isinstance(r, dict) else ""
                if snippet:
                    snippets.append(snippet.strip()[:150])
            if snippets:
                parts.append(f"Based on search results for **{game_line}**{topic_line}:\n")
                parts.extend(f"> {s}" for s in snippets)

        if all_results:
            parts.append(f"\n## Results for **{game_line}**{topic_line}")
            for r in all_results[:7]:
                title = r.get("title", "Link") if isinstance(r, dict) else "Link"
                url = r.get("link", r) if isinstance(r, dict) else r
                snippet = r.get("snippet", "") if isinstance(r, dict) else ""
                if url and clean_url(url):
                    parts.append(f"\n### [{title}]({url})")
                    if snippet:
                        parts.append(f"> {snippet[:200]}")

        if not parts:
            parts.append(f"No results found for: {result.query}")

        return "\n".join(parts)

    def _format_answer(self, answer: str, sources: list) -> str:
        seen = set()
        source_lines = []
        for s in sources[:5]:
            if isinstance(s, dict):
                url = s.get("link", "")
                title = s.get("title", "Source")
            else:
                url = s
                title = "Link"
            if url and url not in seen:
                seen.add(url)
                source_lines.append(f"- [{title}]({url})")

        if source_lines:
            answer += "\n\n**Sources:**\n" + "\n".join(source_lines)

        return answer
