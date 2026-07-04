"""FastAPI surface — Tech Spec v1.0 §5, error envelope per Engineering Rules
v1.1 ERR-00. Phase-0 slice: catalog is loaded (and thereby validated) at
startup; evaluation is exposed for the resolve→score heart. Persistence,
auth/RBAC and async scanning attach here in the next milestones.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from konformos.evaluation.scoring import (
    FindingInput,
    NoPagesScanned,
    compute_readiness,
)
from konformos.registry.loader import Catalog, load_catalog
from konformos.registry.resolver import (
    PackNotEffective,
    PackNotFound,
    resolve,
)
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


def create_app(catalog: Catalog | None = None) -> FastAPI:
    app = FastAPI(title="KonformOS API", version="0.1.0")
    app.state.catalog = catalog or load_catalog()

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
        }

    @app.get("/v1/legal/rule-packs")
    def rule_packs(jurisdiction: Optional[Literal["DE", "EU", "US"]] = None):
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
        return {
            "readiness": {
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
        }

    return app

