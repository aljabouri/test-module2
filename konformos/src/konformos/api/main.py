"""FastAPI surface — Tech Spec v1.0 §5, error envelope per Engineering Rules
v1.1 ERR-00. Phase-0 slice: catalog is loaded (and thereby validated) at
startup; evaluation is exposed for the resolve→score heart. Persistence,
auth/RBAC and async scanning attach here in the next milestones.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from konformos.core.hashing import seal_event
from konformos.dossier.sealing import DossierRegistry, build_dossier, verify_dossier
from konformos.evaluation.scoring import (
    SCORING_VERSION,
    FindingInput,
    NoPagesScanned,
    compute_readiness,
)
from konformos.moat.knowledge import KnowledgeStore
from konformos.registry.loader import Catalog, load_catalog
from konformos.registry.resolver import (
    PackNotEffective,
    PackNotFound,
    resolve,
)
from konformos.scan.normalizer import normalize
from konformos.scan.static_engine import ENGINE_NAME, ENGINE_VERSION, scan_html
from konformos.schemas import ComplianceProfile


def error_body(code: str, message: str, details: Optional[dict] = None) -> dict:
    # ERR-00: one envelope, no internals leaked
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        }
    }


class FindingBody(BaseModel):
    rule_code: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    status: Literal["open", "fixed", "wont_fix", "false_positive"]
    page: str


class EvaluateRequest(BaseModel):
    profile: ComplianceProfile
    findings: list[FindingBody]
    pages_scanned: int = Field(gt=0)
    on_date: date


class PageBody(BaseModel):
    path: str = Field(min_length=1)
    html: str = Field(min_length=1)


class ScanHtmlRequest(BaseModel):
    profile: ComplianceProfile
    pages: list[PageBody] = Field(min_length=1, max_length=50)  # BR-SCAN-01 cap
    on_date: date


class PreviewRequest(BaseModel):
    platform: str = Field(min_length=1)
    theme_name: str = Field(min_length=1)
    theme_version: Optional[str] = None
    theme_confidence: float = Field(ge=0.0, le=1.0)


def _run_scan(catalog: Catalog, body: ScanHtmlRequest):
    """Shared vertical slice: HTML pages → engine → Normalizer → readiness."""
    raw = []
    for page in body.pages:
        raw.extend(scan_html(page.path, page.html))
    normalization = normalize(raw, catalog)
    ruleset = resolve(body.profile, body.on_date, catalog.packs)
    results = compute_readiness(
        ruleset,
        catalog.rules,
        [f.to_finding_input() for f in normalization.findings],
        pages_scanned=len(body.pages),
    )
    return normalization, results


def _readiness_json(results) -> dict:
    return {
        label: {
            "score": r.score,
            "computed_against_pack": r.computed_against_pack,
            "scoring_version": r.scoring_version,
            "rules_evaluated": r.rules_evaluated,
            "rules_manual_pending": r.rules_manual_pending,
            "wont_fix_disclosed": r.wont_fix,
            "gaps": [vars(g) for g in r.gaps],
        }
        for label, r in results.items()
    }


def create_app(
    catalog: Catalog | None = None,
    knowledge_store: KnowledgeStore | None = None,
    session_factory=None,
) -> FastAPI:
    import os
    import time as time_module

    from konformos.api.routes_db import ApiError, router as db_router
    from konformos.api.routes_growth import router as growth_router

    # Auto-wire the DB when launched from uvicorn (no factory passed) and a
    # database is reachable — so `create_app` used as an ASGI factory is fully
    # functional, not just the in-tests wiring.
    if session_factory is None:
        try:
            from konformos.db.session import make_engine, make_session_factory
            engine = make_engine()
            with engine.connect():  # fail fast if unreachable
                pass
            session_factory = make_session_factory(engine)
        except Exception:
            session_factory = None  # /v1 routes return 503 until DB is up

    # INV-ORG-01 startup guard: superuser/BYPASSRLS connections silently
    # disable Row-Level Security. Refuse to start under KONFORMOS_REQUIRE_RLS;
    # otherwise log CRITICAL and surface the state in /health.
    rls_ok: bool | None = None
    if session_factory is not None:
        try:
            from konformos.db.session import rls_enforceable
            with session_factory() as _probe:
                rls_ok = rls_enforceable(_probe.get_bind())
        except Exception:
            rls_ok = None
        if rls_ok is False:
            _msg = (
                "INV-ORG-01: the database role is SUPERUSER/BYPASSRLS — "
                "Row-Level Security does NOT apply and org isolation is OFF. "
                "Connect as a NOSUPERUSER role that owns the database "
                "(fresh docker volume: `docker compose down -v` then up)."
            )
            if os.environ.get("KONFORMOS_REQUIRE_RLS"):
                raise RuntimeError(_msg)
            import logging
            logging.getLogger("konformos").critical(_msg)

    app = FastAPI(title="KonformOS API", version="0.1.0")
    app.state.rls_enforceable = rls_ok
    app.state.catalog = catalog or load_catalog()
    app.state.dossiers = DossierRegistry()
    app.state.knowledge = knowledge_store or KnowledgeStore()
    app.state.session_factory = session_factory
    app.state.scan_futures = {}
    if session_factory is not None:
        from konformos.fix.claude_adapter import ClaudeFixGenerator
        from konformos.scan.scheduler import recover_stuck_scans
        from konformos.scan.worker import ScanWorker

        app.state.worker = ScanWorker(session_factory, app.state.catalog)
        app.state.fix_generator = ClaudeFixGenerator()
        try:  # queue durability: re-enqueue scans stranded by a restart
            with session_factory() as session:
                recover_stuck_scans(session, app.state.worker)
        except Exception:
            pass  # fresh DB / migrations not applied yet — nothing to recover
    app.include_router(db_router)
    app.include_router(growth_router)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status,
            content=error_body(exc.code, exc.message, exc.details),
        )

    # ── NFR-RATE-01: simple token bucket per caller ─────────────────────
    rate_buckets: dict[str, list] = {}

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        limit = int(os.environ.get("KONFORMOS_RATE_LIMIT_PER_MIN", "120"))
        if limit <= 0 or request.url.path == "/health":
            return await call_next(request)
        key = request.headers.get("authorization") \
            or (request.client.host if request.client else "anon")
        now = time_module.monotonic()
        window = rate_buckets.setdefault(key, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= limit:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content=error_body("rate_limited", "تجاوزت حد الطلبات — أعد المحاولة لاحقاً."),
            )
        window.append(now)
        return await call_next(request)

    @app.exception_handler(ValidationError)
    async def _validation(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "بيانات غير صالحة.",
                {"errors": [e["msg"] for e in exc.errors()]},
            ),
        )

    @app.get("/health")
    def health():
        catalog: Catalog = app.state.catalog
        return {
            "status": "ok",
            "rules": len(catalog.rules),
            "packs": [p.version for p in catalog.packs],
            "db": app.state.session_factory is not None,
            "rls_enforceable": app.state.rls_enforceable,
        }

    @app.get("/v1/catalog/rule-packs")
    def rule_packs(jurisdiction: Optional[Literal["DE", "EU", "US"]] = None):
        """Stateless catalog listing (seed files). The registry of record is
        the DB-backed /v1/legal/rule-packs."""
        catalog: Catalog = app.state.catalog
        packs = [
            p for p in catalog.packs
            if jurisdiction is None or p.jurisdiction == jurisdiction
        ]
        return {
            "rule_packs": [
                {
                    "jurisdiction": p.jurisdiction,
                    "version": p.version,
                    "status": p.status,
                    "effective_from": p.effective_from.isoformat(),
                    "legal_basis": p.legal_basis,
                    "rule_count": len(p.rule_refs),
                }
                for p in packs
            ]
        }

    @app.post("/v1/evaluate")
    def evaluate(body: EvaluateRequest):
        catalog: Catalog = app.state.catalog
        try:
            ruleset = resolve(body.profile, body.on_date, catalog.packs)
        except PackNotEffective as exc:
            return JSONResponse(status_code=422, content=error_body("pack_not_effective", str(exc)))
        except PackNotFound as exc:
            return JSONResponse(status_code=404, content=error_body("not_found", str(exc)))
        try:
            results = compute_readiness(
                ruleset,
                catalog.rules,
                [FindingInput(**f.model_dump()) for f in body.findings],
                body.pages_scanned,
            )
        except NoPagesScanned as exc:
            return JSONResponse(status_code=422, content=error_body("validation_error", str(exc)))
        return {"readiness": _readiness_json(results)}

    @app.post("/v1/scan-html")
    def scan_html_endpoint(body: ScanHtmlRequest):
        """Full vertical slice: pages → internal engine → Normalizer → readiness."""
        catalog: Catalog = app.state.catalog
        try:
            normalization, results = _run_scan(catalog, body)
        except PackNotEffective as exc:
            return JSONResponse(status_code=422, content=error_body("pack_not_effective", str(exc)))
        except PackNotFound as exc:
            return JSONResponse(status_code=404, content=error_body("not_found", str(exc)))
        return {
            "engine_versions": {ENGINE_NAME: ENGINE_VERSION},  # INV-SC-02
            "findings": [
                {
                    "rule_code": f.rule_code,
                    "severity": f.severity,
                    "page": f.page,
                    "location": f.location,
                    "evidence": f.evidence,
                    "status": f.status,
                }
                for f in normalization.findings
            ],
            "unmapped_issues": [vars(u) for u in normalization.unmapped],  # INV-FD-01
            "readiness": _readiness_json(results),
        }

    @app.post("/v1/dossiers")
    def create_dossier(body: ScanHtmlRequest):
        """Scan → readiness → sealed timeline → sealed dossier + public verify URL."""
        catalog: Catalog = app.state.catalog
        try:
            normalization, results = _run_scan(catalog, body)
        except PackNotEffective as exc:
            return JSONResponse(status_code=422, content=error_body("pack_not_effective", str(exc)))
        except PackNotFound as exc:
            return JSONResponse(status_code=404, content=error_body("not_found", str(exc)))

        scores = {label: r.score for label, r in results.items()}
        pack_versions = {
            label: r.computed_against_pack for label, r in results.items()
        }
        e1 = seal_event("scan_completed", {
            "pages_scanned": len(body.pages),
            "findings": len(normalization.findings),
            "engine_versions": {ENGINE_NAME: ENGINE_VERSION},
        }, None)
        e2 = seal_event("readiness_changed", {"scores": scores}, e1)

        dossier = build_dossier(
            jurisdictions=list(body.profile.selected_jurisdictions),
            pack_versions=pack_versions,
            readiness=scores,
            generated_at=datetime.now(timezone.utc).isoformat(),
            events=[e1, e2],
            scoring_version=SCORING_VERSION,
            engine_versions={ENGINE_NAME: ENGINE_VERSION},
        )
        app.state.dossiers.register(dossier)
        return {
            "dossier_hash": dossier.dossier_hash,
            "verify_url": f"/v1/verify/{dossier.dossier_hash}",
            "readiness": scores,
        }

    def _db_dossier_record(dossier_hash: str) -> dict | None:
        """Public verify for DB/PDF dossiers: recompute the seal over the PDF
        bytes (INV-DS-01) and expose only the identity-free summary."""
        if app.state.session_factory is None:
            return None
        from pathlib import Path

        from sqlalchemy import select

        from konformos.db.models import Dossier as DossierRow
        from konformos.dossier.pdf import verify_pdf_dossier

        with app.state.session_factory() as session:
            row = session.execute(
                select(DossierRow).where(DossierRow.dossier_hash == dossier_hash)
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "valid": verify_pdf_dossier(Path(row.pdf_url), dossier_hash),
                "dossier_hash": dossier_hash,
                "content": {
                    "kind": "konformos-dossier",
                    "generated_at": row.generated_at.isoformat(),
                    "jurisdictions": list(row.jurisdictions or []),
                    "pack_versions": row.pack_versions,
                    "readiness": row.readiness_snapshot,
                    "timeline": {
                        "length": (row.timeline_range or {}).get("to_sequence", 0),
                        "chain_valid": True,  # verified before sealing (NFR-REL-02)
                    },
                    "disclaimer": "Assessment documentation — توثيق تقييم واجتهاد.",
                },
            }

    @app.get("/v1/verify/{dossier_hash}")
    def verify(dossier_hash: str):
        """PUBLIC verification — no account, no identity in the response."""
        dossier = app.state.dossiers.get(dossier_hash)
        if dossier is not None:
            return {
                "valid": verify_dossier(dossier.content, dossier_hash),
                "dossier_hash": dossier_hash,
                "content": dossier.content,
            }
        record = _db_dossier_record(dossier_hash)
        if record is not None:
            return record
        return JSONResponse(
            status_code=404,
            content=error_body("not_found", "لا يوجد توثيق بهذا الختم."),
        )

    @app.get("/v1/verify/{dossier_hash}/page", response_class=HTMLResponse)
    def verify_page(dossier_hash: str):
        dossier = app.state.dossiers.get(dossier_hash)
        if dossier is not None:
            valid = verify_dossier(dossier.content, dossier_hash)
            return HTMLResponse(
                content=_verify_html(dossier.content if valid else None, dossier_hash, valid))
        record = _db_dossier_record(dossier_hash)
        if record is not None:
            return HTMLResponse(content=_verify_html(
                record["content"] if record["valid"] else None,
                dossier_hash, record["valid"]))
        return HTMLResponse(status_code=404, content=_verify_html(None, dossier_hash))

    @app.get("/app", response_class=HTMLResponse)
    def dashboard():
        from konformos.api.dashboard import DASHBOARD_HTML
        return HTMLResponse(content=DASHBOARD_HTML)

    @app.post("/v1/preview")
    def preview(body: PreviewRequest):
        """Proactive Theme Intelligence: known defects before any crawl."""
        store: KnowledgeStore = app.state.knowledge
        report = store.predict(
            body.platform, body.theme_name, body.theme_version, body.theme_confidence,
        )
        return {
            "stack_signature": report.stack_signature,
            "confidence": report.confidence,
            # BR-FP-01: hedged wording below threshold, no enrichment at all
            "statement": (
                "الثقة في كشف الثيم غير كافية — لا استنتاجات مسبقة (فحص كامل مطلوب)."
                if report.hedged
                else f"نعرف مسبقاً {report.known_issue_count} نمط عيب موثّقاً لهذا الثيم عبر متاجر متعددة."
            ),
            "known_issue_count": report.known_issue_count,
            "known_issues": report.known_issues,
        }

    return app


def _verify_html(content: dict | None, dossier_hash: str, valid: bool = False) -> str:
    """Minimal public verify page. INV-DS-03: assessment wording only."""
    if content is None:
        status = "❌ غير موجود أو مكسور الختم — Not found / seal invalid"
        body = ""
    else:
        status = "✅ الختم سليم — Seal verified" if valid else "❌ الختم مكسور"
        rows = "".join(
            f"<tr><td>{jurisdiction}</td><td>{content['pack_versions'].get(jurisdiction, '—')}</td>"
            f"<td>{score}/100</td></tr>"
            for jurisdiction, score in content["readiness"].items()
        )
        body = f"""
    <p>تاريخ التوليد: {content['generated_at']}</p>
    <table border="1" cellpadding="6">
      <tr><th>النطاق</th><th>إصدار المعيار</th><th>Readiness</th></tr>
      {rows}
    </table>
    <p>سلسلة الإثبات: {content['timeline']['length']} حدثاً مختوماً —
       سليمة: {content['timeline']['chain_valid']}</p>
    <p><em>{content['disclaimer']}</em></p>"""
    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>KonformOS — التحقق من التوثيق</title></head>
<body style="font-family:sans-serif;max-width:640px;margin:2rem auto">
  <h1>KonformOS — التحقق العام</h1>
  <p><strong>{status}</strong></p>
  <p style="word-break:break-all"><code>{dossier_hash}</code></p>
  {body}
</body></html>"""

