"""Structured representation of a natural-language lead search.

A calling LLM (e.g. Claude) parses user intent like:
  "Find Seed and Series A cybersecurity companies to meet at RSA"
into a SearchQuery that the skill can execute against the Specter API.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Parsed search intent ready for execution against Specter."""

    # Free-text search terms to use with /companies/search
    # e.g. ["cybersecurity", "cloud security", "endpoint security"]
    company_queries: list[str] = Field(
        description="Keywords or phrases to search for companies. "
        "Generate multiple related terms to cast a wider net.",
    )

    # Role filters for /companies/{id}/people
    founders: bool = Field(
        default=True,
        description="Include company founders in results.",
    )
    ceo: bool = Field(
        default=False,
        description="Include CEOs in results.",
    )
    department: str | None = Field(
        default=None,
        description="Filter people by department (e.g. 'Engineering', 'Sales').",
    )

    # Client-side filters applied after fetching company details
    funding_stages: list[str] = Field(
        default_factory=list,
        description="Desired funding stages, e.g. ['Seed', 'Series A']. "
        "Empty means no stage filter.",
    )

    # Context for email personalization
    context: str | None = Field(
        default=None,
        description="Event or reason for outreach, used in email drafts. "
        "e.g. 'RSA Conference 2026'",
    )

    max_companies: int = Field(
        default=20,
        description="Max number of companies to process.",
    )
