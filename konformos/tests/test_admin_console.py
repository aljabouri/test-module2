"""Admin control plane isolation (ISO-01..04) + client management (CM) over
real PostgreSQL. Skips without PG.

The isolation contract under test:
- app-surface tokens NEVER open /v1/admin/* (401 admin_token_required)
- admin-surface tokens NEVER work on customer routes (403 wrong_surface)
- elevation requires an admin role AND a fresh TOTP (step-up)
- the admin_ro RLS bypass is SELECT-only at the database layer
- impersonation tokens are hard-wired read-only
- every admin mutation lands in a hash-chained, append-only audit log
"""
import uuid as uuid_module
from pathlib import Path

import pytest
from sqlalchemy import text

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from konformos.api.main import create_app  # noqa: E402
from konformos.api.security import (  # noqa: E402
    generate_totp_secret,
    hash_password,
    totp_code,
)
from konformos.db.models import Organization, User  # noqa: E402
from konformos.db.session import (  # noqa: E402
    make_engine,
    make_session_factory,
    set_admin_context,
    set_system_context,
)
from konformos.registry.loader import load_catalog  # noqa: E402

KONFORMOS_DIR = Path(__file__).resolve().parents[1]

ADMIN_EMAIL = "root@konformos.internal"
ADMIN_PASS = "admin-pass-123456"
ADMIN_SECRET = generate_totp_secret()


@pytest.fixture(scope="module")
def platform(tmp_path_factory):
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
        # internal admin with real TOTP enrollment (RBAC-02)
        set_system_context(session)
        org = Organization(type="merchant", name="KonformOS HQ")
        session.add(org)
        session.flush()
        session.add(User(organization_id=org.id, email=ADMIN_EMAIL,
                         hashed_password=hash_password(ADMIN_PASS),
                         role="admin", mfa_enabled=True,
                         mfa_secret=ADMIN_SECRET))
        session.commit()

    app = create_app(catalog, session_factory=factory)
    client = TestClient(app)
    yield {"client": client, "factory": factory}
    engine.dispose()


@pytest.fixture(scope="module")
def merchant(platform):
    response = platform["client"].post("/v1/auth/register", json={
        "organization_name": "Client Shop GmbH",
        "email": "owner@client-shop.example", "password": "merchant-pass-123",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {"headers": {"Authorization": "Bearer " + body["token"]},
            "organization_id": body["organization_id"]}


@pytest.fixture(scope="module")
def admin_app_headers(platform):
    """The admin's ordinary APP-surface token (step 1 of the step-up)."""
    response = platform["client"].post("/v1/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASS,
        "totp_code": totp_code(ADMIN_SECRET)})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture(scope="module")
def admin_headers(platform, admin_app_headers):
    """The elevated ADMIN-surface token (step 2: fresh TOTP)."""
    response = platform["client"].post(
        "/v1/admin/auth/elevate", headers=admin_app_headers,
        json={"totp_code": totp_code(ADMIN_SECRET)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["surface"] == "admin" and body["expires_in_seconds"] == 900
    return {"Authorization": "Bearer " + body["token"]}


# ── ISO-01: disjoint surfaces ────────────────────────────────────────────
def test_01_owner_cannot_elevate(platform, merchant):
    response = platform["client"].post(
        "/v1/admin/auth/elevate", headers=merchant["headers"],
        json={"totp_code": "000000"})
    assert response.status_code == 403


def test_02_wrong_totp_rejected(platform, admin_app_headers):
    response = platform["client"].post(
        "/v1/admin/auth/elevate", headers=admin_app_headers,
        json={"totp_code": "000000"})
    assert response.status_code == 401


def test_03_app_token_rejected_on_admin_namespace(platform, admin_app_headers):
    response = platform["client"].get("/v1/admin/overview",
                                      headers=admin_app_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "admin_token_required"


def test_04_admin_token_rejected_on_customer_surface(platform, admin_headers):
    response = platform["client"].get("/v1/properties", headers=admin_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_surface"


# ── ISO-02: cross-org READ works, writes stay blocked at the DB ──────────
def test_05_overview_and_client_list(platform, admin_headers, merchant):
    overview = platform["client"].get("/v1/admin/overview",
                                      headers=admin_headers).json()
    assert overview["organizations"] >= 2  # HQ + merchant
    assert "lifecycle_breakdown" in overview and "avg_health" in overview

    clients = platform["client"].get("/v1/admin/clients",
                                     headers=admin_headers).json()["clients"]
    match = [c for c in clients
             if c["organization_id"] == merchant["organization_id"]]
    assert match, "merchant org must be visible cross-org to the admin"
    client = match[0]
    assert client["lifecycle"] == "onboarding"  # fresh org, no scans yet
    assert 0 <= client["health"] <= 100
    assert client["tier"] == "free_scan"


def test_06_admin_ro_bypass_is_select_only(platform, merchant):
    from konformos.db.models import Property
    with platform["factory"]() as session:
        set_admin_context(session)
        rows = session.execute(text("SELECT count(*) FROM properties")).scalar()
        assert rows is not None  # SELECT allowed
        session.add(Property(
            organization_id=uuid_module.UUID(merchant["organization_id"]),
            url="https://forged-by-admin.example"))
        with pytest.raises(Exception):  # WITH CHECK: no admin write path
            session.flush()


# ── CM: client 360, notes, lifecycle, tier ───────────────────────────────
def test_07_client_360(platform, admin_headers, merchant):
    r = platform["client"].get(
        f"/v1/admin/clients/{merchant['organization_id']}",
        headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert {"health_breakdown", "playbook", "members", "properties",
            "notes", "recent_scans"} <= set(body)
    assert body["members"][0]["email"] == "owner@client-shop.example"
    components = body["health_breakdown"]
    assert sum(c["max"] for c in components.values()) == 100


def test_08_notes_append_only(platform, admin_headers, merchant):
    org_id = merchant["organization_id"]
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/notes", headers=admin_headers,
        json={"kind": "call", "body": "مكالمة تعريفية — العميل مهتم بمستوى report"})
    assert r.status_code == 201
    note_id = r.json()["id"]
    body = platform["client"].get(f"/v1/admin/clients/{org_id}",
                                  headers=admin_headers).json()
    assert any(n["id"] == note_id and n["kind"] == "call" for n in body["notes"])
    with platform["factory"]() as session:  # trigger: append-only
        with pytest.raises(Exception):
            session.execute(text(
                "UPDATE client_notes SET body = 'tampered' WHERE id = :id"),
                {"id": note_id})
            session.commit()


def test_09_lifecycle_pinned(platform, admin_headers, merchant):
    org_id = merchant["organization_id"]
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/lifecycle", headers=admin_headers,
        json={"state": "at_risk", "pinned": True, "tags": ["vip"]})
    assert r.status_code == 200 and r.json()["pinned"] is True
    listed = platform["client"].get(
        "/v1/admin/clients?segment=at_risk", headers=admin_headers).json()
    assert any(c["organization_id"] == org_id and c["lifecycle_pinned"]
               for c in listed["clients"])


def test_10_tier_change_applies_and_audits(platform, admin_headers, merchant):
    org_id = merchant["organization_id"]
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/tier", headers=admin_headers,
        json={"tier": "report", "reason": "ترقية تجريبية شهرية"})
    assert r.status_code == 200
    assert r.json() == {"tier": "report", "previous": "free_scan"}
    # the CUSTOMER sees the new tier through their own surface
    me = platform["client"].get("/v1/orgs/me",
                                headers=merchant["headers"]).json()
    assert me["subscription"]["tier"] == "report"
    audit = platform["client"].get("/v1/admin/audit",
                                   headers=admin_headers).json()["entries"]
    assert any(e["action"] == "client.tier_changed"
               and e["data"]["to"] == "report" for e in audit)
    bad = platform["client"].post(
        f"/v1/admin/clients/{org_id}/tier", headers=admin_headers,
        json={"tier": "imaginary", "reason": "x"})
    assert bad.status_code == 422


# ── kill-switch + impersonation ──────────────────────────────────────────
def test_11_suspend_blocks_customer_surface(platform, admin_headers, merchant):
    org_id = merchant["organization_id"]
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/suspend", headers=admin_headers,
        json={"reason": "اشتباه إساءة استخدام"})
    assert r.status_code == 200
    blocked = platform["client"].get("/v1/properties",
                                     headers=merchant["headers"])
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "org_suspended"
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/reactivate", headers=admin_headers)
    assert r.status_code == 200
    assert platform["client"].get(
        "/v1/properties", headers=merchant["headers"]).status_code == 200


def test_12_impersonation_is_read_only(platform, admin_headers, merchant):
    org_id = merchant["organization_id"]
    r = platform["client"].post(
        f"/v1/admin/clients/{org_id}/impersonate", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["read_only"] is True
    imp = {"Authorization": "Bearer " + body["token"]}
    seen = platform["client"].get("/v1/properties", headers=imp)
    assert seen.status_code == 200  # reads work, scoped to the client org
    write = platform["client"].post("/v1/properties", headers=imp, json={
        "url": "https://sneaky-write.example"})
    assert write.status_code == 403
    assert write.json()["error"]["code"] == "impersonation_read_only"
    # …and the impersonation itself is on the audit chain
    audit = platform["client"].get("/v1/admin/audit",
                                   headers=admin_headers).json()["entries"]
    assert any(e["action"] == "client.impersonated" for e in audit)


# ── ISO-03: hash-chained audit — verification + tamper detection ────────
def test_13_audit_chain_valid_then_forgery_detected(platform, admin_headers):
    ok = platform["client"].get("/v1/admin/audit/verify",
                                headers=admin_headers).json()
    assert ok["valid"] is True and ok["entries"] >= 4

    with platform["factory"]() as session:  # UPDATE/DELETE blocked by trigger
        with pytest.raises(Exception):
            session.execute(text(
                "UPDATE admin_audit_log SET action = 'nothing_happened'"
                " WHERE sequence_number = 1"))
            session.commit()

    with platform["factory"]() as session:  # a forged INSERT breaks the chain
        session.execute(text(
            "INSERT INTO admin_audit_log (id, sequence_number, actor_user_id,"
            " action, payload, content_hash, prev_hash)"
            " VALUES (:id, 999, :actor, 'forged.entry', '{}'::jsonb,"
            " 'deadbeef', 'not-the-real-prev-hash')"),
            {"id": str(uuid_module.uuid4()),
             "actor": str(uuid_module.uuid4())})
        session.commit()
    broken = platform["client"].get("/v1/admin/audit/verify",
                                    headers=admin_headers).json()
    assert broken["valid"] is False and broken["broken_at"] == 999


def test_14_system_panel(platform, admin_headers):
    r = platform["client"].get("/v1/admin/system", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["db"] is True
    assert body["admin_token_ttl_seconds"] == 900
    assert body["catalog"]["rules"] == 55
