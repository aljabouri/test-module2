"""Full-platform end-to-end over real PostgreSQL + real Chromium + a local
shop server: auth → curator publishes pack → merchant adds property →
fingerprint → async scan (202+poll) → findings → dossier PDF → public verify
→ legal update recompute → expert review → Stripe webhook. Skips without PG."""
import http.server
import json
import threading
import uuid as uuid_module
from functools import partial
from pathlib import Path

import pytest
from sqlalchemy import text

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from konformos.api.main import create_app  # noqa: E402
from konformos.api.security import hash_password  # noqa: E402
from konformos.db.models import User  # noqa: E402
from konformos.db.session import make_engine, make_session_factory, set_system_context  # noqa: E402
from konformos.registry.loader import load_catalog  # noqa: E402

KONFORMOS_DIR = Path(__file__).resolve().parents[1]
CORPUS_PAGES = KONFORMOS_DIR / "corpus" / "pages"

SHOP_HOME = (CORPUS_PAGES / "shop-home.html").read_text(encoding="utf-8").replace(
    "<head>",
    '<head><meta name="generator" content="WordPress 6.5">'
    '<link rel="stylesheet" href="/wp-content/themes/storefront/style.css">',
)


class ShopHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        routes = {
            "/": SHOP_HOME,
            "/robots.txt": "User-agent: *\nDisallow: /private\n",
        }
        body = routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        payload = body.encode("utf-8")
        self.send_response(200)
        content_type = "text/plain" if self.path.endswith(".txt") else "text/html"
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture(scope="module")
def shop_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ShopHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def platform(shop_server, tmp_path_factory):
    try:
        engine = make_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not reachable")

    cfg = Config()
    cfg.set_main_option("script_location", str(KONFORMOS_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    factory = make_session_factory(engine)
    catalog = load_catalog()
    with factory() as session:
        from konformos.db.repository import seed_from_catalog
        seed_from_catalog(session, catalog)
        session.commit()

    app = create_app(catalog, session_factory=factory)
    client = TestClient(app)
    yield {"client": client, "factory": factory, "app": app, "shop": shop_server}
    engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def env(monkeypatch_module, tmp_path_factory):
    monkeypatch_module.setenv("KONFORMOS_ALLOW_PRIVATE_URLS", "1")
    monkeypatch_module.setenv(
        "KONFORMOS_STORAGE_DIR", str(tmp_path_factory.mktemp("dossiers")))
    monkeypatch_module.delenv("STRIPE_WEBHOOK_SECRET", raising=False)


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


def make_internal_user(platform, role):
    """VAL-USER-01: elevated roles are internal assignments, not self-service."""
    with platform["factory"]() as session:
        set_system_context(session)
        from konformos.db.models import Organization
        org = Organization(type="merchant", name=f"KonformOS internal {role}")
        session.add(org)
        session.flush()
        user = User(organization_id=org.id, email=f"{role}@konformos.internal",
                    hashed_password=hash_password("internal-pass-123"),
                    role=role, mfa_enabled=True)  # RBAC-02
        session.add(user)
        session.commit()
    response = platform["client"].post("/v1/auth/login", json={
        "email": f"{role}@konformos.internal", "password": "internal-pass-123"})
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture(scope="module")
def merchant(platform):
    response = platform["client"].post("/v1/auth/register", json={
        "organization_name": "Demo Shop GmbH",
        "email": "owner@demo-shop.example", "password": "merchant-pass-123",
    })
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture(scope="module")
def curator(platform):
    return make_internal_user(platform, "legal_curator")


@pytest.fixture(scope="module")
def expert(platform):
    return make_internal_user(platform, "expert_reviewer")


# ── the story, in order ──────────────────────────────────────────────────
def test_01_unauthenticated_rejected(platform):
    response = platform["client"].get("/v1/properties")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_required"


def test_02_curator_publishes_seed_pack(platform, curator, merchant):
    client = platform["client"]
    # merchant may NOT publish (RBAC §5)
    denied = client.post("/v1/legal/rule-packs/DE-2026.1/publish", headers=merchant)
    assert denied.status_code == 403
    published = client.post("/v1/legal/rule-packs/DE-2026.1/publish", headers=curator)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "active"  # INV-RP-03 signed inside


def test_03_property_fingerprint(platform, merchant):
    client, shop = platform["client"], platform["shop"]
    created = client.post("/v1/properties", headers=merchant,
                          json={"url": shop, "label": "متجر التجربة"})
    assert created.status_code == 201, created.text
    platform["property_id"] = created.json()["id"]

    fingerprint = client.post(
        f"/v1/properties/{platform['property_id']}/fingerprint", headers=merchant)
    assert fingerprint.status_code == 200, fingerprint.text
    data = fingerprint.json()
    assert data["platform"] == "wordpress"
    assert data["theme"] == {"name": "storefront"}
    assert data["drift"] is False

    # Flow A step 3: choose the compliance profile explicitly
    profile = client.put(
        f"/v1/properties/{platform['property_id']}/compliance-profile",
        headers=merchant,
        json={"selected_jurisdictions": ["DE"], "pack_binding": "latest",
              "combination_mode": "strictest"})
    assert profile.status_code == 200, profile.text


def test_04_async_scan_completes(platform, merchant):
    client = platform["client"]
    started = client.post(f"/v1/properties/{platform['property_id']}/scans",
                          headers=merchant, json={"input_type": "url"})
    assert started.status_code == 202, started.text
    scan_id = started.json()["scan_id"]

    # duplicate while queued/running → 409 (EDGE-SCAN-01)
    duplicate = client.post(f"/v1/properties/{platform['property_id']}/scans",
                            headers=merchant, json={"input_type": "url"})
    assert duplicate.status_code in (409, 403)

    platform["app"].state.scan_futures[scan_id].result(timeout=120)  # join worker
    status = client.get(f"/v1/scans/{scan_id}", headers=merchant).json()
    assert status["status"] == "completed", status
    assert "internal" in status["engine_versions"]  # INV-SC-02
    assert status["readiness"]["DE"]["computed_against_pack"] == "DE-2026.1"
    assert 0 <= status["readiness"]["DE"]["score"] < 100
    platform["scan_id"] = scan_id

    findings = client.get(f"/v1/scans/{scan_id}/findings", headers=merchant).json()
    assert len(findings["findings"]) >= 5  # corpus shop-home defects
    platform["finding_id"] = findings["findings"][0]["id"]


def test_05_free_tier_daily_limit(platform, merchant):
    again = platform["client"].post(
        f"/v1/properties/{platform['property_id']}/scans",
        headers=merchant, json={"input_type": "url"})
    assert again.status_code == 403
    assert again.json()["error"]["code"] == "tier_insufficient"  # BR-BIL


def test_06_finding_state_machine(platform, merchant):
    client = platform["client"]
    no_reason = client.patch(f"/v1/findings/{platform['finding_id']}",
                             headers=merchant, json={"status": "wont_fix"})
    assert no_reason.status_code == 422  # SM-FND: reason mandatory
    ok = client.patch(f"/v1/findings/{platform['finding_id']}", headers=merchant,
                      json={"status": "wont_fix", "reason": "قرار تجاري مؤقت"})
    assert ok.status_code == 200
    bad = client.patch(f"/v1/findings/{platform['finding_id']}", headers=merchant,
                       json={"status": "fixed"})
    assert bad.status_code == 409  # wont_fix → fixed not allowed
    assert bad.json()["error"]["code"] == "invalid_state_transition"


def test_07_fix_endpoint_labeled(platform, merchant):
    fix = platform["client"].get(
        f"/v1/findings/{platform['finding_id']}/fix", headers=merchant).json()
    assert fix["source"] in ("manual_guidance", "knowledge_graph")
    assert "مراجعة" in fix["notice"]  # BR-FIX-02


def test_08_dossier_gated_then_generated(platform, merchant):
    client = platform["client"]
    gated = client.post(f"/v1/properties/{platform['property_id']}/dossier",
                        headers=merchant)
    assert gated.status_code == 403  # free tier: no dossier
    # upgrade via Stripe webhook (BR-BIL-03: Stripe is source of truth)
    with platform["factory"]() as session:
        set_system_context(session)
        from sqlalchemy import select
        from konformos.db.models import Subscription
        subscription = session.execute(select(Subscription)).scalars().all()[0]
        subscription.stripe_customer_id = "cus_demo1"
        session.commit()
    webhook = client.post("/v1/billing/webhook", json={
        "id": "evt_upgrade_1", "type": "customer.subscription.updated",
        "data": {"object": {"customer": "cus_demo1", "status": "active",
                             "metadata": {"tier": "monitoring"}}},
    })
    assert webhook.status_code == 200 and webhook.json()["applied"] == "monitoring/active"

    created = client.post(f"/v1/properties/{platform['property_id']}/dossier",
                          headers=merchant)
    assert created.status_code == 201, created.text
    data = created.json()
    platform["dossier_hash"] = data["dossier_hash"]
    pdf = client.get(data["pdf"], headers=merchant)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_09_public_verify_db_dossier(platform):
    client = platform["client"]
    verified = client.get(f"/v1/verify/{platform['dossier_hash']}").json()
    assert verified["valid"] is True
    content = verified["content"]
    assert content["pack_versions"]["DE"] == "DE-2026.1"
    for key in ("organization", "property", "url", "label"):
        assert key not in content  # public by construction
    page = client.get(f"/v1/verify/{platform['dossier_hash']}/page")
    assert page.status_code == 200 and "الختم سليم" in page.text


def test_10_webhook_idempotent(platform):
    duplicate = platform["client"].post("/v1/billing/webhook", json={
        "id": "evt_upgrade_1", "type": "customer.subscription.updated",
        "data": {"object": {"customer": "cus_demo1", "status": "active",
                             "metadata": {"tier": "free_scan"}}},
    })
    assert duplicate.json()["duplicate"] is True  # EDGE-BIL-02: not re-applied


def test_11_legal_change_flow_and_recompute(platform, curator, merchant):
    client = platform["client"]
    source = client.post("/v1/legal/sources", headers=curator, json={
        "jurisdiction": "DE", "name": "EN 301 549 (ETSI)",
        "url": "https://www.etsi.org/...", "source_type": "standard"}).json()
    event = client.post("/v1/legal/change-events", headers=curator, json={
        "source_id": source["id"], "change_type": "version_bump",
        "llm_summary": "EN 301 549 updated to WCAG 2.2 — 6 new criteria"}).json()

    catalog = json.loads(
        (KONFORMOS_DIR / "docs-link" ).read_text()) if False else None  # noqa
    de_pack = json.loads((KONFORMOS_DIR.parent / "docs" / "rules-catalog" /
                          "seed" / "rule-packs" / "DE-2026.1.json").read_text(encoding="utf-8"))
    new_pack = {**de_pack, "version": "DE-2026.2", "effective_from": "2026-06-28",
                "seed": False, "notes": "WCAG 2.2 upgrade"}
    new_pack["rule_refs"] = de_pack["rule_refs"] + [
        {"rule_code": "wcag-2.2-2.4.11", "weight": 6, "mandatory": True},
        {"rule_code": "wcag-2.2-2.5.7", "weight": 6, "mandatory": True},
        {"rule_code": "wcag-2.2-2.5.8", "weight": 6, "mandatory": True},
        {"rule_code": "wcag-2.2-3.2.6", "weight": 6, "mandatory": True},
        {"rule_code": "wcag-2.2-3.3.7", "weight": 6, "mandatory": True},
        {"rule_code": "wcag-2.2-3.3.8", "weight": 6, "mandatory": True},
    ]
    for key in ("seed_provenance", "signed_by", "signed_at"):
        new_pack.pop(key, None)

    approved = client.post(f"/v1/legal/change-events/{event['id']}/approve",
                           headers=curator, json={"pack": new_pack})
    assert approved.status_code == 200, approved.text

    published = client.post("/v1/legal/rule-packs/DE-2026.2/publish", headers=curator)
    assert published.status_code == 200, published.text
    data = published.json()
    assert data["superseded"] == "DE-2026.1"  # INV-RP-02 atomic swap
    assert data["recomputed_properties"] >= 1  # BR-LEG-05

    # the merchant's timeline shows legal_update_applied (Flow B step 7)
    timeline = client.get(f"/v1/properties/{platform['property_id']}/timeline",
                          headers=merchant).json()
    kinds = [e["event_type"] for e in timeline["events"]]
    assert "scan_completed" in kinds and "legal_update_applied" in kinds
    # property readiness now computed against the NEW pack version
    prop = client.get(f"/v1/properties/{platform['property_id']}", headers=merchant).json()
    assert prop["readiness_current"]["DE"] is not None


def test_12_expert_review_and_sign(platform, expert, merchant):
    client = platform["client"]
    queue = client.get("/v1/expert/review-queue", headers=expert).json()
    assert any(item["scan_id"] == platform["scan_id"] for item in queue["queue"])

    added = client.post(f"/v1/expert/scans/{platform['scan_id']}/manual-findings",
                        headers=expert, json=[{
                            "rule_code": "wcag-2.2-2.4.7", "severity": "serious",
                            "location": {"selector": "nav a", "page": "/"},
                            "evidence": {"note": "focus indicator suppressed by CSS"}}])
    assert added.status_code == 201 and added.json()["added"] == 1

    signed = client.post(f"/v1/expert/scans/{platform['scan_id']}/sign",
                         headers=expert, json={
                             "signature": {"qualification": "BITV-Test Prüfer"},
                             "insurance_ref": "VS-2026-001"})
    assert signed.status_code == 200 and signed.json()["status"] == "signed"

    again = client.post(f"/v1/expert/scans/{platform['scan_id']}/sign",
                        headers=expert, json={"signature": {}})
    assert again.status_code == 409  # SM-ER: signed is final

    timeline = client.get(f"/v1/properties/{platform['property_id']}/timeline",
                          headers=merchant).json()
    assert "expert_review_signed" in [e["event_type"] for e in timeline["events"]]


def test_13_rls_second_org_sees_nothing(platform):
    client = platform["client"]
    other = client.post("/v1/auth/register", json={
        "organization_name": "Other GmbH", "email": "other@example.test",
        "password": "other-pass-1234"}).json()
    headers = {"Authorization": "Bearer " + other["token"]}
    assert client.get("/v1/properties", headers=headers).json()["properties"] == []
    stolen = client.get(f"/v1/scans/{platform['scan_id']}", headers=headers)
    assert stolen.status_code == 404  # RBAC-03: no existence leak


def test_14_dashboard_served(platform):
    page = platform["client"].get("/app")
    assert page.status_code == 200
    assert "KonformOS" in page.text and "لوحة التحكم" in page.text
