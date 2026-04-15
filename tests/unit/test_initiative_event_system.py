"""Unit tests for the three-layer initiative event system."""

import json
import random
from datetime import datetime

from core.initiative.event_system import (
    InitiativeEventLayer,
    ThreeLayerInitiativeEventSystem,
    load_initiative_events,
)


def test_default_life_event_library_has_three_layers():
    events = load_initiative_events()
    layers = {event.layer for event in events}

    assert len(events) >= 100
    assert InitiativeEventLayer.INNER_LIFE in layers
    assert InitiativeEventLayer.SHARED_INTEREST in layers
    assert InitiativeEventLayer.MIXED in layers


def test_select_event_respects_time_rules_and_cooldown(tmp_path):
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "morning_1",
                    "layer": "inner_life",
                    "category": "morning",
                    "seed": "Yunxi wants to talk about the morning light.",
                    "time_rules": {"hours": [8, 12], "weekday": True},
                    "tags": ["morning"],
                    "cooldown_seconds": 3600,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "event_state.json"
    system = ThreeLayerInitiativeEventSystem(
        library_path=library_path,
        state_path=state_path,
        rng=random.Random(1),
    )

    unavailable = system.select_event(moment=datetime(2026, 4, 18, 9, 0))
    selected = system.select_event(moment=datetime(2026, 4, 15, 9, 0))
    blocked_by_cooldown = system.select_event(moment=datetime(2026, 4, 15, 9, 10))

    assert unavailable is None
    assert selected is not None
    assert selected.event_id == "morning_1"
    assert blocked_by_cooldown is None
    assert state_path.exists()


def test_state_persists_selected_event(tmp_path):
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "shared_1",
                    "layer": "shared_interest",
                    "category": "code",
                    "seed": "Yunxi wants to ask Yuan about his code.",
                    "tags": ["code"],
                    "cooldown_seconds": 3600,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "event_state.json"
    first = ThreeLayerInitiativeEventSystem(
        library_path=library_path,
        state_path=state_path,
        rng=random.Random(1),
    )

    selected = first.select_event(moment=datetime(2026, 4, 15, 10, 0))
    second = ThreeLayerInitiativeEventSystem(
        library_path=library_path,
        state_path=state_path,
        rng=random.Random(1),
    )

    assert selected is not None
    assert second.state.selected_count == 1
    assert second.state.active_event_ids == ["shared_1"]
    assert second.select_event(moment=datetime(2026, 4, 15, 10, 30)) is None


def test_prompt_context_marks_event_as_material_not_script(tmp_path):
    library_path = tmp_path / "events.json"
    library_path.write_text(
        json.dumps(
            [
                {
                    "id": "mixed_1",
                    "layer": "mixed",
                    "category": "care",
                    "seed": "Yunxi wants to check whether Yuan has eaten.",
                    "tags": ["care"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    system = ThreeLayerInitiativeEventSystem(library_path=library_path)

    event = system.select_event(moment=datetime(2026, 4, 15, 12, 0))
    context = system.build_prompt_context(event)

    assert "initiative_event" in context
    assert "Yunxi wants to check" in context
    assert "Do not copy it verbatim" in context
