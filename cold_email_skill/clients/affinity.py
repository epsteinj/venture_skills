"""Affinity API client – checks for recent interactions with a lead.

Affinity uses HTTP Basic auth with an empty username and the API key as
the password.  Docs: https://api-docs.affinity.co/
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


class AffinityClient:
    def __init__(self, api_key: str, base_url: str = "https://api.affinity.co") -> None:
        self._client = httpx.Client(
            base_url=base_url,
            auth=("", api_key),
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def has_recent_interaction(self, email: str, *, days: int = 90) -> bool:
        """Return True if anyone on the team has interacted with *email*
        within the last *days* days according to Affinity."""
        person_id = self._find_person_id(email)
        if person_id is None:
            return False
        return self._has_interactions_since(person_id, days=days)

    # ------------------------------------------------------------------
    # Internal API calls
    # ------------------------------------------------------------------

    def _find_person_id(self, email: str) -> int | None:
        """Search Affinity for a person by email address."""
        resp = self._client.get("/persons", params={"term": email})
        resp.raise_for_status()
        persons = resp.json().get("persons", [])
        if not persons:
            return None
        # Return the first match – Affinity dedupes on email.
        return persons[0]["id"]

    def _has_interactions_since(self, person_id: int, *, days: int) -> bool:
        """Check interaction entries on a person within the time window."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        resp = self._client.get(
            f"/persons/{person_id}/interactions",
            params={"page_size": 1},
        )
        resp.raise_for_status()
        interactions = resp.json().get("interactions", [])
        if not interactions:
            return False
        latest = interactions[0]
        interaction_date = datetime.fromisoformat(latest["date"])
        return interaction_date >= cutoff

    def close(self) -> None:
        self._client.close()
