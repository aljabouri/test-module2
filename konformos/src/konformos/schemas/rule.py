"""Rule model — Tech Spec v1.0 §8.2, Engineering Rules v1.1 VAL-ID-01 + VAL-RULE-01."""
from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

RULE_CODE_PATTERN = r"^[a-z0-9]+(-[a-z0-9.]+)*$"


class AutomatedTestLogic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["axe-core", "pa11y", "lighthouse", "internal"]
    rule_id: str = Field(min_length=1)
    additional_rule_ids: list[str] = Field(default_factory=list)
    manual_fallback: bool


class ManualTestLogic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_only: Literal[True]
    expert_guidance: str = Field(min_length=1)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=RULE_CODE_PATTERN, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    source_standard: str = Field(min_length=1)
    wcag_level: Optional[Literal["A", "AA", "AAA"]]
    automatable: bool
    test_logic: Union[AutomatedTestLogic, ManualTestLogic]
    introduced_in: Optional[str] = None
    deprecated: bool = False
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _val_rule_01(self) -> "Rule":
        # VAL-RULE-01: automatable=true ⟺ engine+rule_id; false ⟺ manual_only. No middle state.
        if self.automatable and not isinstance(self.test_logic, AutomatedTestLogic):
            raise ValueError("VAL-RULE-01: automatable=true requires engine + rule_id test_logic")
        if not self.automatable and not isinstance(self.test_logic, ManualTestLogic):
            raise ValueError("VAL-RULE-01: automatable=false requires manual_only test_logic")
        return self
