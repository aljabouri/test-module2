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
