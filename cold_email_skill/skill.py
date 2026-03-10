"""Cold outbound email skill.

Pipeline:
  1. Pull leads from a Specter people list or saved search
  2. Resolve each lead's email via Specter (separate API call)
  3. Check Affinity for recent interactions with that email
  4. If no recent interaction → create an Outlook email draft via N8N webhook
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from cold_email_skill.clients.affinity import AffinityClient
from cold_email_skill.clients.n8n import N8NClient
from cold_email_skill.clients.specter import SpecterClient
from cold_email_skill.models.email_draft import EmailDraft
from cold_email_skill.models.lead import Lead

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    leads_fetched: int = 0
    emails_resolved: int = 0
    no_email: int = 0
    already_contacted: int = 0
    drafts_created: int = 0
    errors: list[str] = field(default_factory=list)


class ColdEmailSkill:
    def __init__(
        self,
        specter: SpecterClient,
        affinity: AffinityClient,
        n8n: N8NClient,
        *,
        sender_email: str,
        days_since_last_interaction: int = 90,
    ) -> None:
        self._specter = specter
        self._affinity = affinity
        self._n8n = n8n
        self._sender_email = sender_email
        self._days = days_since_last_interaction

    def run(
        self,
        *,
        limit: int = 50,
        people_list_id: str | None = None,
        saved_search_id: str | None = None,
    ) -> SkillResult:
        """Execute the full cold-email pipeline and return a summary.

        Provide *one* of ``people_list_id`` or ``saved_search_id`` to
        tell the skill which Specter lead source to pull from.
        """
        result = SkillResult()

        leads = self._fetch_leads(
            limit=limit,
            people_list_id=people_list_id,
            saved_search_id=saved_search_id,
        )
        result.leads_fetched = len(leads)
        logger.info("Fetched %d leads from Specter", len(leads))

        for lead in leads:
            try:
                self._process_lead(lead, result)
            except Exception as exc:
                identifier = lead.email or lead.specter_id
                msg = f"Error processing {identifier}: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        logger.info(
            "Done – %d fetched, %d emails resolved, %d no email, "
            "%d already contacted, %d drafts created, %d errors",
            result.leads_fetched,
            result.emails_resolved,
            result.no_email,
            result.already_contacted,
            result.drafts_created,
            len(result.errors),
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_leads(
        self,
        *,
        limit: int,
        people_list_id: str | None,
        saved_search_id: str | None,
    ) -> list[Lead]:
        if people_list_id:
            return self._specter.get_people_list_results(people_list_id, limit=limit)
        if saved_search_id:
            return self._specter.get_saved_search_results(saved_search_id, limit=limit)
        # Fallback: try the generic get_leads (works with test fakes)
        return self._specter.get_leads(limit=limit)

    def _process_lead(self, lead: Lead, result: SkillResult) -> None:
        # Step 1: resolve email if missing (Specter people lists don't include it)
        if not lead.email:
            self._specter.resolve_lead_email(lead)

        if not lead.email:
            logger.info("Skipping %s (%s) – no email found", lead.full_name, lead.specter_id)
            result.no_email += 1
            return

        result.emails_resolved += 1

        # Step 2: check Affinity
        if self._affinity.has_recent_interaction(lead.email, days=self._days):
            logger.info("Skipping %s – recent Affinity interaction", lead.email)
            result.already_contacted += 1
            return

        # Step 3: create Outlook draft via N8N
        draft = self._build_draft(lead)
        self._n8n.create_outlook_draft(draft)
        logger.info("Draft created for %s", lead.email)
        result.drafts_created += 1

    def _build_draft(self, lead: Lead) -> EmailDraft:
        subject = f"Quick intro – {lead.company}"
        body_html = (
            f"<p>Hi {lead.first_name},</p>"
            f"<p>I came across {lead.company} and wanted to reach out. "
            f"Would love to find a few minutes to connect.</p>"
            f"<p>Best,<br/>The Team</p>"
        )
        return EmailDraft(
            to_email=lead.email,
            to_name=lead.full_name,
            subject=subject,
            body_html=body_html,
            sender_email=self._sender_email,
        )
