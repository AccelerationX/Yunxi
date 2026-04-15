"""Structured persona profile support for Yunxi."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


class PersonaProfileError(RuntimeError):
    """Raised when a persona profile file is missing or malformed."""


@dataclass(frozen=True)
class YunxiPersonaProfile:
    """Structured persona facts used by prompt construction."""

    name: str
    identity: str
    relationship_role: str
    residence: str
    traits: tuple[str, ...] = field(default_factory=tuple)
    speech_style: tuple[str, ...] = field(default_factory=tuple)
    boundaries: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tones: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "YunxiPersonaProfile":
        """Build a validated profile from decoded JSON data.

        Raises:
            PersonaProfileError: If required fields are missing or invalid.
        """
        return cls(
            name=_required_text(data, "name"),
            identity=_required_text(data, "identity"),
            relationship_role=_required_text(data, "relationship_role"),
            residence=_required_text(data, "residence"),
            traits=_string_tuple(data, "traits"),
            speech_style=_string_tuple(data, "speech_style"),
            boundaries=_string_tuple(data, "boundaries"),
            forbidden_tones=_string_tuple(data, "forbidden_tones"),
        )

    def build_identity_lines(self) -> list[str]:
        """Render identity facts as prompt lines."""
        lines = [
            f"\u4f60\u662f{self.name}\uff0c{self.identity}",
            f"\u4f60\u548c\u8fdc\u7684\u5173\u7cfb\uff1a{self.relationship_role}",
            f"\u4f60\u7684\u5e38\u9a7b\u4f4d\u7f6e\uff1a{self.residence}\u3002",
        ]
        lines.extend([f"- \u6027\u683c\u5e95\u8272\uff1a{trait}" for trait in self.traits])
        return lines

    def build_expression_lines(self) -> list[str]:
        """Render speech and boundary guidance as prompt lines."""
        lines: list[str] = []
        lines.extend([f"- \u8bf4\u8bdd\u65b9\u5f0f\uff1a{style}" for style in self.speech_style])
        lines.extend([f"- \u8fb9\u754c\uff1a{boundary}" for boundary in self.boundaries])
        lines.extend([f"- \u907f\u514d\uff1a{tone}" for tone in self.forbidden_tones])
        return lines


def load_persona_profile(path: Path | None = None) -> YunxiPersonaProfile:
    """Load Yunxi's persona profile from disk.

    Args:
        path: Optional explicit JSON file path. When omitted, the repository
            default `data/persona/yunxi_profile.json` is used.

    Raises:
        PersonaProfileError: If the file cannot be read or does not match the
            expected schema.
    """
    profile_path = path or _default_profile_path()
    try:
        raw = profile_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PersonaProfileError(f"Cannot read Yunxi persona profile: {profile_path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PersonaProfileError(f"Invalid Yunxi persona JSON: {profile_path}") from exc

    if not isinstance(data, dict):
        raise PersonaProfileError(f"Yunxi persona root must be an object: {profile_path}")

    return YunxiPersonaProfile.from_mapping(data)


def _default_profile_path() -> Path:
    """Return the repository default persona profile path."""
    return Path(__file__).resolve().parents[3] / "data" / "persona" / "yunxi_profile.json"


def _required_text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PersonaProfileError(f"Yunxi persona profile field is missing or invalid: {key}")
    return value.strip()


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PersonaProfileError(f"Yunxi persona profile field must be a string list: {key}")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PersonaProfileError(f"Yunxi persona profile field contains invalid item: {key}")
        items.append(item.strip())
    return tuple(items)
