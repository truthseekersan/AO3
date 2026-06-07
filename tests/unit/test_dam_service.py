from __future__ import annotations

from app.application.dam_service import (
    _dam_has_dialogue,
    _dam_extract_all_quotes,
    _dam_match_snippet,
    _dam_extract_paragraphs,
    _dam_character_alias_map,
)
from app.domain.entities import CharacterProfile


def test_dam_has_dialogue() -> None:
    assert _dam_has_dialogue('He said, "Hello."') is True
    assert _dam_has_dialogue('He thought, *Hello.*', is_italics=True) is True
    assert _dam_has_dialogue('No quotes here') is False


def test_dam_extract_all_quotes() -> None:
    text = 'She said, "Wait." Then "Go."'
    assert _dam_extract_all_quotes(text) == ['Wait.', 'Go.']

    text_italics = 'She thought, *Wait.* Then *Go.*'
    assert _dam_extract_all_quotes(text_italics, is_italics=True) == ['*Wait.*', '*Go.*']


def test_dam_match_snippet() -> None:
    paragraph = 'She said, "Wait for me." Then she turned around.'
    # Exact snippet clean matching
    assert _dam_match_snippet('Wait for me', paragraph) == 'Wait for me.'
    # Snip too short
    assert _dam_match_snippet('W', paragraph) == ""
    # No match
    assert _dam_match_snippet('Go away', paragraph) == ""


def test_dam_extract_paragraphs() -> None:
    html = "<p>First paragraph.</p><blockquote>Second block.</blockquote>"
    paras = _dam_extract_paragraphs(html)
    assert len(paras) == 2
    assert paras[0]["text"] == "First paragraph."
    assert paras[1]["text"] == "Second block."


def test_dam_character_alias_map() -> None:
    char = CharacterProfile(
        id="char-1",
        fandom_key="f-1",
        name="John Watson",
        full_name="Dr. John Watson",
        tag_urls=["/tags/John%20Watson"],
    )
    alias_map = _dam_character_alias_map([char])
    assert "char-1" in alias_map
    assert "John Watson" in alias_map["char-1"]
    assert "Dr. John Watson" in alias_map["char-1"]
