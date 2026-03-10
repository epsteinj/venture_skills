"""Affinity CRM API client – checks for recent interactions with a lead.

Affinity v1 uses HTTP Basic auth with an empty username and the API key
as the password.  Docs: https://api-docs.affinity.co/

Key endpoints used:
  GET /persons?term={email}&with_interaction_dates=true
    → returns {"persons": [...], "next_page_token": ...}
    → each person has an `interaction_dates` dict with fields like
       last_email_date, last_event_date, etc. (ISO 8601 strings)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)


class AffinityClient:
    def __init__(self, api_key: str, base_url: str = "https://api.affinity.co") -> None:
        self._client = httpx.Client(
            base_url=base_url,
            auth=("", api_key),  # v1: Basic auth, empty user, key as password
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def has_recent_interaction(self, email: str, *, days: int = 90) -> bool:
        """Return True if anyone on the team has interacted with *email*
        within the last *days* days according to Affinity.

        Uses the v1 ``/persons`` search with ``with_interaction_dates=true``
        to get last-interaction timestamps inline (no separate call needed).
        """
        person = self._find_person_with_interactions(email)
        if person is None:
            return False

        interaction_dates = person.get("interaction_dates") or {}
        if not interaction_dates:
            return False

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

        # Check all known date fields — any interaction within the window counts
        date_fields = [
            "last_email_date",
            "last_event_date",
            "last_chat_message_date",
            "last_interaction_date",
        ]

        for field in date_fields:
            raw = interaction_dates.get(field)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt >= cutoff:
                    logger.debug(
                        "Affinity: %s has recent %s (%s)", email, field, raw,
                    )
                    return True
            except (ValueError, TypeError):
                continue

        return False

    # ------------------------------------------------------------------
    # Internal API calls
    # ------------------------------------------------------------------

    def _find_person_with_interactions(self, email: str) -> dict | None:
        """Search Affinity for a person by email, with interaction dates.

        GET /persons?term={email}&with_interaction_dates=true
        Returns the first matching person dict (with interaction_dates
        embedded), or None.
        """
        resp = self._client.get(
            "/persons",
            params={"term": email, "with_interaction_dates": "true"},
        )
        resp.raise_for_status()
        persons = resp.json().get("persons", [])
        if not persons:
            return None
        return persons[0]

    def close(self) -> None:
        self._client.close()
