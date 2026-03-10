from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


class Settings:
    # Specter
    specter_api_key: str = _require("SPECTER_API_KEY")
    specter_base_url: str = os.getenv("SPECTER_BASE_URL", "https://api.specter.com/v1")

    # Affinity
    affinity_api_key: str = _require("AFFINITY_API_KEY")
    affinity_base_url: str = os.getenv("AFFINITY_BASE_URL", "https://api.affinity.co")

    # N8N
    n8n_webhook_url: str = _require("N8N_WEBHOOK_URL")

    # Behaviour
    days_since_last_interaction: int = int(os.getenv("DAYS_SINCE_LAST_INTERACTION", "90"))
    sender_email: str = _require("SENDER_EMAIL")
