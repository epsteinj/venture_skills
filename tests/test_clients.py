"""HTTP-level tests for API clients using respx.

These verify that each client sends requests to the correct endpoints
with correct auth, params, and headers — without hitting real APIs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from cold_email_skill.clients.affinity import AffinityClient
from cold_email_skill.clients.n8n import N8NClient
from cold_email_skill.clients.specter import CreditBudgetExceeded, SpecterClient
from cold_email_skill.models.email_draft import EmailDraft


# =====================================================================
# Affinity
# =====================================================================


class TestAffinityClient:
    """Verify Affinity v1 /persons endpoint usage."""

    BASE = "https://api.affinity.co"

    def _recent_iso(self, days_ago: int = 10) -> str:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        return dt.isoformat()

    def _old_iso(self, days_ago: int = 200) -> str:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        return dt.isoformat()

    @respx.mock
    def test_persons_search_sends_correct_request(self):
        route = respx.get(
            f"{self.BASE}/persons",
            params={"term": "jane@acme.com", "with_interaction_dates": "true"},
        ).respond(json={"persons": [], "next_page_token": None})

        client = AffinityClient("test-key", self.BASE)
        result = client.has_recent_interaction("jane@acme.com")

        assert route.called
        assert result is False

        # Verify Basic auth: empty user, key as password
        req = route.calls[0].request
        assert req.headers["authorization"].startswith("Basic ")

    @respx.mock
    def test_recent_interaction_returns_true(self):
        respx.get(f"{self.BASE}/persons").respond(json={
            "persons": [{
                "id": 123,
                "first_name": "Jane",
                "last_name": "Doe",
                "primary_email": "jane@acme.com",
                "interaction_dates": {
                    "last_email_date": self._recent_iso(10),
                },
            }],
            "next_page_token": None,
        })

        client = AffinityClient("test-key", self.BASE)
        assert client.has_recent_interaction("jane@acme.com", days=90) is True

    @respx.mock
    def test_old_interaction_returns_false(self):
        respx.get(f"{self.BASE}/persons").respond(json={
            "persons": [{
                "id": 123,
                "interaction_dates": {
                    "last_email_date": self._old_iso(200),
                },
            }],
            "next_page_token": None,
        })

        client = AffinityClient("test-key", self.BASE)
        assert client.has_recent_interaction("jane@acme.com", days=90) is False

    @respx.mock
    def test_no_person_found_returns_false(self):
        respx.get(f"{self.BASE}/persons").respond(json={
            "persons": [],
            "next_page_token": None,
        })

        client = AffinityClient("test-key", self.BASE)
        assert client.has_recent_interaction("nobody@x.com") is False

    @respx.mock
    def test_empty_interaction_dates_returns_false(self):
        respx.get(f"{self.BASE}/persons").respond(json={
            "persons": [{"id": 1, "interaction_dates": {}}],
            "next_page_token": None,
        })

        client = AffinityClient("test-key", self.BASE)
        assert client.has_recent_interaction("jane@acme.com") is False

    @respx.mock
    def test_multiple_date_fields_checked(self):
        """Even if last_email_date is old, a recent last_event_date counts."""
        respx.get(f"{self.BASE}/persons").respond(json={
            "persons": [{
                "id": 1,
                "interaction_dates": {
                    "last_email_date": self._old_iso(200),
                    "last_event_date": self._recent_iso(5),
                },
            }],
            "next_page_token": None,
        })

        client = AffinityClient("test-key", self.BASE)
        assert client.has_recent_interaction("jane@acme.com", days=90) is True


# =====================================================================
# Specter
# =====================================================================


class TestSpecterClient:
    """Verify Specter endpoint URLs, auth header, and credit tracking."""

    BASE = "https://app.tryspecter.com/api/v1"

    @respx.mock
    def test_people_list_sends_correct_request(self):
        route = respx.get(
            f"{self.BASE}/lists/people/list_abc/results",
        ).respond(json=[
            {"person_id": "p1", "first_name": "A", "last_name": "B",
             "current_position_company_name": "Co", "current_position_title": "CEO"},
        ])

        client = SpecterClient("sk-test", self.BASE)
        leads = client.get_people_list_results("list_abc", limit=10)

        assert route.called
        req = route.calls[0].request
        assert req.headers["X-API-Key"] == "sk-test"
        assert len(leads) == 1
        assert leads[0].specter_id == "p1"

    @respx.mock
    def test_saved_search_sends_correct_request(self):
        route = respx.get(
            f"{self.BASE}/searches/people/search_xyz/results",
        ).respond(json=[
            {"person_id": "p2", "first_name": "C", "last_name": "D",
             "current_position_company_name": "Inc"},
        ])

        client = SpecterClient("sk-test", self.BASE)
        leads = client.get_saved_search_results("search_xyz", limit=5)

        assert route.called
        assert len(leads) == 1

    @respx.mock
    def test_get_person_email_endpoint(self):
        route = respx.get(
            f"{self.BASE}/people/p1/email",
            params={"type": "professional"},
        ).respond(json={"email": "a@b.com"})

        client = SpecterClient("sk-test", self.BASE)
        email = client.get_person_email("p1")

        assert route.called
        assert email == "a@b.com"

    @respx.mock
    def test_get_person_email_404_returns_none(self):
        respx.get(f"{self.BASE}/people/p1/email").respond(status_code=404)

        client = SpecterClient("sk-test", self.BASE)
        assert client.get_person_email("p1") is None

    @respx.mock
    def test_credit_headers_tracked(self):
        respx.get(f"{self.BASE}/people/p1/email").respond(
            json={"email": "a@b.com"},
            headers={
                "X-CreditLimit-Limit": "10000",
                "X-CreditLimit-Remaining": "9500",
            },
        )

        client = SpecterClient("sk-test", self.BASE)
        client.get_person_email("p1")

        assert client.credits_used == 1
        assert client.credit_remaining == 9500

    @respx.mock
    def test_max_credits_prevents_call(self):
        client = SpecterClient("sk-test", self.BASE, max_credits=0)

        with pytest.raises(CreditBudgetExceeded):
            client.get_person_email("p1")

    @respx.mock
    def test_pagination_fetches_multiple_pages(self):
        page0 = [{"person_id": f"p{i}", "first_name": "X", "last_name": "Y",
                   "current_position_company_name": "Co"} for i in range(500)]
        page1 = [{"person_id": "p500", "first_name": "Z", "last_name": "W",
                   "current_position_company_name": "Co"}]

        respx.get(f"{self.BASE}/lists/people/lid/results", params__contains={"page": "0"}).respond(json=page0)
        respx.get(f"{self.BASE}/lists/people/lid/results", params__contains={"page": "1"}).respond(json=page1)

        client = SpecterClient("sk-test", self.BASE)
        leads = client.get_people_list_results("lid", limit=501)

        assert len(leads) == 501
        assert client.credits_used == 501

    @respx.mock
    def test_search_company_endpoint(self):
        route = respx.get(
            f"{self.BASE}/companies/search",
            params={"query": "Acme"},
        ).respond(json=[{"company_id": "c1", "name": "Acme"}])

        client = SpecterClient("sk-test", self.BASE)
        results = client.search_company("Acme")

        assert route.called
        assert len(results) == 1


# =====================================================================
# N8N
# =====================================================================


class TestN8NClient:
    """Verify N8N webhook sends correct POST with draft payload."""

    WEBHOOK = "https://n8n.example.com/webhook/draft"

    @respx.mock
    def test_create_draft_posts_correct_payload(self):
        route = respx.post(self.WEBHOOK).respond(json={"success": True})

        client = N8NClient(self.WEBHOOK)
        draft = EmailDraft(
            to_email="jane@acme.com",
            to_name="Jane Doe",
            subject="Hello",
            body_html="<p>Hi</p>",
            sender_email="me@co.com",
        )
        result = client.create_outlook_draft(draft)

        assert route.called
        assert result == {"success": True}

        # Verify the JSON body matches the draft
        import json
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["to_email"] == "jane@acme.com"
        assert sent_body["subject"] == "Hello"
        assert sent_body["sender_email"] == "me@co.com"

    @respx.mock
    def test_create_draft_raises_on_server_error(self):
        respx.post(self.WEBHOOK).respond(status_code=500)

        client = N8NClient(self.WEBHOOK)
        draft = EmailDraft(
            to_email="a@b.com", to_name="A", subject="S",
            body_html="<p>x</p>", sender_email="me@co.com",
        )
        with pytest.raises(httpx.HTTPStatusError):
            client.create_outlook_draft(draft)
