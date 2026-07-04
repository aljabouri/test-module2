"""Persistence layer against REAL PostgreSQL: migrations, hardening triggers,
RLS isolation, chain integrity in the DB, idempotent Rules-as-Data seeding.
Skipped automatically when no PostgreSQL is reachable."""
import uuid
from datetime import date

import pytest
from sqlalchemy import inspect, text

sqlalchemy = pytest.importorskip("sqlalchemy")
alembic = pytest.importorskip("alembic")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from pathlib import Path  # noqa: E402

from konformos.core.hashing import ChainBroken  # noqa: E402
from konformos.db.models import (  # noqa: E402
    KnowledgeEntryRow,
    Organization,
    Property,
    RulePackRow,
    TimelineEventRow,
)
from konformos.db.repository import (  # noqa: E402
    TimelineRepository,
    get_active_pack_db,
    seed_from_catalog,
)
from konformos.db.session import make_engine, make_session_factory, set_org_context  # noqa: E402
from konformos.registry.loader import load_catalog  # noqa: E402

KONFORMOS_DIR = Path(__file__).resolve().parents[1]


def _engine_or_skip():
    try:
        engine = make_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        pytest.skip("PostgreSQL not reachable")


@pytest.fixture(scope="module")
def engine():
    engine = _engine_or_skip()
    cfg = Config()
    cfg.set_main_option("script_location", str(KONFORMOS_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url.render_as_string(hide_password=False)))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine):
    factory = make_session_factory(engine)
    with factory() as session:
        yield session
        session.rollback()


@pytest.fixture()
def org_property(session):
    org = Organization(type="merchant", name="Test GmbH")
    session.add(org)
    session.flush()
    set_org_context(session, org.id)
    prop = Property(organization_id=org.id, url="https://example-shop.test", label="shop")
    session.add(prop)
    session.flush()
    return org, prop


def test_migrations_applied(engine):
    tables = set(inspect(engine).get_table_names())
    expected = {
        "organizations", "users", "subscriptions", "properties",
        "stack_fingerprints", "compliance_profiles", "legal_sources",
        "legal_change_events", "rules", "rule_packs", "rule_mappings",
        "scans", "findings", "fixes", "readiness_results",
        "knowledge_entries", "timeline_events", "dossiers", "expert_reviews",
    }
    assert expected <= tables


def test_knowledge_entries_has_no_identity_columns(engine):
    """INV-KG-01 enforced by the schema itself."""
    columns = {c["name"] for c in inspect(engine).get_columns("knowledge_entries")}
    for forbidden in ("organization_id", "property_id", "url", "domain", "email"):
        assert forbidden not in columns
    fks = inspect(engine).get_foreign_keys("knowledge_entries")
    assert all(fk["referred_table"] == "rules" for fk in fks)


def test_seed_catalog_idempotent(session):
    catalog = load_catalog()
    first = seed_from_catalog(session, catalog)
    assert first.rules_inserted == 55 and first.packs_inserted == 3
    second = seed_from_catalog(session, catalog)
    assert second.rules_inserted == 0 and second.packs_inserted == 0
    assert second.packs_skipped == 3  # INV-RP-01: never silently re-written


def test_timeline_chain_in_db(session, org_property):
    _, prop = org_property
    TimelineRepository.append(session, prop.id, "scan_completed", {"scan": "s1"})
    TimelineRepository.append(session, prop.id, "fix_applied", {"fix": "f1"})
    e3 = TimelineRepository.append(session, prop.id, "readiness_changed", {"to": 78})
    assert e3.sequence_number == 3
    assert TimelineRepository.verify_property_chain(session, prop.id) == 3


def test_db_trigger_blocks_update_and_delete(engine, session, org_property):
    """INV-TL-01 at the DB layer — even raw SQL cannot rewrite history."""
    _, prop = org_property
    TimelineRepository.append(session, prop.id, "scan_completed", {"scan": "s1"})
    session.commit()
    set_org_context(session, prop.organization_id)

    with pytest.raises(Exception, match="INV-TL-01"):
        session.execute(text(
            "UPDATE timeline_events SET payload = '{}'::jsonb WHERE property_id = :p"
        ), {"p": str(prop.id)})
    session.rollback()
    set_org_context(session, prop.organization_id)

    with pytest.raises(Exception, match="INV-TL-01"):
        session.execute(text(
            "DELETE FROM timeline_events WHERE property_id = :p"
        ), {"p": str(prop.id)})
    session.rollback()

    # tampering detection end-to-end: disable nothing, verify chain over rows
    set_org_context(session, prop.organization_id)
    assert TimelineRepository.verify_property_chain(session, prop.id) >= 1


def test_chain_broken_detected_from_db_rows(session, org_property):
    _, prop = org_property
    TimelineRepository.append(session, prop.id, "scan_completed", {"scan": "s1"})
    # forge a row that skips the chain (INSERT is allowed — append-only)
    session.add(TimelineEventRow(
        property_id=prop.id, sequence_number=2, event_type="fix_applied",
        payload={"fix": "FORGED"}, content_hash="deadbeef", prev_hash="deadbeef",
    ))
    session.flush()
    with pytest.raises(ChainBroken):
        TimelineRepository.verify_property_chain(session, prop.id)


def test_one_active_pack_per_jurisdiction(session):
    """INV-RP-02 partial unique index."""
    from sqlalchemy.exc import IntegrityError

    session.add(RulePackRow(
        jurisdiction="DE", version="DE-2030.1", effective_from=date(2030, 1, 1),
        status="active", legal_basis="t", rule_refs=[],
    ))
    session.flush()
    session.add(RulePackRow(
        jurisdiction="DE", version="DE-2030.2", effective_from=date(2030, 2, 1),
        status="active", legal_basis="t", rule_refs=[],
    ))
    with pytest.raises(IntegrityError):
        session.flush()


def test_get_active_pack_respects_effective_date(session):
    session.add_all([
        RulePackRow(jurisdiction="EU", version="EU-2031.1",
                    effective_from=date(2031, 1, 1), status="active",
                    legal_basis="t", rule_refs=[]),
        RulePackRow(jurisdiction="EU", version="EU-2031.2",
                    effective_from=date(2031, 6, 1), status="superseded",
                    legal_basis="t", rule_refs=[]),
    ])
    session.flush()
    pack = get_active_pack_db(session, "EU", date(2031, 3, 1))
    assert pack is not None and pack.version == "EU-2031.1"
    assert get_active_pack_db(session, "EU", date(2030, 1, 1)) is None  # BR-LEG-04


def test_rls_isolates_organizations(session):
    """INV-ORG-01: an org context only sees its own properties."""
    org_a = Organization(type="merchant", name="A GmbH")
    org_b = Organization(type="merchant", name="B GmbH")
    session.add_all([org_a, org_b])
    session.flush()

    set_org_context(session, org_a.id)
    session.add(Property(organization_id=org_a.id, url="https://a.test"))
    session.flush()
    set_org_context(session, org_b.id)
    session.add(Property(organization_id=org_b.id, url="https://b.test"))
    session.flush()

    from sqlalchemy import select
    set_org_context(session, org_a.id)
    visible = session.execute(select(Property.url)).scalars().all()
    assert visible == ["https://a.test"]

    set_org_context(session, None)  # no context → zero rows, not all rows
    assert session.execute(select(Property.url)).scalars().all() == []


def test_rls_blocks_cross_org_insert(session):
    org_a = Organization(type="merchant", name="A2 GmbH")
    org_b = Organization(type="merchant", name="B2 GmbH")
    session.add_all([org_a, org_b])
    session.flush()
    set_org_context(session, org_a.id)
    session.add(Property(organization_id=org_b.id, url="https://forged.test"))
    with pytest.raises(Exception):  # WITH CHECK violation
        session.flush()


def test_sequence_gap_impossible_via_repository(session, org_property):
    """INV-TL-04: unique(property_id, sequence_number) + repo locking."""
    from sqlalchemy.exc import IntegrityError

    _, prop = org_property
    row = TimelineRepository.append(session, prop.id, "scan_completed", {"n": 1})
    session.add(TimelineEventRow(
        property_id=prop.id, sequence_number=row.sequence_number,  # duplicate
        event_type="x", payload={}, content_hash="x", prev_hash="x",
    ))
    with pytest.raises(IntegrityError):
        session.flush()
