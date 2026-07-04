"""Dossier sealing + PUBLIC verification (roadmap point 1).

The sealed content is public-by-construction: it carries no customer identity
(no organization, no property label, no URL) — only what an authority needs
to verify: scope, pack versions, readiness snapshot, chain integrity, and the
seal itself. INV-DS-01 applies to the canonical content (the v0 equivalent of
the final PDF bytes); INV-DS-02: pack versions live inside the sealed content;
INV-DS-03: assessment wording only, never certification.

NFR-REL-02 / EDGE-TL-01: the full timeline chain is verified BEFORE sealing —
a broken chain blocks dossier generation, we never seal broken evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from konformos.core.hashing import GENESIS, SealedEvent, canonical_hash, verify_chain

DISCLAIMER = (
    "Assessment documentation (Nachweis der Bemühungen) — "
    "توثيق تقييم واجتهاد، وليس اعتماداً رسمياً."
)


@dataclass(frozen=True)
class SealedDossier:
    content: dict
    dossier_hash: str


def build_dossier(
    *,
    jurisdictions: list[str],
    pack_versions: dict[str, str],
    readiness: dict[str, int],
    generated_at: str,
    events: list[SealedEvent],
    scoring_version: str,
    engine_versions: dict[str, str],
) -> SealedDossier:
    verify_chain(events)  # raises ChainBroken → no dossier over broken evidence
    content = {
        "kind": "konformos-dossier",
        "format_version": "1",
        "generated_at": generated_at,
        "jurisdictions": sorted(jurisdictions),
        "pack_versions": pack_versions,  # INV-DS-02: inside the sealed content
        "readiness": readiness,
        "scoring_version": scoring_version,
        "engine_versions": engine_versions,
        "timeline": {
            "length": len(events),
            "head_hash": events[-1].content_hash if events else GENESIS,
            "chain_valid": True,
        },
        "disclaimer": DISCLAIMER,
    }
    return SealedDossier(content=content, dossier_hash=canonical_hash(content))


def verify_dossier(content: dict, expected_hash: str) -> bool:
    """Anyone can recompute the seal — the basis of the public verify page."""
    return canonical_hash(content) == expected_hash


class DossierRegistry:
    """In-memory registry keyed by seal (DB-backed in the persistence milestone)."""

    def __init__(self) -> None:
        self._by_hash: dict[str, SealedDossier] = {}

    def register(self, dossier: SealedDossier) -> None:
        self._by_hash[dossier.dossier_hash] = dossier

    def get(self, dossier_hash: str) -> SealedDossier | None:
        return self._by_hash.get(dossier_hash)
