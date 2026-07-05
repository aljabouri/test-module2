"""End-to-end vertical slice over the real corpus + real seed catalog:
HTML → scan → normalize → readiness → sealed dossier → PUBLIC verification.
Plus the proactive Theme Intelligence preview."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from konformos.api.main import create_app
from konformos.moat.knowledge import KnowledgeEntry, KnowledgeStore
from konformos.registry.loader import load_catalog

CORPUS_PAGES = Path(__file__).resolve().parents[1] / "corpus" / "pages"

PROFILE = {
    "property_id": "p1",
    "selected_jurisdictions": ["DE"],
    "pack_binding": "pinned",
    "pinned_versions": {"DE": "DE-2026.1"},
    "combination_mode": "strictest",
}


@pytest.fixture(scope="module")
def client():
    store = KnowledgeStore()
    store.contribute(
        KnowledgeEntry(
            stack_signature="shopware:vision:3",
            rule_code="wcag-2.2-1.1.1",
            pattern={"where": "product gallery"},
            known_fix={"type": "code_patch", "hint": "alt from product title"},
            occurrence_count=37,
            fix_success_rate=0.92,
            validated_by_expert=True,
        ),
        data_sharing_consent=True,
    )
    return TestClient(create_app(load_catalog(), knowledge_store=store))


def corpus_body():
    return {
        "profile": PROFILE,
        "pages": [
            {"path": name, "html": (CORPUS_PAGES / name).read_text(encoding="utf-8")}
            for name in ("shop-home.html", "product-page.html", "clean-page.html")
        ],
        "on_date": "2026-07-01",
    }


def test_scan_html_slice(client):
    response = client.post("/v1/scan-html", json=corpus_body())
    assert response.status_code == 200
    data = response.json()
    assert data["engine_versions"] == {"internal": "internal-0.1"}  # INV-SC-02
    assert len(data["findings"]) == 13  # corpus ground truth
    assert data["unmapped_issues"] == []
    readiness = data["readiness"]["DE"]
    assert 0 <= readiness["score"] < 100
    assert readiness["computed_against_pack"] == "DE-2026.1"


def test_dossier_then_public_verify_roundtrip(client):
    created = client.post("/v1/dossiers", json=corpus_body()).json()
    dossier_hash = created["dossier_hash"]
    assert created["verify_url"] == f"/v1/verify/{dossier_hash}"

    verified = client.get(f"/v1/verify/{dossier_hash}").json()
    assert verified["valid"] is True
    content = verified["content"]
    assert content["pack_versions"] == {"DE": "DE-2026.1"}
    assert content["timeline"]["chain_valid"] is True
    # public by construction: no identity in the public record
    for key in ("organization", "property", "url", "label"):
        assert key not in content

    page = client.get(f"/v1/verify/{dossier_hash}/page")
    assert page.status_code == 200
    assert "الختم سليم" in page.text
    # INV-DS-03 on the public page too
    assert "certif" not in page.text.lower()


def test_verify_unknown_hash_404(client):
    response = client.get("/v1/verify/" + "0" * 64)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_preview_known_theme(client):
    response = client.post("/v1/preview", json={
        "platform": "Shopware", "theme_name": "Vision",
        "theme_version": "3.4.1", "theme_confidence": 0.93,
    })
    data = response.json()
    assert data["stack_signature"] == "shopware:vision:3"
    assert data["known_issue_count"] == 1
    issue = data["known_issues"][0]
    assert issue["seen_in_stores"] == 37 and issue["fix_available"] is True


def test_preview_low_confidence_hedged(client):
    # BR-FP-01: no pre-scan claims below the confidence threshold
    data = client.post("/v1/preview", json={
        "platform": "Shopware", "theme_name": "Vision",
        "theme_version": "3.4.1", "theme_confidence": 0.4,
    }).json()
    assert data["known_issue_count"] == 0
    assert "غير كافية" in data["statement"]
