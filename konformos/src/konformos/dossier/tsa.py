"""RFC 3161 timestamping seam — INV-TL-06 machinery.

The chain never depends on TSA (insertion proceeds with a null token); this
module completes tokens afterwards. `TSAClient` is the pluggable seam: wire a
real RFC 3161 client (e.g. rfc3161ng against a trusted TSA) in production;
`NullTSA` documents the absence honestly, `backfill_tsa_tokens` is the
recurring job either way.
"""
from __future__ import annotations

import uuid
from typing import Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.db.models import TimelineEventRow


class TSAClient(Protocol):
    def timestamp(self, content_hash: str) -> Optional[str]:
        """Returns an encoded timestamp token for the hash, or None."""


class NullTSA:
    """No TSA configured — tokens stay null; the hash chain stands alone."""

    def timestamp(self, content_hash: str) -> Optional[str]:
        return None


def backfill_tsa_tokens(session: Session, client: TSAClient,
                        property_id: uuid.UUID | None = None,
                        limit: int = 500) -> int:
    """Completes missing timestamp_token values (INV-TL-06 backfill job).

    The append-only trigger (migration 0004 refinement) permits updates to
    timestamp_token ONLY — every sealed column (payload, hashes, sequence)
    remains immutable at the DB layer. Returns the count filled.
    """
    query = select(TimelineEventRow).where(
        TimelineEventRow.timestamp_token.is_(None))
    if property_id is not None:
        query = query.where(TimelineEventRow.property_id == property_id)
    rows = session.execute(query.limit(limit)).scalars().all()

    filled = 0
    for row in rows:
        token = client.timestamp(row.content_hash)
        if token is not None:
            row.timestamp_token = token
            filled += 1
    return filled
