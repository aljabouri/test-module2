"""RulePack model — Tech Spec v1.0 §8.3, Engineering Rules v1.1 VAL-PACK-01,
VAL-ID-02/03, INV-RP-03, BR-LEG-03."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from konformos.schemas.rule import RULE_CODE_PATTERN

PACK_VERSION_PATTERN = r"^(DE|EU|US)-[0-9]{4}\.[0-9]+(\.[0-9]+)?$"

Jurisdiction = Literal["DE", "EU", "US"]


class RuleRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str = Field(pattern=RULE_CODE_PATTERN)
    weight: int = Field(ge=0, le=10)
    mandatory: bool


class RulePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdiction: Jurisdiction
    version: str = Field(pattern=PACK_VERSION_PATTERN)
    effective_from: date
    status: Literal["draft", "active", "superseded"]
    legal_basis: str = Field(min_length=1)
    rule_refs: list[RuleRef] = Field(min_length=1)
    report_template_id: Optional[str] = None
    seed: bool = False
    seed_provenance: Optional[str] = None
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None
    source_change_events: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _pack_rules(self) -> "RulePack":
        # VAL-ID-02: version prefix must equal jurisdiction
        if not self.version.startswith(f"{self.jurisdiction}-"):
            raise ValueError("VAL-ID-02: version prefix must equal jurisdiction")
        # VAL-PACK-01: no duplicate rule_code within a pack
        codes = [r.rule_code for r in self.rule_refs]
        if len(codes) != len(set(codes)):
            raise ValueError("VAL-PACK-01: duplicate rule_code within pack")
        # BR-LEG-03: seed packs must document provenance
        if self.seed and not self.seed_provenance:
            raise ValueError("BR-LEG-03: seed=true requires seed_provenance")
        # INV-RP-03 + BR-LEG-03: published packs must be signed, and traceable
        # to change events unless they are seed packs.
        if self.status in ("active", "superseded"):
            if not self.signed_by or not self.signed_at:
                raise ValueError("INV-RP-03: published pack requires signed_by and signed_at")
            if not self.seed and not self.source_change_events:
                raise ValueError("BR-LEG-03: published non-seed pack requires source_change_events")
        return self


def is_effective(pack: RulePack, on_date: date) -> bool:
    """BR-LEG-04: a pack is selectable only once its effective_from has arrived."""
    return pack.effective_from <= on_date
