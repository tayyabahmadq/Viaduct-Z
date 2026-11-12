"""Runtime configuration.

Deliberately dependency-free: a tiny .env reader instead of python-dotenv so the
container has one less moving part. Real environment variables always win.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    seed_on_start: bool
    start_balance_cents: int
    credit_ceiling_cents: int
    rate_limit_per_minute: int
    peer_online_seconds: int
    public_base_url: str
    paypal_client_id: str
    paypal_client_secret: str
    paypal_base_url: str
    paypal_currency: str
    ai_api_key: str
    ai_base_url: str
    ai_model: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./viaduct.db"),
        seed_on_start=os.getenv("SEED_ON_START", "1") == "1",
        start_balance_cents=int(os.getenv("START_BALANCE_CENTS", "250000")),
        credit_ceiling_cents=int(os.getenv("CREDIT_CEILING_CENTS", "500000")),
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")),
        peer_online_seconds=int(os.getenv("PEER_ONLINE_SECONDS", "180")),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        paypal_client_id=os.getenv("PAYPAL_CLIENT_ID", ""),
        paypal_client_secret=os.getenv("PAYPAL_CLIENT_SECRET", ""),
        paypal_base_url=os.getenv(
            "PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"
        ).rstrip("/"),
        paypal_currency=os.getenv("PAYPAL_CURRENCY", "USD"),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        ai_model=os.getenv("AI_MODEL", "gpt-5-nano"),
    )
