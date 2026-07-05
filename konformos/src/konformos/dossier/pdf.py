"""Audit-Ready Dossier PDF — Tech Spec v1.0 §4.8.2.

INV-DS-01: dossier_hash = SHA-256 of the FINAL PDF BYTES.
INV-DS-02: pack versions printed inside the document body.
INV-DS-03: assessment wording only (guarded by tests on the bytes).
BR-CUST-03: mandatory "Limitations of this assessment" section.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

STORAGE_ENV = "KONFORMOS_STORAGE_DIR"


def storage_dir() -> Path:
    path = Path(os.environ.get(STORAGE_ENV, "storage"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class PdfDossier:
    pdf_path: Path
    dossier_hash: str
    content_summary: dict


def generate_pdf_dossier(
    *,
    jurisdictions: list[str],
    pack_versions: dict[str, str],
    readiness: dict[str, int],
    gaps: list[dict],
    generated_at: str,
    timeline_length: int,
    timeline_head_hash: str,
    engine_versions: dict[str, str],
    pages_scanned: int,
    rules_evaluated: int,
    rules_manual_pending: int,
    scoring_version: str,
) -> PdfDossier:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "KonformOS - Accessibility Conformance Assessment", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Generated: {generated_at}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Readiness against named standards", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    for jurisdiction in sorted(readiness):
        pack = pack_versions.get(jurisdiction, "-")
        pdf.cell(0, 7, f"  {jurisdiction}: {readiness[jurisdiction]}/100  "
                       f"(computed against pack {pack})", new_x=XPos.LMARGIN, new_y=YPos.NEXT)  # INV-DS-02
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Top remaining gaps (by legal priority)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    for gap in gaps[:15]:
        pdf.cell(0, 6, f"  - {gap['rule_code']} [{gap['pack_version']}] "
                       f"penalty {gap['penalty']} on {gap['pages_affected']} page(s)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if not gaps:
        pdf.cell(0, 6, "  none - no open automated findings", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Limitations of this assessment", new_x=XPos.LMARGIN, new_y=YPos.NEXT)  # BR-CUST-03
    pdf.set_font("Helvetica", "", 10)
    for line in (
        f"Pages scanned: {pages_scanned}.",
        f"Automated coverage: {rules_evaluated} rules evaluated automatically; "
        f"{rules_manual_pending} rules require human expert verification.",
        f"Engines: {', '.join(f'{k} {v}' for k, v in engine_versions.items())}. "
        f"Scoring algorithm version {scoring_version}.",
        "The automated score covers only the automatable subset of the standard.",
    ):
        pdf.multi_cell(0, 6, "  " + line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Evidence integrity", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, f"  Sealed timeline: {timeline_length} hash-chained events. "
                         f"Chain head: {timeline_head_hash[:32]}...", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5,
        "This document is assessment documentation of conformance efforts "
        "(Nachweis der Bemuehungen). It is not an official accreditation.")

    raw = bytes(pdf.output())
    dossier_hash = hashlib.sha256(raw).hexdigest()  # INV-DS-01: hash of the bytes
    pdf_path = storage_dir() / f"dossier-{dossier_hash[:16]}.pdf"
    pdf_path.write_bytes(raw)

    return PdfDossier(
        pdf_path=pdf_path,
        dossier_hash=dossier_hash,
        content_summary={
            "jurisdictions": sorted(jurisdictions),
            "pack_versions": pack_versions,
            "readiness": readiness,
            "generated_at": generated_at,
            "timeline": {"length": timeline_length, "head_hash": timeline_head_hash},
        },
    )


def verify_pdf_dossier(pdf_path: Path, expected_hash: str) -> bool:
    if not pdf_path.is_file():
        return False
    return hashlib.sha256(pdf_path.read_bytes()).hexdigest() == expected_hash
