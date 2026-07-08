"""Prompt Loader ? loads, caches, and interpolates prompt templates."""

import os as _os
import json as _json
from functools import lru_cache
from typing import Optional

_PROMPT_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "prompts")


@lru_cache(maxsize=32)
def load(name: str) -> str:
    """Load a prompt template by name (e.g. 'compiler_system' -> prompts/compiler_system.txt)."""
    path = _os.path.join(_PROMPT_DIR, f"{name}.txt")
    if not _os.path.isfile(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


@lru_cache(maxsize=32)
def load_raw(name: str) -> str:
    """Load raw prompt without stripping ? for templates with significant whitespace."""
    path = _os.path.join(_PROMPT_DIR, f"{name}.txt")
    if not _os.path.isfile(path):
        raise FileNotFoundError(f"Prompt not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_template(name: str, **kwargs) -> str:
    """Load a prompt template and interpolate variables via str.format().

    Example:
        load_template("user_compile", PRD_TEXT="...", INDUSTRY="E-Commerce")
    """
    raw = load_raw(name)
    return raw.format(**kwargs)


def load_industries() -> dict:
    """Load the industry profiles from prompts/industries.json."""
    path = _os.path.join(_PROMPT_DIR, "industries.json")
    if not _os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return _json.load(f)


def detect_industry(prd_text: str) -> tuple[str, dict]:
    """Auto-detect which industry a PRD belongs to.

    Returns (industry_key, industry_profile).
    """
    industries = load_industries()
    if not industries:
        return ("general", {})

    text_lower = prd_text.lower()
    scores = {}

    for key, profile in industries.items():
        score = 0
        # English keywords
        for kw in profile.get("keywords", []):
            if kw.lower() in text_lower:
                score += 2
        # Chinese keywords
        for kw in profile.get("cn_keywords", []):
            if kw in prd_text:
                score += 2
        scores[key] = score

    # Return the industry with the highest score
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return (best, industries.get(best, {}))
    return ("general", industries.get("general", {}))


def build_industry_prompt(industry_key: str) -> str:
    """Build a concise industry context string for the prompt."""
    industries = load_industries()
    profile = industries.get(industry_key, industries.get("general", {}))
    if not profile:
        return "General business process"

    parts = [profile.get("name", "General")]
    roles = profile.get("typical_roles", [])
    if roles:
        parts.append(f"Typical roles: {', '.join(roles[:5])}")
    sla = profile.get("typical_sla", "")
    if sla:
        parts.append(f"SLA: {sla}")
    return ". ".join(parts)


def list_prompts() -> list[str]:
    """List all available prompt names."""
    if not _os.path.isdir(_PROMPT_DIR):
        return []
    return [
        _os.path.splitext(f)[0]
        for f in _os.listdir(_PROMPT_DIR)
        if f.endswith(".txt")
    ]


def resolve(name: str) -> str:
    """Resolve the full path to a prompt file."""
    return _os.path.join(_PROMPT_DIR, f"{name}.txt")
