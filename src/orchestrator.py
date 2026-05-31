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
from src.strategy.swarm import StrategySwarm, SwarmConsensus
from src.strategy.strategies import get_boss_strategy, get_game_tips, BOSS_STRATEGIES
from src.i18n.lang import detect_language, HELP_KEYWORDS, CONTEXT_CATEGORIES

logger = logging.getLogger(__name__)

KNOWN_GAMES = [
    # FromSoftware / Souls-like
    "elden ring", "dark souls", "dark souls 2", "dark souls 3", "sekiro",
    "bloodborne", "demon's souls", "lies of p", "hollow knight",
    "mortal shell", "the surge", "remnant", "nioh", "nioh 2", "wo long",
    "star wars jedi fallen order", "star wars jedi survivor", "ashen",
    "code vein", "lords of the fallen", "steelrising", "thymesia",
    # Rockstar / Open World
    "grand theft auto", "gta", "gta 5", "gta v", "gta online", "red dead redemption",
    "rdr2", "red dead redemption 2", "bully", "max payne", "la noire",
    # Bethesda
    "skyrim", "oblivion", "morrowind", "daggerfall", "fallout", "fallout 2",
    "fallout 3", "fallout new vegas", "fallout 4", "fallout 76",
    "starfield", "the elder scrolls online",
    # Nintendo
    "zelda", "breath of the wild", "tears of the kingdom", "ocarina of time",
    "majora's mask", "twilight princess", "wind waker", "mario", "super mario",
    "mario odyssey", "mario kart", "smash bros", "pokemon", "pokemon go",
    "pokemon scarlet", "pokemon violet", "metroid", "fire emblem",
    "splatoon", "animal crossing", "xenoblade", "kirby", "donkey kong",
    # CD Projekt
    "witcher 3", "witcher", "cyberpunk 2077", "cyberpunk",
    # Sony / PlayStation
    "god of war", "god of war ragnarok", "spider-man", "spider-man 2",
    "horizon zero dawn", "horizon forbidden west", "the last of us",
    "uncharted", "ghost of tsushima", "days gone", "ratchet and clank",
    "returnal", "demons souls remake", "bloodborne",
    # Final Fantasy / JRPG
    "final fantasy", "ff7", "ff7 remake", "ff14", "ff16", "ff15", "ff10",
    "chrono trigger", "dragon quest", "kingdom hearts", "persona", "persona 5",
    "nier", "nier automata", "tales of", "star ocean",
    # Western RPG
    "baldur's gate 3", "baldurs gate 3", "bg3", "divinity", "divinity original sin",
    "mass effect", "dragon age", "kingdom come", "kotor", "pillars of eternity",
    "pathfinder", "disco elysium", "wasteland", "outer worlds",
    # MMO / Online
    "world of warcraft", "wow", "final fantasy 14", "ff14", "guild wars 2",
    "elder scrolls online", "eso", "destiny 2", "warframe", "path of exile", "poe",
    "lost ark", "albion", "runescape", "osrs", "new world",
    # MOBA / Battle Royale
    "league of legends", "valorant", "dota 2", "heroes of the storm",
    "fortnite", "pubg", "apex legends", "warzone", "call of duty warzone",
    "overwatch", "overwatch 2", "smite", "rainbow six siege", "siege",
    # FPS / Shooter
    "call of duty", "call of duty black ops", "call of duty modern warfare",
    "battlefield", "halo", "doom", "doom eternal", "half-life", "portal",
    "counter strike", "csgo", "cs2", "team fortress 2", "titanfall",
    "far cry", "crysis", "metro", "bioshock",
    # Survival / Crafting
    "minecraft", "terraria", "stardew valley", "subnautica", "the forest",
    "sons of the forest", "ark survival", "rust", "valheim", "project zomboid",
    "7 days to die", "green hell", "stranded deep",
    # Factory / Automation
    "factorio", "satisfactory", "dyson sphere program", "shapez",
    "captain of industry", "mindustry",
    # Horror
    "resident evil", "silent hill", "dead space", "alan wake", "outlast",
    "amnesia", "alien isolation", "evil within", "until dawn", "darkwood",
    "signalis", "tormented souls",
    # Action / Hack and Slash
    "devil may cry", "bayonetta", "metal gear", "mg rising", "ninja gaiden",
    "dying light", "dead island", "left 4 dead", "back 4 blood",
    "warhammer 40k space marine", "shadow of war", "shadow of mordor",
    # Racing
    "forza horizon", "forza motorsport", "gran turismo", "need for speed",
    "assetto corsa", "iracing", "dirt rally", "f1",
    # Sports
    "fifa", "ea sports fc", "madden", "nba 2k", "mlb the show", "wwe",
    "football manager", "pga tour",
    # Strategy
    "civilization", "civ 6", "age of empires", "starcraft", "total war",
    "xcom", "crusader kings", "europa universalis", "stellaris",
    "rimworld", "frostpunk", "they are billions", "against the storm",
    # Indie
    "hades", "hollow knight", "celeste", "dead cells", "slay the spire",
    "binding of isaac", "enter the gungeon", "risk of rain 2",
    "vampire survivors", "balatro", "stray", "outer wilds", "undertale",
    "cuphead", "shovel knight", "hotline miami", "katana zero",
    "disco elysium", "inscryption", "tunic", "return of the obra dinn",
    # Fighting
    "street fighter", "mortal kombat", "tekken", "guilty gear",
    "dragon ball fighterz", "super smash bros",
    # MMORPG
    "world of warcraft", "wow", "final fantasy 14", "ff14", "black desert",
    "guild wars 2", "eso", "runescape", "oldschool runescape",
    "maple story", "maplestory",
]

BOSS_TO_GAME = {
    # Elden Ring
    "malenia": "Elden Ring", "radahn": "Elden Ring", "godrick": "Elden Ring",
    "margit": "Elden Ring", "mohg": "Elden Ring", "maliketh": "Elden Ring",
    "godfrey": "Elden Ring", "hoarah loux": "Elden Ring", "rennala": "Elden Ring",
    "rykard": "Elden Ring", "fire giant": "Elden Ring",
    "tree sentinel": "Elden Ring", "astel": "Elden Ring",
    # Dark Souls
    "midir": "Dark Souls 3", "nameless king": "Dark Souls 3",
    "sister friede": "Dark Souls 3", "gael": "Dark Souls 3",
    "pontiff sulyvahn": "Dark Souls 3", "abyss watchers": "Dark Souls 3",
    "dancer": "Dark Souls 3", "soul of cinder": "Dark Souls 3",
    "artorias": "Dark Souls", "manus": "Dark Souls", "kalameet": "Dark Souls",
    # Bloodborne
    "orphan of kos": "Bloodborne", "father gascoigne": "Bloodborne",
    "amygdala": "Bloodborne", "lady maria": "Bloodborne",
    "gehrman": "Bloodborne", "moon presence": "Bloodborne",
    "ludwig": "Bloodborne", "laurence": "Bloodborne",
    # Sekiro
    "isshin": "Sekiro", "genichiro": "Sekiro", "owl father": "Sekiro",
    "demon of hatred": "Sekiro", "lady butterfly": "Sekiro",
    "guardian ape": "Sekiro", "corrupted monk": "Sekiro",
    "divine dragon": "Sekiro",
    # Other
    "omega weapon": "Final Fantasy", "sephiroth": "Final Fantasy 7",
    "safer sephiroth": "Final Fantasy 7", "ultima weapon": "Final Fantasy",
}

BOSS_KEYWORDS = [
    # Elden Ring
    "malenia", "radahn", "godrick", "margit", "mohg", "maliketh",
    "godfrey", "hoarah loux", "rennala", "rykard", "fire giant",
    "tree sentinel", "astel", "mimic tear", "malformed star",
    # Dark Souls
    "midir", "nameless king", "sister friede", "orphan of kos",
    "artorias", "manus", "kalameet", "pontiff sulyvahn",
    "aldrich", "abyss watchers", "dancer", "twin princes",
    "soul of cinder", "gael", "champion gundyr",
    # Bloodborne
    "father gascoigne", "amygdala", "micolash", "gehrman",
    "moon presence", "ludwig", "laurence", "living failures",
    "lady maria", "kos orphan", "ebrietas", "martyr logarius",
    # Sekiro
    "isshin", "genichiro", "owl father", "demon of hatred",
    "lady butterfly", "guardian ape", "corrupted monk",
    "true monk", "divine dragon",
    # Other
    "omega weapon", "sephiroth", "safer sephiroth", "ultima weapon",
    "emerald weapon", "ruby weapon", "diamond weapon",
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
    for boss_name, game_name in BOSS_TO_GAME.items():
        if boss_name in query_lower:
            return game_name
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
        self.current_language = "en"
        self.session_history: list[AssistResult] = []
        self.strategy_swarm = StrategySwarm()
        self.youtube_finder = None

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

        self.detect_player_language(query)

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

        if boss and self.strategy_swarm.agents:
            from src.config import config
            if config.strategy.swarm_enabled:
                try:
                    swarm_result = self.analyze_boss_strategy(boss)
                    if swarm_result and swarm_result.swarm_confidence > 0.5:
                        strat_section = f"\n\n## 🧠 Swarm Strategy for {boss}"
                        strat_section += f"\n**Agreement:** {swarm_result.agreement_level * 100:.0f}%"
                        strat_section += f"\n**Confidence:** {swarm_result.swarm_confidence * 100:.0f}%"
                        strat_section += f"\n\n**Top Recommendations:**"
                        for rec in swarm_result.top_recommendations[:3]:
                            strat_section += f"\n- {rec}"
                        if swarm_result.consensus_loadout:
                            strat_section += f"\n\n**Recommended Loadout:**"
                            for item in swarm_result.consensus_loadout[:5]:
                                strat_section += f"\n- {item}"
                        result.answer += strat_section
                        result.confidence = max(result.confidence, swarm_result.swarm_confidence)
                except Exception as e:
                    logger.warning(f"Swarm analysis failed: {e}")

        result.processing_time_ms = (datetime.now() - start).total_seconds() * 1000
        self.session_history.append(result)

        return result

    def detect_player_language(self, text: str) -> str:
        self.current_language = detect_language(text)
        return self.current_language

    def get_localized_keywords(self) -> list[str]:
        return HELP_KEYWORDS.get(self.current_language, HELP_KEYWORDS["en"])

    def get_localized_context(self) -> dict:
        return CONTEXT_CATEGORIES.get(self.current_language, CONTEXT_CATEGORIES["en"])

    async def analyze_boss_strategy(self, boss_name: str, game: str = "") -> Optional[SwarmConsensus]:
        return self.strategy_swarm.analyze_boss(boss_name, game or self.current_game)

    def get_boss_info(self, boss_name: str):
        return get_boss_strategy(boss_name)

    def get_game_genre_tips(self, genre: str) -> list[str]:
        return get_game_tips(genre)

    def list_known_bosses(self) -> list[dict]:
        return [
            {"name": k.replace("_", " ").title(), "game": v["game"]}
            for k, v in BOSS_STRATEGIES.items()
        ]

    async def find_youtube_guide(self, boss: str, game: str = "") -> Optional[dict]:
        game_name = game or self.current_game
        if not game_name:
            return None
        try:
            from src.web.youtube_transcript import YouTubeTranscriptFinder
            from src.config import config
            if config.youtube.api_key:
                finder = YouTubeTranscriptFinder(api_key=config.youtube.api_key)
                return await finder.find_guide_for_boss(game_name, boss)
        except Exception as e:
            logger.warning(f"YouTube guide search failed: {e}")
        return None

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
