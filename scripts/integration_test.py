#!/usr/bin/env python3
"""Quick integration smoke-test against live Specter & Affinity APIs.

Usage:
    SPECTER_API_KEY=... AFFINITY_API_KEY=... python scripts/integration_test.py
"""

from __future__ import annotations

import os
import sys

def main() -> None:
    specter_key = os.environ.get("SPECTER_API_KEY")
    affinity_key = os.environ.get("AFFINITY_API_KEY")

    if not specter_key or not affinity_key:
        print("Set SPECTER_API_KEY and AFFINITY_API_KEY env vars first.")
        sys.exit(1)

    passed = 0
    failed = 0

    # ── Specter ──────────────────────────────────────────────────────
    from cold_email_skill.clients.specter import SpecterClient

    client = SpecterClient(specter_key)
    try:
        # 1. Company search (1 credit)
        results = client.search_company("Anthropic")
        assert isinstance(results, list), f"Expected list, got {type(results)}"
        print(f"[PASS] Specter search_company: {len(results)} result(s)")
        passed += 1

        # 2. Credit headers populated
        assert client.credit_remaining is not None, "credit_remaining not set"
        print(f"[PASS] Specter credits remaining: {client.credit_remaining}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Specter: {e}")
        failed += 1
    finally:
        client.close()

    # ── Affinity ─────────────────────────────────────────────────────
    from cold_email_skill.clients.affinity import AffinityClient

    client_a = AffinityClient(affinity_key)
    try:
        # 1. Search for a non-existent email → should return False
        result = client_a.has_recent_interaction("nobody-test-ping@example.com")
        assert result is False, f"Expected False, got {result}"
        print(f"[PASS] Affinity has_recent_interaction (unknown email): {result}")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Affinity: {e}")
        failed += 1
    finally:
        client_a.close()

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"Passed: {passed}  Failed: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
