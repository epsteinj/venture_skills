"""Specter API client – fetches leads.

This is a stub implementation.  Once you have the Specter API docs, update
the endpoint paths, query parameters, and response‑parsing logic below.
"""

from __future__ import annotations

import httpx

from cold_email_skill.models.lead import Lead


class SpecterClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )

    # ------------------------------------------------------------------
    # TODO: replace the endpoint / params once Specter docs are available
    # ------------------------------------------------------------------

    def get_leads(self, *, limit: int = 50) -> list[Lead]:
        """Fetch the latest leads from Specter.

        Adjust the endpoint, query params, and response mapping once the
        real API schema is known.
        """
        resp = self._client.get("/leads", params={"limit": limit})
        resp.raise_for_status()
        data = resp.json()

        # Map raw Specter response into our Lead model.
        # Update field names to match the actual API response.
        return [
            Lead(
                specter_id=item["id"],
                first_name=item["first_name"],
                last_name=item["last_name"],
                email=item["email"],
                company=item["company"],
                title=item.get("title"),
                linkedin_url=item.get("linkedin_url"),
            )
            for item in data.get("results", [])
        ]

    def close(self) -> None:
        self._client.close()
