"""Tests for the cold-email skill orchestrator.

Uses lightweight fakes so we don't need real API credentials.
"""

from __future__ import annotations

import tempfile
import os

from cold_email_skill.dedup import DedupStore
from cold_email_skill.models.email_draft import EmailDraft
from cold_email_skill.models.lead import Lead
from cold_email_skill.skill import ColdEmailSkill


# ------------------------------------------------------------------
# Fakes
# ------------------------------------------------------------------

def _make_lead(**overrides) -> Lead:
    defaults = dict(
        specter_id="per_001",
        first_name="Jane",
        last_name="Doe",
        email="jane@acme.com",
        company="Acme Corp",
        title="CTO",
    )
    defaults.update(overrides)
    return Lead(**defaults)


class FakeSpecter:
    def __init__(self, leads: list[Lead], *, emails: dict[str, str] | None = None) -> None:
        self._leads = leads
        self._emails = emails or {}
        self._credits_used = 0

    @property
    def credits_used(self) -> int:
        return self._credits_used

    def get_leads(self, *, limit: int = 50) -> list[Lead]:
        self._credits_used += len(self._leads[:limit])
        return self._leads[:limit]

    def resolve_lead_email(self, lead: Lead) -> Lead:
        self._credits_used += 1
        if lead.specter_id in self._emails:
            lead.email = self._emails[lead.specter_id]
        return lead


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


def _temp_dedup() -> DedupStore:
    """Create a DedupStore backed by a temp file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return DedupStore(db_path=path)


# ------------------------------------------------------------------
# Core pipeline tests
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


def test_lead_without_email_resolved_from_specter():
    lead = _make_lead(specter_id="per_99", email="")
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter([lead], emails={"per_99": "resolved@acme.com"}),
        affinity=FakeAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert result.emails_resolved == 1
    assert result.drafts_created == 1
    assert n8n.drafts[0].to_email == "resolved@acme.com"


def test_lead_without_email_and_no_resolution_skipped():
    lead = _make_lead(specter_id="per_00", email="")
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter([lead]),
        affinity=FakeAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()

    assert result.no_email == 1
    assert result.drafts_created == 0


def test_error_on_one_lead_does_not_stop_others():
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


# ------------------------------------------------------------------
# Dedup tests
# ------------------------------------------------------------------

def test_dedup_prevents_redrafting():
    """Second run should skip leads already drafted in the first run."""
    dedup = _temp_dedup()
    try:
        lead = _make_lead()
        n8n = FakeN8N()

        # First run
        skill = ColdEmailSkill(
            specter=FakeSpecter([lead]),
            affinity=FakeAffinity(),
            n8n=n8n,
            sender_email="me@co.com",
            dedup=dedup,
        )
        r1 = skill.run()
        assert r1.drafts_created == 1

        # Second run with same lead
        n8n2 = FakeN8N()
        skill2 = ColdEmailSkill(
            specter=FakeSpecter([lead]),
            affinity=FakeAffinity(),
            n8n=n8n2,
            sender_email="me@co.com",
            dedup=dedup,
        )
        r2 = skill2.run()
        assert r2.drafts_created == 0
        assert r2.already_drafted == 1
        assert len(n8n2.drafts) == 0
    finally:
        dedup.close()


def test_dedup_store_count_and_clear():
    dedup = _temp_dedup()
    try:
        assert dedup.count() == 0
        dedup.record_draft("a@x.com", "per_1")
        dedup.record_draft("b@x.com", "per_2")
        assert dedup.count() == 2
        assert dedup.already_drafted("a@x.com")
        assert not dedup.already_drafted("c@x.com")
        dedup.clear()
        assert dedup.count() == 0
    finally:
        dedup.close()


def test_no_dedup_allows_redrafting():
    """Without dedup store, same lead gets drafted again."""
    lead = _make_lead()
    n8n = FakeN8N()

    skill = ColdEmailSkill(
        specter=FakeSpecter([lead]),
        affinity=FakeAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
        dedup=None,
    )
    r1 = skill.run()
    assert r1.drafts_created == 1

    n8n2 = FakeN8N()
    skill2 = ColdEmailSkill(
        specter=FakeSpecter([lead]),
        affinity=FakeAffinity(),
        n8n=n8n2,
        sender_email="me@co.com",
        dedup=None,
    )
    r2 = skill2.run()
    assert r2.drafts_created == 1  # no dedup, so it drafts again


# ------------------------------------------------------------------
# Credit tracking tests
# ------------------------------------------------------------------

def test_credits_used_tracked_in_result():
    leads = [
        _make_lead(specter_id="1", email="a@x.com"),
        _make_lead(specter_id="2", email="b@x.com"),
    ]
    n8n = FakeN8N()
    skill = ColdEmailSkill(
        specter=FakeSpecter(leads),
        affinity=FakeAffinity(),
        n8n=n8n,
        sender_email="me@co.com",
    )
    result = skill.run()
    assert result.credits_used > 0
