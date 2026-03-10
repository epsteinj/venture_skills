"""Tests for the natural-language query parser."""

from __future__ import annotations

from cold_email_skill.query_parser import parse_simple
from cold_email_skill.models.search_query import SearchQuery


class TestParseSimple:
    def test_rsa_cybersecurity(self):
        q = parse_simple(
            "I'm going to RSA in a couple of weeks. "
            "Find relevant Seed and Series A cybersecurity companies to meet."
        )
        assert isinstance(q, SearchQuery)
        assert q.context == "RSA Conference"
        assert "Seed" in q.funding_stages
        assert "Series A" in q.funding_stages
        assert any("cybersecurity" in term.lower() for term in q.company_queries)
        assert q.founders is True

    def test_fintech_seed(self):
        q = parse_simple("Find seed stage fintech startups")
        assert "Seed" in q.funding_stages
        assert any("fintech" in t.lower() for t in q.company_queries)

    def test_conference_implies_industry(self):
        q = parse_simple("I'm attending Money20/20 next month")
        assert q.context == "Money20/20"
        assert any("fintech" in t.lower() for t in q.company_queries)

    def test_ai_series_b(self):
        q = parse_simple("Series B AI companies")
        assert "Series B" in q.funding_stages
        assert any("artificial intelligence" in t.lower() or "ai" in t.lower() for t in q.company_queries)

    def test_ceo_filter(self):
        q = parse_simple("Find CEOs at cybersecurity companies")
        assert q.ceo is True

    def test_department_filter(self):
        q = parse_simple("Find sales leaders at SaaS companies")
        assert q.department == "Sales"
        assert q.founders is False

    def test_unknown_industry_uses_raw_text(self):
        q = parse_simple("Find quantum computing companies")
        assert len(q.company_queries) > 0

    def test_multiple_stages(self):
        q = parse_simple("Pre-seed and seed stage biotech startups")
        assert "Pre-Seed" in q.funding_stages
        assert "Seed" in q.funding_stages

    def test_black_hat_conference(self):
        q = parse_simple("Going to Black Hat, need to find Series A security startups")
        assert q.context == "Black Hat"
        assert "Series A" in q.funding_stages

    def test_defense_industry(self):
        q = parse_simple("Find early stage defense tech companies")
        assert "Early Stage" in q.funding_stages
        assert any("defense" in t.lower() for t in q.company_queries)


class TestSearchQueryModel:
    def test_defaults(self):
        q = SearchQuery(company_queries=["test"])
        assert q.founders is True
        assert q.ceo is False
        assert q.department is None
        assert q.funding_stages == []
        assert q.context is None
        assert q.max_companies == 20

    def test_serialization(self):
        q = SearchQuery(
            company_queries=["cybersecurity", "cloud security"],
            funding_stages=["Seed"],
            context="RSA Conference",
        )
        data = q.model_dump()
        assert data["company_queries"] == ["cybersecurity", "cloud security"]
        assert data["funding_stages"] == ["Seed"]
        assert data["context"] == "RSA Conference"
