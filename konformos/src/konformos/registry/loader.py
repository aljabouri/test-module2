"""Loads the Rules-as-Data seed catalog (docs/rules-catalog) into typed models.

Loading IS validation: every document passes through the Pydantic models,
so a malformed catalog fails loudly at startup (Tech Spec v1.0 §8.1
Schema-as-Code) — and dangling rule_refs are rejected (INV-RP-04).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from konformos.schemas import Rule, RuleMapping, RulePack

CATALOG_ENV_VAR = "KONFORMOS_CATALOG_DIR"


def find_catalog_dir(start: Path | None = None) -> Path:
    """Resolve the catalog directory: env var first, then walk up from here."""
    env = os.environ.get(CATALOG_ENV_VAR)
    if env:
        path = Path(env)
        if not path.is_dir():
            raise FileNotFoundError(f"{CATALOG_ENV_VAR} points to missing dir: {path}")
        return path
    current = (start or Path(__file__)).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "docs" / "rules-catalog"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("docs/rules-catalog not found; set KONFORMOS_CATALOG_DIR")


@dataclass
class Catalog:
    rules: dict[str, Rule] = field(default_factory=dict)
    packs: list[RulePack] = field(default_factory=list)
    mappings: dict[str, RuleMapping] = field(default_factory=dict)


def load_catalog(catalog_dir: Path | None = None) -> Catalog:
    base = catalog_dir or find_catalog_dir()
    catalog = Catalog()

    rules_doc = json.loads((base / "seed" / "rules.wcag22.json").read_text(encoding="utf-8"))
    for raw in rules_doc["rules"]:
        rule = Rule.model_validate(raw)
        if rule.code in catalog.rules:
            raise ValueError(f"duplicate rule code in catalog: {rule.code} (INV-RP-05)")
        catalog.rules[rule.code] = rule

    for path in sorted((base / "seed" / "rule-packs").glob("*.json")):
        pack = RulePack.model_validate_json(path.read_text(encoding="utf-8"))
        dangling = [r.rule_code for r in pack.rule_refs if r.rule_code not in catalog.rules]
        if dangling:
            raise ValueError(f"{pack.version}: dangling rule_refs {dangling} (INV-RP-04)")
        catalog.packs.append(pack)

    maps_doc = json.loads((base / "seed" / "rule-mappings.json").read_text(encoding="utf-8"))
    for raw in maps_doc["mappings"]:
        mapping = RuleMapping.model_validate(raw)
        if mapping.rule_code not in catalog.rules:
            raise ValueError(f"mapping references unknown rule {mapping.rule_code}")
        catalog.mappings[mapping.rule_code] = mapping

    return catalog
