"""CLI entry-point for the cold-email skill."""

from __future__ import annotations

import argparse
import json
import logging

from cold_email_skill.clients.affinity import AffinityClient
from cold_email_skill.clients.n8n import N8NClient
from cold_email_skill.clients.specter import SpecterClient
from cold_email_skill.config import Settings
from cold_email_skill.dedup import DedupStore
from cold_email_skill.query_parser import parse_simple, parse_with_llm
from cold_email_skill.skill import ColdEmailSkill


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cold outbound email skill")
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help='Natural-language search, e.g. "Seed cybersecurity companies for RSA"',
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use Claude to parse --query (requires ANTHROPIC_API_KEY). "
        "Falls back to rule-based parsing if not set.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max leads to fetch from Specter (default: 50)",
    )
    parser.add_argument(
        "--max-credits",
        type=int,
        default=None,
        help="Stop processing if Specter credit usage would exceed this number",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Disable deduplication (allow re-drafting the same person)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check Affinity but skip creating Outlook drafts",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    logger = logging.getLogger(__name__)

    # ── Parse semantic query if provided ─────────────────────────────
    search_query = None
    outreach_context = None

    if args.query:
        if args.use_llm:
            search_query = parse_with_llm(args.query)
        else:
            search_query = parse_simple(args.query)

        outreach_context = search_query.context
        logger.info("Parsed query → %s", search_query.model_dump_json(indent=2))

    settings = Settings()
    specter = SpecterClient(
        settings.specter_api_key,
        settings.specter_base_url,
        max_credits=args.max_credits,
    )
    affinity = AffinityClient(settings.affinity_api_key, settings.affinity_base_url)
    n8n = N8NClient(settings.n8n_webhook_url)
    dedup = None if args.no_dedup else DedupStore()

    try:
        skill = ColdEmailSkill(
            specter=specter,
            affinity=affinity,
            n8n=n8n,
            sender_email=settings.sender_email,
            days_since_last_interaction=settings.days_since_last_interaction,
            dedup=dedup,
            outreach_context=outreach_context,
        )

        if args.dry_run:
            logging.info("DRY RUN – drafts will NOT be created")
            skill._n8n = _NoOpN8N()

        result = skill.run(
            limit=args.limit,
            people_list_id=settings.specter_people_list_id,
            saved_search_id=settings.specter_saved_search_id,
            search_query=search_query,
        )
        print(json.dumps(result.__dict__, indent=2))
    finally:
        specter.close()
        affinity.close()
        n8n.close()
        if dedup:
            dedup.close()


class _NoOpN8N:
    """Drop-in replacement for N8NClient that skips the webhook call."""

    def create_outlook_draft(self, draft):  # noqa: ANN001, ANN201
        logging.getLogger(__name__).info("Dry run – skipping draft for %s", draft.to_email)
        return {"success": True, "dry_run": True}


if __name__ == "__main__":
    main()
