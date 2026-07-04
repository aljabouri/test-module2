"""Rule-Pack resolution — Tech Spec v1.0 §8.7, Engineering Rules v1.1 BR-LEG-04,
BR-EVAL-05 (weight merging), EDGE-LEG-02 (frameworks on different WCAG versions).

resolve(profile, on_date, packs) → ResolvedRuleSet: which rules apply, with
which weight per jurisdiction and combined, against named pack versions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from konformos.schemas import ComplianceProfile, RulePack
from konformos.schemas.pack import Jurisdiction, is_effective


class PackNotFound(Exception):
    pass


class PackNotEffective(Exception):
    """ERR 422 pack_not_effective: pinned pack whose effective_from is in the future."""


def get_active_pack(packs: list[RulePack], jurisdiction: Jurisdiction, on_date: date) -> RulePack:
    """BR-LEG-04: newest ACTIVE pack whose effective_from <= on_date."""
    candidates = [
        p for p in packs
        if p.jurisdiction == jurisdiction and p.status == "active" and is_effective(p, on_date)
    ]
    if not candidates:
        raise PackNotFound(f"no active pack for {jurisdiction} effective on {on_date}")
    return max(candidates, key=lambda p: (p.effective_from, p.version))


def get_pack_by_version(packs: list[RulePack], version: str) -> RulePack:
    for pack in packs:
        if pack.version == version:
            return pack
    raise PackNotFound(f"pack {version} not found")


@dataclass
class ResolvedRule:
    rule_code: str
    weights: dict[Jurisdiction, int] = field(default_factory=dict)
    mandatory: dict[Jurisdiction, bool] = field(default_factory=dict)

    def combined_weight(self, combination_mode: str) -> int:
        # BR-EVAL-05: strictest = max across jurisdictions; union = sum
        # (each jurisdiction already capped at 10) — union punishes shared
        # defects harder. A rule present in one jurisdiction enters as-is.
        if combination_mode == "strictest":
            return max(self.weights.values())
        return sum(self.weights.values())

    @property
    def combined_mandatory(self) -> bool:
        # BR-EVAL-05: mandatory merges with OR
        return any(self.mandatory.values())


@dataclass
class ResolvedRuleSet:
    rules: dict[str, ResolvedRule]
    pack_versions: dict[Jurisdiction, str]
    combination_mode: str

    def jurisdiction_rules(self, jurisdiction: Jurisdiction) -> dict[str, int]:
        """The per-jurisdiction weight matrix ("which rule for which jurisdiction")."""
        return {
            code: rule.weights[jurisdiction]
            for code, rule in self.rules.items()
            if jurisdiction in rule.weights
        }


def canonical_rule(rule_code: str) -> str:
    """Canonical legal node for a rule (v1.0 §8.7). Codes are already unified
    on WCAG 2.2 numbering across frameworks (catalog decision #1), so this is
    the identity today; kept as the single extension point if a future
    framework introduces codes needing RuleMapping-based unification."""
    return rule_code


def resolve(
    profile: ComplianceProfile,
    on_date: date,
    packs: list[RulePack],
) -> ResolvedRuleSet:
    selected: dict[Jurisdiction, RulePack] = {}
    for jurisdiction in profile.selected_jurisdictions:
        if profile.pack_binding == "pinned":
            pack = get_pack_by_version(packs, profile.pinned_versions[jurisdiction])
            if not is_effective(pack, on_date):
                raise PackNotEffective(
                    f"{pack.version} not effective before {pack.effective_from}"
                )
        else:
            pack = get_active_pack(packs, jurisdiction, on_date)
        selected[jurisdiction] = pack

    rules: dict[str, ResolvedRule] = {}
    for jurisdiction, pack in selected.items():
        for ref in pack.rule_refs:
            node = canonical_rule(ref.rule_code)
            resolved = rules.setdefault(node, ResolvedRule(rule_code=node))
            resolved.weights[jurisdiction] = ref.weight
            resolved.mandatory[jurisdiction] = ref.mandatory

    return ResolvedRuleSet(
        rules=rules,
        pack_versions={j: p.version for j, p in selected.items()},
        combination_mode=profile.combination_mode,
    )
