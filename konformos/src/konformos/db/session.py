"""Engine/session factory. PostgreSQL-first: JSONB, ARRAY and RLS require it."""
from __future__ import annotations

import os
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg2://konformos:konformos_dev@127.0.0.1:5432/konformos"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None):
    return create_engine(url or database_url(), future=True)


def make_session_factory(engine=None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or make_engine(), future=True, expire_on_commit=False)


def set_org_context(session: Session, organization_id: uuid.UUID | None) -> None:
    """INV-ORG-01: every customer-facing unit of work runs inside an org
    context; RLS hides all rows when it is unset."""
    session.execute(
        text("SELECT set_config('app.current_org', :val, false)"),
        {"val": str(organization_id) if organization_id else ""},
    )
    session.execute(text("SELECT set_config('app.rls_bypass', '', false)"))


def set_system_context(session: Session) -> None:
    """Named narrow bypass for system flows with no org yet (login lookup,
    Stripe webhook). Applies ONLY to users/subscriptions — properties has no
    bypass by design (migration 0003)."""
    session.execute(text("SELECT set_config('app.current_org', '', false)"))
    session.execute(text("SELECT set_config('app.rls_bypass', 'system', false)"))


def rls_enforceable(bind) -> bool | None:
    """INV-ORG-01 guard: RLS NEVER applies to superusers or BYPASSRLS roles —
    a platform connected that way runs with org isolation silently OFF.
    Returns True/False, or None when it cannot be determined (non-PG bind)."""
    try:
        with bind.connect() as conn:
            bypasses = conn.execute(text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles"
                " WHERE rolname = current_user"
            )).scalar()
        return not bool(bypasses)
    except Exception:
        return None
