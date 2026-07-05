"""ComplianceProfile model — Tech Spec v1.0 §8.4, Engineering Rules v1.1 VAL-PROF-01."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from konformos.schemas.pack import Jurisdiction


class ComplianceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property_id: str = Field(min_length=1)
    selected_jurisdictions: list[Jurisdiction] = Field(min_length=1)
    pack_binding: Literal["latest", "pinned"]
    pinned_versions: Optional[dict[Jurisdiction, str]] = None
    combination_mode: Literal["union", "strictest"]

    @model_validator(mode="after")
    def _val_prof_01(self) -> "ComplianceProfile":
        if len(set(self.selected_jurisdictions)) != len(self.selected_jurisdictions):
            raise ValueError("VAL-PROF-01: duplicate jurisdictions")
        if self.pack_binding == "latest" and self.pinned_versions is not None:
            raise ValueError("VAL-PROF-01: pack_binding=latest requires pinned_versions=null")
        if self.pack_binding == "pinned":
            missing = set(self.selected_jurisdictions) - set(self.pinned_versions or {})
            if missing:
                raise ValueError(
                    f"VAL-PROF-01: pinned_versions missing for {sorted(missing)}"
                )
        return self
