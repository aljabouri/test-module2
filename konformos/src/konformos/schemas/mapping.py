"""RuleMapping model — Tech Spec v1.0 §8.5."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from konformos.schemas.rule import RULE_CODE_PATTERN

KNOWN_FRAMEWORKS = {"en_301_549", "bfsg", "ada_title_ii", "section_508"}


class RuleMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str = Field(pattern=RULE_CODE_PATTERN)
    equivalences: dict[str, str] = Field(min_length=1)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _known_frameworks(self) -> "RuleMapping":
        unknown = set(self.equivalences) - KNOWN_FRAMEWORKS
        if unknown:
            raise ValueError(f"unknown framework keys: {sorted(unknown)}")
        return self
