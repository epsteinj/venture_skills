"""CLI entry-point for the cold-email skill."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from cold_email_skill.clients.affinity import AffinityClient
from cold_email_skill.clients.n8n import N8NClient
from cold_email_skill.clients.specter import SpecterClient
from cold_email_skill.config import Settings
from cold_email_skill.skill import ColdEmailSkill


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Cold outbound email skill")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max leads to fetch from Specter (default: 50)",
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

    settings = Settings()
    specter = SpecterClient(settings.specter_api_key, settings.specter_base_url)
    affinity = AffinityClient(settings.affinity_api_key, settings.affinity_base_url)
    n8n = N8NClient(settings.n8n_webhook_url)

    try:
        skill = ColdEmailSkill(
            specter=specter,
            affinity=affinity,
            n8n=n8n,
            sender_email=settings.sender_email,
            days_since_last_interaction=settings.days_since_last_interaction,
        )

        if args.dry_run:
            logging.info("DRY RUN – drafts will NOT be created")
            # In dry-run mode we still fetch leads and check Affinity,
            # but swap in a no-op N8N client.
            skill._n8n = _NoOpN8N()

        result = skill.run(
            limit=args.limit,
            people_list_id=settings.specter_people_list_id,
            saved_search_id=settings.specter_saved_search_id,
        )
        print(json.dumps(result.__dict__, indent=2))
    finally:
        specter.close()
        affinity.close()
        n8n.close()


class _NoOpN8N:
    """Drop-in replacement for N8NClient that skips the webhook call."""

    def create_outlook_draft(self, draft):  # noqa: ANN001, ANN201
        logging.getLogger(__name__).info("Dry run – skipping draft for %s", draft.to_email)
        return {"success": True, "dry_run": True}


if __name__ == "__main__":
    main()
