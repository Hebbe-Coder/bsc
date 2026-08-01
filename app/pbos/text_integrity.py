"""Small integrity checks for legacy PBOS text artifacts."""

from __future__ import annotations

from typing import Any


def is_unreadable_legacy_text(value: Any) -> bool:
    """Identify damaged legacy text without rewriting its audit record."""
    text = str(value or "").strip()
    if not text:
        return False
    if "\ufffd" in text:
        return True
    characters = [character for character in text if not character.isspace()]
    question_count = sum(character == "?" for character in characters)
    return bool(
        question_count >= 3
        and characters
        and ("???" in text or question_count / len(characters) >= 0.25)
    )
