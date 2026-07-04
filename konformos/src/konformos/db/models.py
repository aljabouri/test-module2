"""SQLAlchemy models — Tech Spec v1.0 §6, PostgreSQL-first (JSONB, ARRAY, RLS).

Deliberate structural decisions guarded by tests:
- knowledge_entries has NO organization/property/url columns at all (INV-KG-01
  is enforced by the schema itself, not just by code).
- timeline_events is append-only via a DB trigger (migration 0002) on top of
  the application-layer guard (INV-TL-01 defense in depth).
- rule updates are DATA, not migrations (Rules-as-Data): the schema below is
  stable; packs/rules change as rows.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Base(DeclarativeBase):
    type_annotation_map = {
        dict: JSONB,
        list: JSONB,
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# ── §6.1 الحساب ──────────────────────────────────────────────────────────
class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[str] = mapped_column(Text)  # merchant | agency
    name: Mapped[str] = mapped_column(Text)
    billing_email: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    data_sharing_consent: Mapped[bool] = mapped_column(Boolean, default=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    hashed_password: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
    stripe_subscription_id: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    seats: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(Text)


# ── §6.2 الملكية والبصمة ─────────────────────────────────────────────────
class Property(TimestampMixin, Base):
    __tablename__ = "properties"
    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    url: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text)
    current_fingerprint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    active_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    readiness_current: Mapped[dict | None] = mapped_column(JSONB)


class StackFingerprint(TimestampMixin, Base):
    __tablename__ = "stack_fingerprints"
    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    platform: Mapped[str] = mapped_column(Text)
    platform_version: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[dict | None] = mapped_column(JSONB)
    plugins: Mapped[list | None] = mapped_column(JSONB)
    frontend_framework: Mapped[str | None] = mapped_column(Text)
    component_library: Mapped[str | None] = mapped_column(Text)
    detection_confidence: Mapped[dict | None] = mapped_column(JSONB)
    raw_signals: Mapped[dict | None] = mapped_column(JSONB)


class ComplianceProfileRow(TimestampMixin, Base):
    __tablename__ = "compliance_profiles"
    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    selected_jurisdictions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    pack_binding: Mapped[str] = mapped_column(Text, default="latest")
    pinned_versions: Mapped[dict | None] = mapped_column(JSONB)
    combination_mode: Mapped[str] = mapped_column(Text, default="strictest")


# ── §6.3 القانون والقواعد (القلب) ────────────────────────────────────────
class LegalSource(TimestampMixin, Base):
    __tablename__ = "legal_sources"
    id: Mapped[uuid.UUID] = uuid_pk()
    jurisdiction: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(Text)
    check_frequency: Mapped[str] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None]
    last_content_hash: Mapped[str | None] = mapped_column(Text)


class LegalChangeEvent(TimestampMixin, Base):
    __tablename__ = "legal_change_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_sources.id"))
    detected_at: Mapped[datetime]
    change_type: Mapped[str] = mapped_column(Text)
    semantic_diff: Mapped[dict | None] = mapped_column(JSONB)
    llm_summary: Mapped[str | None] = mapped_column(Text)
    llm_proposed_pack_delta: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="pending_review")
    review_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class RuleRow(TimestampMixin, Base):
    __tablename__ = "rules"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True)  # INV-RP-05: never reused
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    wcag_level: Mapped[str | None] = mapped_column(Text)
    test_logic: Mapped[dict] = mapped_column(JSONB)
    automatable: Mapped[bool] = mapped_column(Boolean)
    source_standard: Mapped[str] = mapped_column(Text)


class RulePackRow(TimestampMixin, Base):
    __tablename__ = "rule_packs"
    id: Mapped[uuid.UUID] = uuid_pk()
    jurisdiction: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text, unique=True)
    effective_from: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text)  # draft | active | superseded
    legal_basis: Mapped[str] = mapped_column(Text)
    rule_refs: Mapped[list] = mapped_column(JSONB)
    report_template_id: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[bool] = mapped_column(Boolean, default=False)
    seed_provenance: Mapped[str | None] = mapped_column(Text)
    signed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signed_at: Mapped[datetime | None]
    source_change_events: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))


class RuleMappingRow(TimestampMixin, Base):
    __tablename__ = "rule_mappings"
    id: Mapped[uuid.UUID] = uuid_pk()
    rule_code: Mapped[str] = mapped_column(ForeignKey("rules.code"), unique=True)
    equivalences: Mapped[dict] = mapped_column(JSONB)


# ── §6.4 الفحص ───────────────────────────────────────────────────────────
class Scan(TimestampMixin, Base):
    __tablename__ = "scans"
    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    trigger: Mapped[str] = mapped_column(Text)
    input_type: Mapped[str] = mapped_column(Text)
    fingerprint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    profile_snapshot: Mapped[dict | None] = mapped_column(JSONB)  # INV-SC-01
    status: Mapped[str] = mapped_column(Text, default="queued")
    engine_versions: Mapped[dict | None] = mapped_column(JSONB)  # INV-SC-02


class Finding(TimestampMixin, Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = uuid_pk()
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id"))
    rule_code: Mapped[str] = mapped_column(ForeignKey("rules.code"))  # INV-FD-01
    severity: Mapped[str] = mapped_column(Text)
    location: Mapped[dict | None] = mapped_column(JSONB)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text, default="automated")
    status: Mapped[str] = mapped_column(Text, default="open")
    knowledge_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Fix(TimestampMixin, Base):
    __tablename__ = "fixes"
    id: Mapped[uuid.UUID] = uuid_pk()
    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("findings.id"))
    type: Mapped[str] = mapped_column(Text)
    diff: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    verified_survived: Mapped[bool | None] = mapped_column(Boolean)


class ReadinessResultRow(TimestampMixin, Base):
    __tablename__ = "readiness_results"
    id: Mapped[uuid.UUID] = uuid_pk()
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scans.id"))
    jurisdiction: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    gaps: Mapped[list | None] = mapped_column(JSONB)
    computed_against_pack: Mapped[str] = mapped_column(Text)  # INV-RD-01: NOT NULL


# ── §6.5 الخندق (بلا أي عمود هوية — INV-KG-01 بنيوياً) ───────────────────
class KnowledgeEntryRow(TimestampMixin, Base):
    __tablename__ = "knowledge_entries"
    id: Mapped[uuid.UUID] = uuid_pk()
    stack_signature: Mapped[str] = mapped_column(Text)
    rule_code: Mapped[str] = mapped_column(ForeignKey("rules.code"))
    pattern: Mapped[dict] = mapped_column(JSONB)
    known_fix: Mapped[dict | None] = mapped_column(JSONB)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    fix_success_rate: Mapped[float | None] = mapped_column(Float)
    validated_by_expert: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("stack_signature", "rule_code"),)  # BR-KG-02


# ── §6.6 الإثبات (Append-Only) ───────────────────────────────────────────
class TimelineEventRow(Base):
    __tablename__ = "timeline_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    sequence_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(Text)
    timestamp_token: Mapped[str | None] = mapped_column(Text)  # INV-TL-06: nullable
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    __table_args__ = (UniqueConstraint("property_id", "sequence_number"),)  # INV-TL-04


class Dossier(TimestampMixin, Base):
    __tablename__ = "dossiers"
    id: Mapped[uuid.UUID] = uuid_pk()
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id"))
    generated_at: Mapped[datetime]
    jurisdictions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    pack_versions: Mapped[dict] = mapped_column(JSONB)  # INV-DS-02
    readiness_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    timeline_range: Mapped[dict | None] = mapped_column(JSONB)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    dossier_hash: Mapped[str] = mapped_column(Text, unique=True)
    expert_signature_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ExpertReview(TimestampMixin, Base):
    __tablename__ = "expert_reviews"
    id: Mapped[uuid.UUID] = uuid_pk()
    scan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scans.id"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    manual_findings: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    signature: Mapped[dict | None] = mapped_column(JSONB)
    insurance_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="in_progress")
