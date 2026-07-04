"""End-to-end: the real seed catalog loads through the typed models, and the
API serves packs + evaluates readiness against it (AC-P0 slices)."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from konformos.api.main import create_app
from konformos.registry.loader import load_catalog


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def client(catalog):
    return TestClient(create_app(catalog))


def test_seed_catalog_loads_and_matches_wcag22_counts(catalog):
    a = sum(1 for r in catalog.rules.values() if r.wcag_level == "A")
    aa = sum(1 for r in catalog.rules.values() if r.wcag_level == "AA")
    assert (a, aa) == (31, 24)
    assert "wcag-2.2-4.1.1" not in catalog.rules  # removed in WCAG 2.2
    assert {p.version for p in catalog.packs} == {"DE-2026.1", "EU-2026.1", "US-2026.1"}
    assert all(p.status == "draft" for p in catalog.packs)  # P3: unsigned seed stays draft
    assert set(catalog.mappings) == set(catalog.rules)


def test_health_and_pack_listing(client):
    health = client.get("/health").json()
    assert health["rules"] == 55
    packs = client.get("/v1/catalog/rule-packs", params={"jurisdiction": "DE"}).json()
    assert [p["version"] for p in packs["rule_packs"]] == ["DE-2026.1"]
    assert packs["rule_packs"][0]["rule_count"] == 49


def test_evaluate_endpoint_full_flow(client, catalog):
    # seed packs are draft; pin to them explicitly (resolve-by-latest needs active)
    body = {
        "profile": {
            "property_id": "p1",
            "selected_jurisdictions": ["DE"],
            "pack_binding": "pinned",
            "pinned_versions": {"DE": "DE-2026.1"},
            "combination_mode": "strictest",
        },
        "findings": [
            {"rule_code": "wcag-2.2-1.4.3", "severity": "critical", "status": "open", "page": "/"},
            {"rule_code": "wcag-2.2-2.4.2", "severity": "serious", "status": "open", "page": "/"},
        ],
        "pages_scanned": 5,
        "on_date": str(date(2026, 7, 1)),
    }
    response = client.post("/v1/evaluate", json=body)
    assert response.status_code == 200
    readiness = response.json()["readiness"]["DE"]
    assert 0 <= readiness["score"] < 100
    assert readiness["computed_against_pack"] == "DE-2026.1"  # INV-RD-01
    assert readiness["rules_manual_pending"] > 0  # BR-EVAL-04 disclosure
    assert readiness["gaps"][0]["rule_code"] == "wcag-2.2-1.4.3"


def test_evaluate_pack_not_effective_error_envelope(client):
    body = {
        "profile": {
            "property_id": "p1",
            "selected_jurisdictions": ["US"],
            "pack_binding": "pinned",
            "pinned_versions": {"US": "US-2026.1"},
            "combination_mode": "strictest",
        },
        "findings": [],
        "pages_scanned": 1,
        "on_date": "2025-01-01",  # before US pack's effective_from
    }
    response = client.post("/v1/evaluate", json=body)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "pack_not_effective"  # ERR-00 envelope
    assert error["request_id"].startswith("req_")
