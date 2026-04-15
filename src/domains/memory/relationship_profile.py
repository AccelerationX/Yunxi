"""Relationship profile loading for Yunxi and Yuan."""

from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from pathlib import Path


class RelationshipProfileError(RuntimeError):
    """Raised when the relationship profile file is missing or malformed."""


@dataclass(frozen=True)
class UserRelationshipProfile:
    """Stable relationship facts about Yuan."""

    preferred_name: str
    facts: tuple[str, ...] = field(default_factory=tuple)
    interests: tuple[str, ...] = field(default_factory=tuple)
    dislikes: tuple[str, ...] = field(default_factory=tuple)
    expectations: tuple[str, ...] = field(default_factory=tuple)

    def build_prompt_lines(self) -> list[str]:
        """Render relationship facts as prompt lines."""
        lines = [f"\u8fdc\u7684\u79f0\u547c\uff1a{self.preferred_name}"]
        lines.extend([f"- \u8fdc\u7684\u4e8b\u5b9e\uff1a{fact}" for fact in self.facts])
        lines.extend([f"- \u8fdc\u7684\u957f\u671f\u5174\u8da3\uff1a{interest}" for interest in self.interests])
        lines.extend([f"- \u8fdc\u660e\u786e\u53cd\u611f\uff1a{dislike}" for dislike in self.dislikes])
        lines.extend([f"- \u76f8\u5904\u8981\u6c42\uff1a{expectation}" for expectation in self.expectations])
        return lines


def load_user_relationship_profile(path: Path | None = None) -> UserRelationshipProfile:
    """Load Yuan's relationship profile from a markdown file.

    Args:
        path: Optional explicit markdown file path. When omitted, the repository
            default `data/relationship/user_profile.md` is used.

    Raises:
        RelationshipProfileError: If the file cannot be read or required
            sections are empty.
    """
    profile_path = path or _default_profile_path()
    try:
        text = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RelationshipProfileError(f"Cannot read Yuan relationship profile: {profile_path}") from exc

    facts = _extract_bullets(text, "## basic_facts")
    interests = _extract_bullets(text, "## interests")
    dislikes = _extract_bullets(text, "## dislikes")
    expectations = _extract_bullets(text, "## expectations")
    preferred_name = _preferred_name_from_facts(facts)

    if not preferred_name:
        raise RelationshipProfileError("Yuan relationship profile is missing preferred name")

    return UserRelationshipProfile(
        preferred_name=preferred_name,
        facts=tuple(facts),
        interests=tuple(interests),
        dislikes=tuple(dislikes),
        expectations=tuple(expectations),
    )


def _default_profile_path() -> Path:
    """Return the repository default relationship profile path."""
    return Path(__file__).resolve().parents[3] / "data" / "relationship" / "user_profile.md"


def _extract_bullets(text: str, heading: str) -> list[str]:
    """Extract markdown bullet lines under a second-level heading."""
    lines = text.splitlines()
    in_section = False
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section and stripped.startswith("- "):
            item = _decode_escaped_text(stripped[2:].strip())
            if item:
                values.append(item)
    if not values:
        raise RelationshipProfileError(f"Yuan relationship profile section is empty: {heading}")
    return values


def _decode_escaped_text(value: str) -> str:
    """Decode unicode escape bullets while leaving normal text untouched."""
    if "\\u" not in value:
        return value
    return codecs.decode(value, "unicode_escape")


def _preferred_name_from_facts(facts: list[str]) -> str:
    """Read the preferred name from basic fact bullets."""
    prefix = "\u79f0\u547c\uff1a"
    for fact in facts:
        if fact.startswith(prefix):
            return fact.removeprefix(prefix).strip()
    return ""
