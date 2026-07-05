"""Growth features end-to-end on real PostgreSQL: TOTP MFA, statement,
deploy hook, agency grants, signed outbound webhooks, moat auto-feeding,
theme/design-system/PDF adapters, scheduler, TSA backfill. Skips without PG."""
import http.server
import io
import json
import threading
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select, text

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from konformos.api.main import create_app  # noqa: E402
from konformos.api.security import totp_code  # noqa: E402
from konformos.db.models import KnowledgeEntryRow, Notification  # noqa: E402
from konformos.db.session import (  # noqa: E402
    make_engine,
    make_session_factory,
    set_system_context,
)
from konformos.registry.loader import load_catalog  # noqa: E402

KONFORMOS_DIR = Path(__file__).resolve().parents[1]
CORPUS_PAGES = KONFORMOS_DIR / "corpus" / "pages"

SHOP_HOME = (CORPUS_PAGES / "shop-home.html").read_text(encoding="utf-8").replace(
    "<head>",
    '<head><meta name="generator" content="WordPress 6.5">'
    '<link rel="stylesheet" href="/wp-content/themes/storefront/style.css">',
)

received_hooks: list[dict] = []


class TinyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = SHOP_HOME if self.path == "/" else None
        if self.path == "/robots.txt":
            body = "User-agent: *\n"
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        payload = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # outbound-webhook receiver
        length = int(self.headers.get("Content-Length", "0"))
        received_hooks.append({
            "path": self.path,
            "signature": self.headers.get("Konformos-Signature"),
            "body": json.loads(self.rfile.read(length) or b"{}"),
        })
        self.send_response(200)
        self.end_headers()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module", autouse=True)
def env(monkeypatch_module, tmp_path_factory):
    monkeypatch_module.setenv("KONFORMOS_ALLOW_PRIVATE_URLS", "1")
    monkeypatch_module.setenv("KONFORMOS_RATE_LIMIT_PER_MIN", "0")
    monkeypatch_module.setenv(
        "KONFORMOS_STORAGE_DIR", str(tmp_path_factory.mktemp("storage")))
    monkeypatch_module.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch_module.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="module")
def platform(env):
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
        # publish DE pack so latest-binding resolution works
        from konformos.db.models import RulePackRow
        import uuid as uuid_module
        from datetime import datetime, timezone
        pack = session.execute(select(RulePackRow).where(
            RulePackRow.version == "DE-2026.1")).scalar_one()
        pack.status = "active"
        pack.signed_by = uuid_module.uuid4()
        pack.signed_at = datetime.now(timezone.utc)
        session.commit()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TinyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = create_app(catalog, session_factory=factory)
    client = TestClient(app)
    yield {"client": client, "factory": factory, "app": app,
           "base": f"http://127.0.0.1:{server.server_address[1]}"}
    server.shutdown()
    engine.dispose()


@pytest.fixture(scope="module")
def owner(platform):
    response = platform["client"].post("/v1/auth/register", json={
        "organization_name": "Growth GmbH", "organization_type": "agency",
        "email": "owner@growth.example", "password": "growth-pass-1234"})
    assert response.status_code == 201, response.text
    headers = {"Authorization": "Bearer " + response.json()["token"]}
    # dev tier via Stripe webhook (code_inputs + webhooks)
    with platform["factory"]() as session:
        set_system_context(session)
        from konformos.db.models import Subscription
        subscription = session.execute(select(Subscription)).scalars().first()
        subscription.stripe_customer_id = "cus_growth"
        session.commit()
    platform["client"].post("/v1/billing/webhook", json={
        "id": "evt_growth_up", "type": "customer.subscription.updated",
        "data": {"object": {"customer": "cus_growth", "status": "active",
                             "metadata": {"tier": "dev"}}}})
    return headers


def _wait(platform, scan_id, headers):
    platform["app"].state.scan_futures[scan_id].result(timeout=120)
    status = platform["client"].get(f"/v1/scans/{scan_id}", headers=headers).json()
    assert status["status"] == "completed", status
    return status


def test_01_mfa_full_cycle(platform, owner):
    client = platform["client"]
    setup = client.post("/v1/auth/mfa/setup", headers=owner).json()
    secret = setup["secret"]
    verified = client.post("/v1/auth/mfa/verify", headers=owner,
                           json={"code": totp_code(secret)})
    assert verified.status_code == 200 and verified.json()["mfa_enabled"]
    # login now requires the TOTP code
    without = client.post("/v1/auth/login", json={
        "email": "owner@growth.example", "password": "growth-pass-1234"})
    assert without.status_code == 401
    assert without.json()["error"]["code"] == "mfa_required"
    with_code = client.post("/v1/auth/login", json={
        "email": "owner@growth.example", "password": "growth-pass-1234",
        "totp_code": totp_code(secret)})
    assert with_code.status_code == 200


def test_02_property_webhook_scan_and_moat(platform, owner):
    client = platform["client"]
    # consent so the moat can feed (INV-KG-02)
    client.patch("/v1/orgs/me", headers=owner, json={"data_sharing_consent": True})
    created = client.post("/v1/properties", headers=owner,
                          json={"url": platform["base"], "label": "growth shop"})
    assert created.status_code == 201, created.text
    platform["property_id"] = created.json()["id"]
    client.put(f"/v1/properties/{platform['property_id']}/compliance-profile",
               headers=owner, json={"selected_jurisdictions": ["DE"],
                                    "pack_binding": "latest",
                                    "combination_mode": "strictest"})
    fingerprint = client.post(
        f"/v1/properties/{platform['property_id']}/fingerprint", headers=owner)
    assert fingerprint.json()["theme"] == {"name": "storefront"}

    # register an outbound webhook endpoint (points at our tiny server)
    endpoint = client.post("/v1/webhook-endpoints", headers=owner,
                           json={"url": platform["base"] + "/hooks"}).json()
    assert endpoint["secret"].startswith("whsec_")

    started = client.post(f"/v1/properties/{platform['property_id']}/scans",
                          headers=owner, json={"input_type": "url"})
    assert started.status_code == 202, started.text
    _wait(platform, started.json()["scan_id"], owner)

    # outbound webhook delivered with HMAC signature
    assert any(h["body"]["type"] == "scan.completed" and
               h["signature"] and h["signature"].startswith("t=")
               for h in received_hooks)
    # notification row recorded
    notifications = client.get("/v1/notifications", headers=owner).json()
    assert any(n["type"] == "scan_done" for n in notifications["notifications"])

    # moat fed automatically (consent + theme confidence gates passed)
    with platform["factory"]() as session:
        entries = session.execute(select(KnowledgeEntryRow)).scalars().all()
        assert entries, "moat should have been fed"
        assert all(e.stack_signature == "wordpress:storefront:6" for e in entries)


def test_03_statement(platform, owner):
    statement = platform["client"].post(
        f"/v1/properties/{platform['property_id']}/statement", headers=owner)
    assert statement.status_code == 200
    text_body = statement.json()["statement"]
    assert "Erklärung zur Barrierefreiheit" in text_body
    assert "DE-2026.1" in text_body
    assert "اعتماد" in text_body  # honest: ليس اعتماداً رسمياً


def test_04_deploy_hook_flow_c(platform, owner):
    client = platform["client"]
    token = client.post(
        f"/v1/properties/{platform['property_id']}/deploy-token",
        headers=owner).json()["deploy_token"]
    hook = client.post(f"/v1/deploy/{token}")  # unauthenticated CI call
    assert hook.status_code == 202, hook.text
    scan_id = hook.json()["scan_id"]
    if hook.json()["status"] == "queued":
        _wait(platform, scan_id, owner)
    bad = client.post("/v1/deploy/dk_invalid")
    assert bad.status_code == 404


def test_05_agency_grants(platform, owner):
    client = platform["client"]
    # owner creates a member seat directly (internal assignment)
    with platform["factory"]() as session:
        set_system_context(session)
        from konformos.api.security import hash_password
        from konformos.db.models import User
        org_id = session.execute(select(User.organization_id).where(
            User.email == "owner@growth.example")).scalar_one()
        member = User(organization_id=org_id, email="seat@growth.example",
                      hashed_password=hash_password("seat-pass-123456"),
                      role="member")
        session.add(member)
        session.commit()
        member_id = str(member.id)
    member_headers = {"Authorization": "Bearer " + client.post(
        "/v1/auth/login", json={"email": "seat@growth.example",
                                "password": "seat-pass-123456"}).json()["token"]}

    # second property the member is NOT granted
    other = client.post("/v1/properties", headers=owner,
                        json={"url": platform["base"], "label": "other"}).json()
    client.post(f"/v1/properties/{platform['property_id']}/grants",
                headers=owner, json={"user_id": member_id})

    seen = client.get("/v1/properties", headers=member_headers).json()["properties"]
    assert [p["id"] for p in seen] == [platform["property_id"]]  # BR-CUST-04
    denied = client.get(f"/v1/properties/{other['id']}", headers=member_headers)
    assert denied.status_code == 404  # RBAC-03 within the org


def test_06_theme_zip_adapter(platform, owner):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("templates/product.html",
                         (CORPUS_PAGES / "product-page.html").read_text())
        archive.writestr("assets/style.css", "body{}")
    started = platform["client"].post(
        f"/v1/properties/{platform['property_id']}/scans/upload",
        headers=owner,
        data={"input_type": "theme"},
        files={"file": ("theme.zip", buffer.getvalue(), "application/zip")})
    assert started.status_code == 202, started.text
    status = _wait(platform, started.json()["scan_id"], owner)
    assert status["readiness"]["DE"]["score"] < 100
    findings = platform["client"].get(
        f"/v1/scans/{started.json()['scan_id']}/findings", headers=owner).json()
    assert any(f["location"].get("page") == "templates/product.html"
               for f in findings["findings"])


def test_07_design_system_adapter(platform, owner):
    started = platform["client"].post(
        f"/v1/properties/{platform['property_id']}/scans/design-system",
        headers=owner, json={"components": [
            {"name": "IconButton", "html": "<a href='/cart'><img src='/i.svg'></a>"},
            {"name": "CleanButton", "html": "<a href='/x'>Warenkorb</a>"},
        ]})
    assert started.status_code == 202, started.text
    scan_id = started.json()["scan_id"]
    _wait(platform, scan_id, owner)
    findings = platform["client"].get(
        f"/v1/scans/{scan_id}/findings", headers=owner).json()["findings"]
    pages = {f["location"].get("page") for f in findings}
    assert "component:IconButton" in pages       # icon link + missing alt
    assert "component:CleanButton" not in pages  # clean shell masks nothing


def test_08_pdf_adapter(platform, owner):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, "Rechnung 2026")
    raw = bytes(pdf.output())  # untagged, no Title, no Lang

    started = platform["client"].post(
        f"/v1/properties/{platform['property_id']}/scans/upload",
        headers=owner,
        data={"input_type": "pdf"},
        files={"file": ("invoice.pdf", raw, "application/pdf")})
    assert started.status_code == 202, started.text
    scan_id = started.json()["scan_id"]
    _wait(platform, scan_id, owner)
    findings = platform["client"].get(
        f"/v1/scans/{scan_id}/findings", headers=owner).json()["findings"]
    codes = {f["rule_code"] for f in findings}
    # pdf-title → 2.4.2, pdf-lang → 3.1.1, pdf-tagged → 1.3.1 (catalog-mapped)
    assert {"wcag-2.2-2.4.2", "wcag-2.2-3.1.1", "wcag-2.2-1.3.1"} <= codes


def test_09_scheduler_tick(platform, owner):
    from konformos.scan.scheduler import recover_stuck_scans, tick
    with platform["factory"]() as session:
        # force staleness: pretend last scans are old
        set_system_context(session)
        session.execute(text(
            "UPDATE scans SET created_at = created_at - interval '30 days'"))
        session.commit()
    with platform["factory"]() as session:
        enqueued = tick(session, platform["app"].state.worker)
    assert len(enqueued) >= 1  # dev tier property re-scheduled
    # join via API polling until the worker finishes
    import time
    deadline = time.time() + 120
    client = platform["client"]
    while time.time() < deadline:
        states = [client.get(f"/v1/scans/{s}", headers=owner).json()["status"]
                  for s in enqueued]
        if all(state in ("completed", "failed") for state in states):
            break
        time.sleep(1)
    assert all(state in ("completed", "failed") for state in states)
    with platform["factory"]() as session:
        assert recover_stuck_scans(session, platform["app"].state.worker) == []


def test_10_tsa_backfill(platform):
    from konformos.dossier.tsa import backfill_tsa_tokens

    class FakeTSA:
        def timestamp(self, content_hash: str):
            return f"tst-{content_hash[:8]}"

    with platform["factory"]() as session:
        set_system_context(session)
        filled = backfill_tsa_tokens(session, FakeTSA())
        session.commit()
    assert filled > 0  # timeline events from the scans above got tokens
