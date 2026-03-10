"""Specter API client – fetches leads from saved searches or people lists.

Docs: https://api.tryspecter.com/api-ref/introduction

Base URL : https://app.tryspecter.com/api/v1
Auth     : X-API-Key header
Rate limit: 15 req/s (HTTP 429 on exceed)
"""

from __future__ import annotations

import httpx

from cold_email_skill.models.lead import Lead

_DEFAULT_BASE = "https://app.tryspecter.com/api/v1"


class SpecterClient:
    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Lead sources
    # ------------------------------------------------------------------

    def get_leads(self, *, limit: int = 50) -> list[Lead]:
        """Fetch leads from a people saved search or people list.

        Callers should use the more specific methods below; this is the
        convenience entry-point used by the skill orchestrator.  By
        default it delegates to get_people_list_results using the list
        ID from the SPECTER_PEOPLE_LIST_ID env var (set in config).
        """
        raise NotImplementedError(
            "Use get_people_list_results() or get_saved_search_results() directly, "
            "or configure SPECTER_PEOPLE_LIST_ID / SPECTER_SAVED_SEARCH_ID."
        )

    def get_people_list_results(self, list_id: str, *, limit: int = 50) -> list[Lead]:
        """GET /lists/people/{listId}/results — people in a Specter list."""
        resp = self._client.get(
            f"/lists/people/{list_id}/results",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return self._parse_people(resp.json())

    def get_saved_search_results(self, search_id: str, *, limit: int = 50) -> list[Lead]:
        """GET /saved-searches/people/{searchId}/results — people matching a saved search."""
        resp = self._client.get(
            f"/saved-searches/people/{search_id}/results",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return self._parse_people(resp.json())

    # ------------------------------------------------------------------
    # Person helpers
    # ------------------------------------------------------------------

    def get_person_email(self, person_id: str) -> str | None:
        """GET /people/{personId}/email — resolve a person's email."""
        resp = self._client.get(f"/people/{person_id}/email")
        resp.raise_for_status()
        data = resp.json()
        return data.get("email")

    def get_company_people(self, company_id: str) -> list[dict]:
        """GET /companies/{companyId}/people — key people at a company."""
        resp = self._client.get(f"/companies/{company_id}/people")
        resp.raise_for_status()
        return resp.json().get("results", resp.json() if isinstance(resp.json(), list) else [])

    def search_company(self, query: str) -> list[dict]:
        """GET /companies/search?query=... — search by name or domain."""
        resp = self._client.get("/companies/search", params={"query": query})
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else resp.json().get("results", [])

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_people(self, data: dict | list) -> list[Lead]:
        """Map Specter person objects to our Lead model.

        The exact response shape may vary; we handle both a top-level
        list and a ``{"results": [...]}`` envelope.
        """
        items = data if isinstance(data, list) else data.get("results", [])

        leads: list[Lead] = []
        for item in items:
            email = item.get("email") or item.get("work_email") or item.get("personal_email")
            if not email:
                continue

            leads.append(
                Lead(
                    specter_id=str(item.get("id", "")),
                    first_name=item.get("first_name", ""),
                    last_name=item.get("last_name", ""),
                    email=email,
                    company=item.get("company", {}).get("name", "") if isinstance(item.get("company"), dict) else item.get("company_name", item.get("company", "")),
                    title=item.get("title") or item.get("job_title"),
                    linkedin_url=item.get("linkedin_url") or item.get("linkedin"),
                )
            )
        return leads

    def close(self) -> None:
        self._client.close()
