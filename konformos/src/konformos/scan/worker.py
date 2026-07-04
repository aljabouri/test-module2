"""Async scan worker — the Task Queue seam (Tech Spec v1.0 §2.3/§5: scans are
202 + poll, never synchronous). In-process thread pool now; the enqueue/run
interface is what Celery/Redis replaces at scale — states and transactions
stay identical (SM-SCAN).

SM-SCAN-02: the transition to `completed` is ONE transaction: findings +
readiness + property cache + timeline event — any failure rolls back all and
the scan lands in `failed` with the error recorded (ERR-02).
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from konformos.core import hashing  # noqa: F401 (chain built via TimelineRepository)
from konformos.db.models import (
    ComplianceProfileRow,
    Finding as FindingRow,
    Property,
    ReadinessResultRow,
    Scan,
)
from konformos.db.repository import TimelineRepository
from konformos.db.session import set_org_context
from konformos.evaluation.scoring import SCORING_VERSION, compute_readiness
from konformos.registry.loader import Catalog
from konformos.registry.resolver import resolve
from konformos.scan.normalizer import normalize
from konformos.scan.static_engine import ENGINE_NAME, ENGINE_VERSION, scan_html
from konformos.schemas import ComplianceProfile


class ScanWorker:
    def __init__(self, session_factory, catalog: Catalog, max_workers: int = 2):
        self._session_factory = session_factory
        self._catalog = catalog
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def enqueue(self, scan_id: uuid.UUID):
        """Returns the future so tests can join; production callers ignore it."""
        return self._executor.submit(self._run, scan_id)

    # ------------------------------------------------------------------
    def _load_profile(self, session: Session, property_id: uuid.UUID) -> ComplianceProfile:
        row = session.execute(
            select(ComplianceProfileRow)
            .where(ComplianceProfileRow.property_id == property_id)
            .order_by(ComplianceProfileRow.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None:  # sensible default: DE, latest, strictest (Flow A step 3)
            return ComplianceProfile(
                property_id=str(property_id), selected_jurisdictions=["DE"],
                pack_binding="latest", combination_mode="strictest",
            )
        return ComplianceProfile(
            property_id=str(property_id),
            selected_jurisdictions=list(row.selected_jurisdictions),
            pack_binding=row.pack_binding,
            pinned_versions=row.pinned_versions,
            combination_mode=row.combination_mode,
        )

    def _db_packs(self, session: Session):
        """Resolution uses the packs in the DB (the registry of record)."""
        from konformos.db.models import RulePackRow
        from konformos.schemas import RulePack

        rows = session.execute(select(RulePackRow)).scalars().all()
        packs = []
        for row in rows:
            packs.append(RulePack.model_validate(dict(
                jurisdiction=row.jurisdiction, version=row.version,
                effective_from=row.effective_from, status=row.status,
                legal_basis=row.legal_basis, rule_refs=row.rule_refs,
                report_template_id=row.report_template_id,
                seed=row.seed, seed_provenance=row.seed_provenance,
                signed_by=str(row.signed_by) if row.signed_by else None,
                signed_at=row.signed_at,
                source_change_events=[str(e) for e in (row.source_change_events or [])],
            )))
        return packs

    def _fetch_pages(self, scan: Scan) -> tuple[list[tuple[str, str]], list[dict]]:
        snapshot = scan.profile_snapshot or {}
        input_ref = snapshot.get("input_ref", {})
        if scan.input_type == "url":
            from konformos.scan.crawler import crawl
            result = crawl(
                input_ref["url"],
                max_pages=snapshot.get("page_cap", 1),
            )
            return result.pages, result.pages_skipped
        raise ValueError(f"input_type {scan.input_type} not implemented yet")

    def _run(self, scan_id: uuid.UUID) -> None:
        with self._session_factory() as session:
            scan = session.execute(
                select(Scan).where(Scan.id == scan_id)
            ).scalar_one()
            set_org_context(session, scan.organization_id)
            try:
                self._execute(session, scan)
                session.commit()
            except Exception as exc:
                session.rollback()
                with self._session_factory() as failure_session:
                    failed = failure_session.execute(
                        select(Scan).where(Scan.id == scan_id)
                    ).scalar_one()
                    failed.status = "failed"
                    failed.profile_snapshot = {
                        **(failed.profile_snapshot or {}),
                        "error": {"code": "scan_failed", "message": str(exc)[:500]},
                    }
                    failure_session.commit()

    def _execute(self, session: Session, scan: Scan) -> None:
        # queued → running with the frozen snapshot (INV-SC-01)
        profile = self._load_profile(session, scan.property_id)
        packs = self._db_packs(session)
        ruleset = resolve(profile, date.today(), packs)
        scan.status = "running"
        scan.profile_snapshot = {
            **(scan.profile_snapshot or {}),
            "profile": profile.model_dump(),
            "pack_versions": ruleset.pack_versions,
        }
        scan.engine_versions = {ENGINE_NAME: ENGINE_VERSION}  # INV-SC-02
        session.flush()

        pages, skipped = self._fetch_pages(scan)
        if not pages:
            raise RuntimeError("BR-EVAL-07: no successfully scanned pages")

        raw = []
        for path, html in pages:
            raw.extend(scan_html(path, html))
        try:  # axe as second engine when the environment allows
            from konformos.scan.axe_engine import AxeEngine, AxeUnavailable
            try:
                axe = AxeEngine()
                raw.extend(axe.scan_pages(pages))
                scan.engine_versions["axe-core"] = axe.version or "unknown"
            except AxeUnavailable:
                pass
        except ImportError:
            pass

        normalization = normalize(raw, self._catalog)
        results = compute_readiness(
            ruleset, self._catalog.rules,
            [f.to_finding_input() for f in normalization.findings],
            pages_scanned=len(pages),
        )

        # SM-SCAN-02: one transaction from here to completed
        for finding in normalization.findings:
            session.add(FindingRow(
                scan_id=scan.id, rule_code=finding.rule_code,
                severity=finding.severity,
                location={**finding.location, "page": finding.page},
                evidence=finding.evidence, source="automated", status="open",
            ))
        scores = {}
        for label, result in results.items():
            scores[label] = result.score
            session.add(ReadinessResultRow(
                scan_id=scan.id, jurisdiction=label, score=result.score,
                gaps=[vars(g) for g in result.gaps],
                computed_against_pack=result.computed_against_pack,  # INV-RD-01
            ))
        prop = session.execute(
            select(Property).where(Property.id == scan.property_id)
        ).scalar_one()
        prop.readiness_current = scores  # INV-RD-02: cache from results only

        TimelineRepository.append(session, scan.property_id, "scan_completed", {
            "scan_id": str(scan.id), "pages_scanned": len(pages),
            "pages_skipped": skipped, "findings": len(normalization.findings),
            "engine_versions": scan.engine_versions,
            "scoring_version": SCORING_VERSION,
        })
        TimelineRepository.append(session, scan.property_id, "readiness_changed", {
            "scan_id": str(scan.id), "scores": scores,
            "pack_versions": scan.profile_snapshot["pack_versions"],
        })
        scan.profile_snapshot = {**scan.profile_snapshot, "pages_skipped": skipped}
        scan.status = "completed"
