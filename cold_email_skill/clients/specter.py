"""Specter API client – fetches leads from saved searches or people lists.

Docs: https://api.tryspecter.com/api-ref/introduction

Base URL  : https://app.tryspecter.com/api/v1
Auth      : X-API-Key header
Rate limit: 15 req/s (HTTP 429 on exceed)
Pagination: page (0-based) + limit (default 50, max 5000)
Credits   : 1 per result returned
"""

from __future__ import annotations

import logging

import httpx

from cold_email_skill.models.lead import Lead

logger = logging.getLogger(__name__)

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
        """Fallback used by test fakes. Real callers should use
        get_people_list_results() or get_saved_search_results().
        """
        raise NotImplementedError(
            "Use get_people_list_results() or get_saved_search_results(), "
            "or set SPECTER_PEOPLE_LIST_ID / SPECTER_SAVED_SEARCH_ID."
        )

    def get_people_list_results(self, list_id: str, *, limit: int = 50) -> list[Lead]:
        """GET /lists/people/{listId}/results

        Returns full person profiles. Email is NOT included — call
        resolve_lead_email() afterwards.
        """
        results = self._paginate(f"/lists/people/{list_id}/results", limit=limit)
        return self._parse_people(results)

    def get_saved_search_results(self, search_id: str, *, limit: int = 50) -> list[Lead]:
        """GET /searches/people/{searchId}/results

        Returns full person profiles. Email is NOT included — call
        resolve_lead_email() afterwards.
        """
        results = self._paginate(f"/searches/people/{search_id}/results", limit=limit)
        return self._parse_people(results)

    # ------------------------------------------------------------------
    # Email resolution
    # ------------------------------------------------------------------

    def get_person_email(self, person_id: str, email_type: str = "professional") -> str | None:
        """GET /people/{personId}/email?type=professional|personal

        Uses a waterfall across providers. Returns the email string or
        None if unavailable. Costs 1 credit per email returned.
        """
        resp = self._client.get(
            f"/people/{person_id}/email",
            params={"type": email_type},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("email")

    def resolve_lead_email(self, lead: Lead) -> Lead:
        """Mutates ``lead.email`` by fetching from Specter if it's empty."""
        if lead.email:
            return lead

        email = self.get_person_email(lead.specter_id)
        if email:
            lead.email = email
        return lead

    # ------------------------------------------------------------------
    # Company helpers
    # ------------------------------------------------------------------

    def get_company_people(
        self,
        company_id: str,
        *,
        founders: bool = False,
        ceo: bool = False,
        department: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """GET /companies/{companyId}/people"""
        params: dict = {"limit": limit}
        if founders:
            params["founders"] = True
        if ceo:
            params["ceo"] = True
        if department:
            params["department"] = department
        resp = self._client.get(f"/companies/{company_id}/people", params=params)
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []

    def search_company(self, query: str) -> list[dict]:
        """GET /companies/search?query=..."""
        resp = self._client.get("/companies/search", params={"query": query})
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _paginate(self, path: str, *, limit: int) -> list[dict]:
        """Fetch up to ``limit`` results using Specter's page/limit pagination."""
        page_size = min(limit, 500)
        collected: list[dict] = []
        page = 0

        while len(collected) < limit:
            resp = self._client.get(path, params={"page": page, "limit": page_size})
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or len(batch) == 0:
                break
            collected.extend(batch)
            if len(batch) < page_size:
                break
            page += 1

        return collected[:limit]

    def _parse_people(self, items: list[dict]) -> list[Lead]:
        """Map Specter person objects to our Lead model.

        Person responses include person_id, first_name, last_name,
        full_name, current_position_company_name, current_position_title,
        linkedin_url, etc.  Email is NOT included — it requires a
        separate endpoint call.
        """
        leads: list[Lead] = []
        for item in items:
            person_id = item.get("person_id", "")
            if not person_id:
                continue

            leads.append(
                Lead(
                    specter_id=person_id,
                    first_name=item.get("first_name", ""),
                    last_name=item.get("last_name", ""),
                    email="",  # resolved separately via get_person_email
                    company=item.get("current_position_company_name") or "",
                    title=item.get("current_position_title") or item.get("level_of_seniority"),
                    linkedin_url=item.get("linkedin_url"),
                )
            )
        return leads

    def close(self) -> None:
        self._client.close()
