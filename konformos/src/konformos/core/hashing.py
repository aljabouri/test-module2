"""Timeline sealing primitives — Engineering Rules v1.1 INV-TL-02/03/04.

INV-TL-02: content_hash = SHA-256(canonical_json(payload)), where canonical
JSON has keys sorted ascending at every level, UTF-8, no extra whitespace,
and nulls written (not dropped). All hashing MUST go through canonical_hash().
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS = "GENESIS"


def canonical_json(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SealedEvent:
    """An append-only timeline entry (INV-TL-01: never mutated, only created)."""

    sequence_number: int
    event_type: str
    payload: dict
    content_hash: str
    prev_hash: str


class ChainBroken(Exception):
    """Raised when hash-chain verification fails (ERR chain_broken — critical alert)."""

    def __init__(self, sequence_number: int, reason: str):
        self.sequence_number = sequence_number
        self.reason = reason
        super().__init__(f"chain broken at #{sequence_number}: {reason}")


def seal_event(event_type: str, payload: dict, prev: SealedEvent | None) -> SealedEvent:
    """Create the next chain entry. INV-TL-03: first event links to GENESIS."""
    return SealedEvent(
        sequence_number=1 if prev is None else prev.sequence_number + 1,
        event_type=event_type,
        payload=payload,
        content_hash=canonical_hash(payload),
        prev_hash=GENESIS if prev is None else prev.content_hash,
    )


def verify_chain(events: list[SealedEvent]) -> None:
    """Recompute and verify the full chain; raises ChainBroken at first break.

    Guards INV-TL-02 (hash matches payload), INV-TL-03 (linkage), INV-TL-04
    (sequence contiguous from 1, no gaps).
    """
    prev: SealedEvent | None = None
    for event in events:
        expected_seq = 1 if prev is None else prev.sequence_number + 1
        if event.sequence_number != expected_seq:
            raise ChainBroken(event.sequence_number, f"sequence gap (expected {expected_seq})")
        if event.content_hash != canonical_hash(event.payload):
            raise ChainBroken(event.sequence_number, "content_hash does not match payload")
        expected_prev = GENESIS if prev is None else prev.content_hash
        if event.prev_hash != expected_prev:
            raise ChainBroken(event.sequence_number, "prev_hash does not match previous event")
        prev = event
