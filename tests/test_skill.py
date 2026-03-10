"""Tests for the cold-email skill orchestrator.

Uses lightweight fakes so we don't need real API credentials.
"""

from __future__ import annotations

from cold_email_skill.models.email_draft import EmailDraft
from cold_email_skill.models.lead import Lead
from cold_email_skill.skill import ColdEmailSkill


# ------------------------------------------------------------------
# Fakes
# ------------------------------------------------------------------

def _make_lead(**overrides) -> Lead:
    defaults = dict(
        specter_id="sp-1",
        first_name="Jane",
        last_name="Doe",
        email="jane@acme.com",
        company="Acme Corp",
        title="CTO",
    )
    defaults.update(overrides)
    return Lead(**defaults)


class FakeSpecter:
    def __init__(self, leads: list[Lead]) -> None:
        self._leads = leads

    def get_leads(self, *, limit: int = 50) -> list[Lead]:
        return self._leads[:limit]


class FakeAffinity:
    def __init__(self, contacted_emails: set[str] | None = None) -> None:
        self._contacted = contacted_emails or set()

    def has_recent_interaction(self, email: str, *, days: int = 90) -> bool:
        return email in self._contacted


class FakeN8N:
    def __init__(self) -> None:
        self.drafts: list[EmailDraft] = []

    def create_outlook_draft(self, draft: EmailDraft) -> dict:
        self.drafts.append(draft)
        return {"success": True}


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_lead_with_no_interaction_gets_draft():
    lead = _make_lead()
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter([lead]),
        affinity=FakeAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert result.leads_fetched == 1
    assert result.drafts_created == 1
    assert result.already_contacted == 0
    assert len(n8n.drafts) == 1
    assert n8n.drafts[0].to_email == "jane@acme.com"


def test_lead_with_recent_interaction_is_skipped():
    lead = _make_lead()
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter([lead]),
        affinity=FakeAffinity(contacted_emails={"jane@acme.com"}),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert result.leads_fetched == 1
    assert result.drafts_created == 0
    assert result.already_contacted == 1
    assert len(n8n.drafts) == 0


def test_multiple_leads_mixed():
    leads = [
        _make_lead(specter_id="1", email="a@x.com", first_name="A"),
        _make_lead(specter_id="2", email="b@x.com", first_name="B"),
        _make_lead(specter_id="3", email="c@x.com", first_name="C"),
    ]
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter(leads),
        affinity=FakeAffinity(contacted_emails={"b@x.com"}),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert result.leads_fetched == 3
    assert result.already_contacted == 1
    assert result.drafts_created == 2


def test_error_on_one_lead_does_not_stop_others():
    """If Affinity blows up for one lead the others still get processed."""

    class ExplodingAffinity:
        def __init__(self) -> None:
            self._calls = 0

        def has_recent_interaction(self, email: str, *, days: int = 90) -> bool:
            self._calls += 1
            if self._calls == 1:
                raise RuntimeError("boom")
            return False

    leads = [
        _make_lead(specter_id="1", email="a@x.com"),
        _make_lead(specter_id="2", email="b@x.com"),
    ]
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter(leads),
        affinity=ExplodingAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert len(result.errors) == 1
    assert result.drafts_created == 1


def test_email_draft_model():
    draft = EmailDraft(
        to_email="a@b.com",
        to_name="A B",
        subject="Hello",
        body_html="<p>Hi</p>",
        sender_email="me@co.com",
    )
    payload = draft.model_dump()
    assert payload["to_email"] == "a@b.com"
    assert payload["cc"] == []
    assert payload["bcc"] == []
