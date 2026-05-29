import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_sec: float = 30.0
    device_index: Optional[int] = None
    silence_threshold: float = 0.01
    silence_duration_sec: float = 2.0


@dataclass
class STTConfig:
    provider: str = "whisper"
    model: str = "base"
    language: str = "en"
    api_key: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass
class ScreenConfig:
    fps: int = 1
    region: Optional[tuple[int, int, int, int]] = None
    window_title: Optional[str] = None
    capture_driver: str = "mss"


@dataclass
class VisionConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    endpoint: Optional[str] = None
    prompt_template: str = (
        "You are a game analysis assistant. Analyze this gameplay screenshot. "
        "Identify: 1) The game title 2) The current scene/level/location "
        "3) Visible UI elements (health, quest markers, inventory) "
        "4) Enemies or NPCs visible 5) What the player seems to be doing "
        "6) Any tutorial hints or objectives on screen. "
        "Return as JSON with keys: game, location, ui_elements, entities, player_action, objectives"
    )


@dataclass
class WebSearchConfig:
    provider: str = "google"
    api_key: Optional[str] = None
    search_engine_id: Optional[str] = None
    max_results: int = 5
    rate_limit_per_min: int = 60


@dataclass
class RedditConfig:
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    user_agent: str = "STREAMBUDDY/1.0"
    subreddits: list = field(default_factory=lambda: [
        "gamingsuggestions", "tips", "walkthrough", "gameguides"
    ])


@dataclass
class WikiConfig:
    enabled_sources: list = field(default_factory=lambda: [
        "fextralife", "fandom", "ign_wikis", "gamepedia"
    ])
    rate_limit_per_min: int = 30


@dataclass
class CacheConfig:
    backend: str = "sqlite"
    ttl_seconds: int = 86400
    db_path: str = "data/cache.db"


@dataclass
class TwitchConfig:
    enabled: bool = False
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    channel: str = ""
    auto_reply: bool = True
    monitor_chat: bool = True


@dataclass
class OBSConfig:
    overlay_enabled: bool = True
    overlay_port: int = 8081
    help_card_duration_sec: int = 30


@dataclass
class APIConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1
    cors_origins: list = field(default_factory=lambda: ["*"])
    rate_limit_per_min: int = 30
    max_concurrent_jobs: int = 10


@dataclass
class TierConfig:
    name: str = "free"
    rate_limit_per_min: int = 10
    max_queries_per_day: int = 100
    max_sources: int = 3
    allow_vision: bool = False
    allow_voice: bool = False
    allow_twitch: bool = False


TIERS = {
    "free": TierConfig("free", 10, 100, 3, False, False, False),
    "pro": TierConfig("pro", 60, 1000, 10, True, True, True),
    "enterprise": TierConfig("enterprise", 300, 10000, 25, True, True, True),
}


@dataclass
class AppConfig:
    log_level: str = "INFO"
    data_dir: str = "data"
    max_history_per_user: int = 100
    auto_detect_game: bool = True
    debug: bool = False

    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    wiki: WikiConfig = field(default_factory=WikiConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    obs: OBSConfig = field(default_factory=OBSConfig)
    api: APIConfig = field(default_factory=APIConfig)


def load_config_from_env() -> AppConfig:
    cfg = AppConfig()

    cfg.log_level = os.getenv("LOG_LEVEL", "INFO")
    cfg.data_dir = os.getenv("DATA_DIR", "data")
    cfg.debug = os.getenv("DEBUG", "false").lower() == "true"

    cfg.stt.provider = os.getenv("STT_PROVIDER", "openai")
    cfg.stt.model = os.getenv("STT_MODEL", "whisper-1")
    cfg.stt.api_key = os.getenv("STT_API_KEY") or os.getenv("OPENAI_API_KEY")
    cfg.stt.endpoint = os.getenv("STT_ENDPOINT")

    cfg.vision.provider = os.getenv("VISION_PROVIDER", "openai")
    cfg.vision.model = os.getenv("VISION_MODEL", "gpt-4o-mini")
    cfg.vision.api_key = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY")
    cfg.vision.endpoint = os.getenv("VISION_ENDPOINT")

    cfg.web_search.provider = os.getenv("SEARCH_PROVIDER", "google")
    cfg.web_search.api_key = os.getenv("SEARCH_API_KEY") or os.getenv("GOOGLE_API_KEY")
    cfg.web_search.search_engine_id = os.getenv("SEARCH_ENGINE_ID") or os.getenv("GOOGLE_CX")

    cfg.reddit.client_id = os.getenv("REDDIT_CLIENT_ID")
    cfg.reddit.client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    cfg.twitch.enabled = os.getenv("TWITCH_ENABLED", "false").lower() == "true"
    cfg.twitch.client_id = os.getenv("TWITCH_CLIENT_ID")
    cfg.twitch.client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    cfg.twitch.channel = os.getenv("TWITCH_CHANNEL", "")

    cfg.api.host = os.getenv("API_HOST", "0.0.0.0")
    cfg.api.port = int(os.getenv("API_PORT", "8080"))
    cfg.api.workers = int(os.getenv("API_WORKERS", "1"))

    Path(cfg.data_dir).mkdir(parents=True, exist_ok=True)
    Path(os.path.dirname(cfg.cache.db_path)).mkdir(parents=True, exist_ok=True)

    return cfg


config = load_config_from_env()
