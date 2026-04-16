"""Tests for sanitized daily-mode reaction library guidance."""

from core.persona.reaction_library import load_reaction_library


def test_load_default_reaction_library():
    library = load_reaction_library()

    assert library.get("comfort") is not None
    assert library.get("intimacy_sex") is None


def test_reaction_library_matches_companion_need():
    library = load_reaction_library()

    matches = library.match("我今天有点累，只想你陪我一下", current_emotion="担心")

    assert matches
    assert matches[0].reaction.id == "comfort"


def test_default_reaction_library_has_no_explicit_adult_material():
    library = load_reaction_library()
    forbidden = ("性器", "乳头", "湿", "插入", "喘", "成人化内容")

    text = "\n".join(
        [
            reaction.id
            + reaction.name
            + reaction.style
            + "".join(reaction.triggers)
            + "".join(reaction.examples)
            for reaction in library.reactions
        ]
    )

    assert not any(token in text for token in forbidden)
