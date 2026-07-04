"""AI Fix generation via the Claude API (System 6, step 2 of BR-FIX-01).

Uses the official Anthropic SDK with claude-opus-4-8 and adaptive thinking.
Structured output (json_schema) guarantees a parseable Fix object. When no
credentials are available (ANTHROPIC_API_KEY / auth profile), `available` is
False and the caller falls back to the template guidance — never a crash.

Every generated fix is labeled per BR-FIX-02 (developer review required) and
is a suggestion only — no Auto-PR (v1.0 §4.6.2).
"""
from __future__ import annotations

import json
from typing import Optional

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string",
                 "enum": ["code_patch", "config_change", "content_change",
                          "manual_guidance"]},
        "explanation": {"type": "string",
                        "description": "لماذا هذا عيب، لمن يضر، وكيف يصلحه المطوّر"},
        "diff": {"type": ["string", "null"],
                 "description": "patch مقترح إن أمكن، وإلا null"},
    },
    "required": ["type", "explanation", "diff"],
    "additionalProperties": False,
}


def build_prompt(rule_title: str, rule_description: str, severity: str,
                 selector: str, snippet: str, stack_hint: Optional[str]) -> str:
    stack_line = f"المنصة/الثيم: {stack_hint}\n" if stack_hint else ""
    return (
        "أنت خبير وصولية ويب (WCAG/EN 301 549). اقترح إصلاحاً لعيب واحد.\n"
        f"القاعدة: {rule_title} — {rule_description}\n"
        f"الشدة: {severity}\n{stack_line}"
        f"الموقع (selector): {selector}\n"
        f"المقتطف:\n{snippet}\n\n"
        "أعد إصلاحاً عملياً محدداً بهذا الموقع، مع شرح موجز بالعربية لمن يضر "
        "العيب ولماذا يعمل الإصلاح. إن أمكن diff دقيق فأعطه، وإلا إرشاداً يدوياً."
    )


class ClaudeFixGenerator:
    MODEL = "claude-opus-4-8"

    def __init__(self) -> None:
        self._client = None
        try:
            import anthropic
            client = anthropic.Anthropic()
            # credentials resolve from env/profile; a client with none will
            # fail at request time — treat missing key env as unavailable
            # only if the SDK itself cannot resolve anything.
            self._client = client
        except Exception:
            self._client = None

    @property
    def available(self) -> bool:
        import os
        return self._client is not None and bool(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )

    def generate(self, *, rule_title: str, rule_description: str,
                 severity: str, selector: str, snippet: str,
                 stack_hint: Optional[str] = None) -> Optional[dict]:
        if not self.available:
            return None
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema",
                                          "schema": FIX_SCHEMA}},
                messages=[{"role": "user", "content": build_prompt(
                    rule_title, rule_description, severity,
                    selector, snippet, stack_hint)}],
            )
            if response.stop_reason == "refusal":
                return None
            text = next(
                (block.text for block in response.content if block.type == "text"),
                None)
            return json.loads(text) if text else None
        except Exception:
            return None  # graceful degradation to template guidance
