"""Parse natural-language lead queries into structured SearchQuery objects.

Two strategies:
  1. parse_with_llm()  – uses Claude to extract intent (recommended)
  2. parse_simple()    – rule-based fallback (no API dependency)
"""

from __future__ import annotations

import json
import logging
import re

from cold_email_skill.models.search_query import SearchQuery

logger = logging.getLogger(__name__)

# ── Industry keyword map ─────────────────────────────────────────────
# Maps broad terms to more specific search queries for better Specter results.
_INDUSTRY_EXPANSIONS: dict[str, list[str]] = {
    "cybersecurity": ["cybersecurity", "cloud security", "endpoint security", "identity security", "application security"],
    "cyber": ["cybersecurity", "cloud security", "endpoint security"],
    "ai": ["artificial intelligence", "machine learning", "generative AI", "AI infrastructure"],
    "fintech": ["fintech", "payments", "neobank", "lending platform"],
    "healthtech": ["healthtech", "digital health", "health AI", "clinical software"],
    "devtools": ["developer tools", "devops", "developer platform", "code infrastructure"],
    "climate": ["climate tech", "clean energy", "carbon", "sustainability software"],
    "saas": ["SaaS", "enterprise software", "cloud software"],
    "biotech": ["biotech", "therapeutics", "drug discovery", "life sciences"],
    "edtech": ["edtech", "education technology", "learning platform"],
    "proptech": ["proptech", "real estate technology", "property management software"],
    "insurtech": ["insurtech", "insurance technology", "insurance platform"],
    "defense": ["defense tech", "defense", "national security", "dual-use"],
}

# Conference → industry context
_CONFERENCE_CONTEXT: dict[str, dict] = {
    "rsa": {"industries": ["cybersecurity"], "context": "RSA Conference"},
    "black hat": {"industries": ["cybersecurity"], "context": "Black Hat"},
    "defcon": {"industries": ["cybersecurity"], "context": "DEF CON"},
    "ces": {"industries": ["consumer electronics", "IoT"], "context": "CES"},
    "sxsw": {"industries": ["media tech", "entertainment tech"], "context": "SXSW"},
    "money2020": {"industries": ["fintech"], "context": "Money20/20"},
    "money20/20": {"industries": ["fintech"], "context": "Money20/20"},
    "money 20/20": {"industries": ["fintech"], "context": "Money20/20"},
    "himss": {"industries": ["healthtech"], "context": "HIMSS"},
    "collision": {"industries": ["technology startups"], "context": "Collision"},
    "web summit": {"industries": ["technology startups"], "context": "Web Summit"},
    "techcrunch disrupt": {"industries": ["technology startups"], "context": "TechCrunch Disrupt"},
    "jp morgan": {"industries": ["biotech", "healthtech"], "context": "JP Morgan Healthcare Conference"},
    "re:invent": {"industries": ["cloud", "devtools", "AI infrastructure"], "context": "AWS re:Invent"},
    "google next": {"industries": ["cloud", "AI"], "context": "Google Cloud Next"},
    "build": {"industries": ["devtools", "AI"], "context": "Microsoft Build"},
}

# Funding stage aliases
_STAGE_ALIASES: dict[str, str] = {
    "pre-seed": "Pre-Seed",
    "preseed": "Pre-Seed",
    "seed": "Seed",
    "series a": "Series A",
    "series b": "Series B",
    "series c": "Series C",
    "series d": "Series D",
    "growth": "Growth",
    "late stage": "Late Stage",
    "late-stage": "Late Stage",
    "early stage": "Early Stage",
    "early-stage": "Early Stage",
}


def parse_simple(text: str) -> SearchQuery:
    """Rule-based parser: extracts industries, stages, roles, and context
    from a natural-language query without needing an LLM.
    """
    lower = text.lower()

    # ── Detect conference context ────────────────────────────────────
    context = None
    inferred_industries: list[str] = []

    for trigger, info in _CONFERENCE_CONTEXT.items():
        if trigger in lower:
            context = info["context"]
            inferred_industries.extend(info["industries"])
            break

    # ── Extract funding stages ───────────────────────────────────────
    stages: list[str] = []
    for alias, canonical in _STAGE_ALIASES.items():
        if alias in lower and canonical not in stages:
            stages.append(canonical)

    # ── Extract industries ───────────────────────────────────────────
    mentioned_industries: list[str] = []
    for keyword in _INDUSTRY_EXPANSIONS:
        if keyword in lower:
            mentioned_industries.append(keyword)

    all_industries = list(dict.fromkeys(inferred_industries + mentioned_industries))

    # ── Build search queries ─────────────────────────────────────────
    company_queries: list[str] = []
    for ind in all_industries:
        if ind in _INDUSTRY_EXPANSIONS:
            company_queries.extend(_INDUSTRY_EXPANSIONS[ind])
        else:
            company_queries.append(ind)

    # Deduplicate while preserving order
    company_queries = list(dict.fromkeys(company_queries))

    # If no industries detected, use the raw text as the search query
    if not company_queries:
        # Strip common filler words and use what's left
        cleaned = re.sub(
            r"\b(find|search|look for|get|me|relevant|companies|startups|to meet|at|in|a couple of weeks?|going to)\b",
            "",
            lower,
        ).strip()
        if cleaned:
            company_queries = [cleaned]

    # ── Role detection ───────────────────────────────────────────────
    founders = True  # default for VC outreach
    ceo = False
    department = None

    if "ceo" in lower or "chief executive" in lower:
        ceo = True
    if "cto" in lower or "engineering" in lower:
        department = "Engineering"
    if "sales" in lower or "revenue" in lower:
        department = "Sales"
        founders = False

    return SearchQuery(
        company_queries=company_queries,
        founders=founders,
        ceo=ceo,
        department=department,
        funding_stages=stages,
        context=context,
    )


def parse_with_llm(text: str, *, api_key: str | None = None) -> SearchQuery:
    """Use Claude to parse the query into a SearchQuery.

    Requires the ``anthropic`` package and an API key (via param or
    ANTHROPIC_API_KEY env var).
    """
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed, falling back to simple parser")
        return parse_simple(text)

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    schema = SearchQuery.model_json_schema()

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Parse this venture capital lead search query into structured parameters.\n\n"
                    f"Query: \"{text}\"\n\n"
                    "Return a JSON object matching this schema:\n"
                    f"{json.dumps(schema, indent=2)}\n\n"
                    "Guidelines:\n"
                    "- Generate multiple related company_queries to cast a wide net "
                    "(e.g. for 'cybersecurity' also include 'cloud security', 'endpoint security', etc.)\n"
                    "- Detect conferences/events and set context (e.g. 'RSA' → 'RSA Conference')\n"
                    "- Map funding stages to canonical names: Pre-Seed, Seed, Series A, Series B, etc.\n"
                    "- Default founders=true for VC outreach\n"
                    "- Return ONLY the JSON object, no other text."
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)
    return SearchQuery(**parsed)
