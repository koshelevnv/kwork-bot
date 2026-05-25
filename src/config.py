from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Settings:
    tg_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    admin_ids: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
    ])
    categories: list[str] = field(default_factory=lambda: [
        x.strip() for x in os.getenv("KWORK_CATEGORIES", "41").split(",") if x.strip()
    ])
    poll_interval: int = field(default_factory=lambda: int(os.getenv("POLL_INTERVAL_SECONDS", "30")))
