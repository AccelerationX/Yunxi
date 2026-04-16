"""Reaction library support for daily-mode expression guidance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


class ReactionLibraryError(RuntimeError):
    """Raised when a reaction library file is missing or malformed."""


@dataclass(frozen=True)
class Reaction:
    """One reusable reaction style entry."""

    id: str
    name: str
    triggers: tuple[str, ...]
    style: str
    examples: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "Reaction":
        """Build a validated reaction from decoded JSON data."""
        return cls(
            id=_required_text(data, "id"),
            name=_required_text(data, "name"),
            triggers=_string_tuple(data, "triggers"),
            style=_required_text(data, "style"),
            examples=_string_tuple(data, "examples"),
        )


@dataclass(frozen=True)
class ReactionMatch:
    """A scored reaction match for the current user input."""

    reaction: Reaction
    score: int
    matched_triggers: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReactionLibrary:
    """Structured reaction library used as prompt guidance, not templates."""

    reactions: tuple[Reaction, ...]

    def get(self, reaction_id: str) -> Reaction | None:
        """Return a reaction by id."""
        for reaction in self.reactions:
            if reaction.id == reaction_id:
                return reaction
        return None

    def match(
        self,
        user_input: str,
        current_emotion: str = "",
        limit: int = 2,
    ) -> list[ReactionMatch]:
        """Match user input and current emotion to reaction guidance."""
        normalized_input = user_input.casefold()
        candidates: list[ReactionMatch] = []
        for reaction in self.reactions:
            matched = tuple(
                trigger
                for trigger in reaction.triggers
                if trigger.casefold() in normalized_input
            )
            score = len(matched) * 10
            score += _emotion_bonus(reaction.id, current_emotion)
            if score > 0:
                candidates.append(
                    ReactionMatch(
                        reaction=reaction,
                        score=score,
                        matched_triggers=matched,
                    )
                )

        candidates.sort(
            key=lambda item: (
                item.score,
                len(item.matched_triggers),
                -self.reactions.index(item.reaction),
            ),
            reverse=True,
        )
        return candidates[: max(0, limit)]


def load_reaction_library(path: Path | None = None) -> ReactionLibrary:
    """Load the default sanitized reaction library."""
    library_path = path or _default_library_path()
    try:
        raw = library_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReactionLibraryError(f"Cannot read reaction library: {library_path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReactionLibraryError(f"Invalid reaction library JSON: {library_path}") from exc

    if not isinstance(data, list):
        raise ReactionLibraryError(f"Reaction library root must be a list: {library_path}")

    reactions = []
    for item in data:
        if not isinstance(item, dict):
            raise ReactionLibraryError("Reaction library item must be an object")
        reactions.append(Reaction.from_mapping(item))
    return ReactionLibrary(reactions=tuple(reactions))


def _default_library_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "persona" / "reaction_library.json"


def _emotion_bonus(reaction_id: str, emotion: str) -> int:
    emotion_map = {
        "开心": {"celebrate"},
        "委屈": {"repair", "comfort"},
        "想念": {"affection", "greeting"},
        "吃醋": {"jealousy"},
        "担心": {"comfort"},
    }
    return 4 if reaction_id in emotion_map.get(emotion, set()) else 0


def _required_text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReactionLibraryError(f"Reaction field is missing or invalid: {key}")
    return value.strip()


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReactionLibraryError(f"Reaction field must be a string list: {key}")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ReactionLibraryError(f"Reaction field contains invalid item: {key}")
        items.append(item.strip())
    return tuple(items)
