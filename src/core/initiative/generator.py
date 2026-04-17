"""Proactive generation context builder.

The builder prepares prompt material for proactive messages. It never returns a
user-visible fallback sentence and never calls an LLM directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.cognition.initiative_engine import InitiativeDecision


class ProactiveGenerationContextBuilder:
    """Assemble decision, event, and expression material for proactive prompts."""

    def build(
        self,
        *,
        decision: "InitiativeDecision",
        event_context: str = "",
        expression_context: str = "",
    ) -> str:
        """Build LLM prompt material for one proactive generation."""
        parts = [
            "initiative_decision:",
            f"- intent: {decision.intent}",
            f"- urgency: {decision.urgency:.2f}",
            f"- reason: {decision.reason}",
            f"- expression_mode: {decision.expression_mode}",
        ]
        if event_context:
            parts.extend(["", "life_event_material:", event_context])
        if expression_context:
            parts.extend(["", expression_context])
        if decision.intent == "presence_murmur":
            parts.extend(
                [
                    "",
                    "presence_murmur_boundary:",
                    "- The final message must be one short sentence or phrase.",
                    "- It may be emotionally warm but can be content-free.",
                    "- Do not recommend articles, videos, links, searches, news, or newly published content.",
                    "- Do not ask whether Yuan is interested, and do not offer to send more material.",
                    "- Do not start a task, plan, checklist, or research thread.",
                ]
            )
        parts.extend(
            [
                "",
                "generation_boundary:",
                "- Final message must be generated naturally by the LLM.",
                "- Do not expose internal field names.",
                "- Do not turn this into a task plan unless Yuan asked for one.",
            ]
        )
        return "\n".join(parts)
