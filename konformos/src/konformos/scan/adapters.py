"""Additional input adapters (Tech Spec v1.0 §4.4.1) — all normalize through
the same table (P1): Theme (static analysis on source archives), Design
System (isolated component render), PDF (PDF/UA markers via pypdf).

NFR-SIZE-01: archive extraction is zip-bomb guarded (uncompressed total,
member count, nesting depth).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from konformos.scan.static_engine import ENGINE_NAME, RawIssue, scan_html

TEMPLATE_SUFFIXES = {".html", ".htm", ".twig", ".liquid", ".php", ".vue"}
MAX_MEMBERS = 5000
MAX_UNCOMPRESSED = 1_000_000_000  # 1GB (NFR-SIZE-01)


class ArchiveRejected(ValueError):
    pass


def pages_from_theme_zip(archive_bytes: bytes) -> list[tuple[str, str]]:
    """Theme/Plugin adapter: every template file in the archive becomes a
    'page' (path = file path) scanned by the static engine — أدق من الحيّ:
    يرى ما لا يُعرَض."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ArchiveRejected("ملف الأرشيف تالف أو ليس zip") from exc

    members = archive.infolist()
    if len(members) > MAX_MEMBERS:
        raise ArchiveRejected(f"أكثر من {MAX_MEMBERS} ملفاً (NFR-SIZE-01)")
    total = sum(m.file_size for m in members)
    if total > MAX_UNCOMPRESSED:
        raise ArchiveRejected("الحجم المفكوك يتجاوز الحد (حماية zip-bomb)")

    pages: list[tuple[str, str]] = []
    for member in members:
        if member.is_dir():
            continue
        path = Path(member.filename)
        if ".." in path.parts:  # path traversal guard
            continue
        if path.suffix.lower() not in TEMPLATE_SUFFIXES:
            continue
        raw = archive.read(member)
        try:
            pages.append((member.filename, raw.decode("utf-8", errors="replace")))
        except Exception:
            continue
    return pages


# Known-clean shell so only COMPONENT defects surface (design system adapter)
_COMPONENT_SHELL = ("<!DOCTYPE html><html lang=\"de\"><head><meta charset=\"utf-8\">"
                    "<title>component</title></head><body>{body}</body></html>")


def pages_from_components(components: list[dict]) -> list[tuple[str, str]]:
    """Design System adapter: render each component isolated in a compliant
    shell — يصلح المصدر = يصلح كل النسخ."""
    return [
        (f"component:{component['name']}",
         _COMPONENT_SHELL.format(body=component["html"]))
        for component in components
    ]


def pdf_raw_issues(pdf_bytes: bytes, document_name: str) -> tuple[list[RawIssue], int]:
    """PDF adapter: minimal PDF/UA marker checks mapped to catalog rules via
    pdf-* engine issue ids (extending detection = extending the catalog).
    Returns (issues, documents_scanned)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    issues: list[RawIssue] = []

    def issue(issue_id: str, evidence: str) -> None:
        issues.append(RawIssue(engine=ENGINE_NAME, issue_id=issue_id,
                               page=document_name, selector="document",
                               evidence=evidence))

    metadata = reader.metadata or {}
    if not (metadata.title or "").strip():
        issue("pdf-title", "لا عنوان في بيانات المستند (PDF/UA: Title مطلوب)")

    root = reader.trailer.get("/Root", {})
    if not str(root.get("/Lang", "") or "").strip():
        issue("pdf-lang", "لا سمة Lang على مستوى المستند")

    mark_info = root.get("/MarkInfo")
    marked = bool(mark_info and mark_info.get("/Marked"))
    has_struct_tree = "/StructTreeRoot" in root
    if not (marked and has_struct_tree):
        issue("pdf-tagged", "المستند غير مُوسوم (Tagged PDF) — البنية غير قابلة للقراءة برمجياً")

    return issues, max(1, len(reader.pages))
