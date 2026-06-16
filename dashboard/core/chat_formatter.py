"""Format raw AI backend output into structured chat payloads for the dashboard."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from core.pm_analysis import strip_ansi

SESSION_RE = re.compile(r"To resume this session:\s*kimi\s+-r\s+\S+.*", re.IGNORECASE | re.DOTALL)
SKILL_PREFIX_RE = re.compile(
    r"^(?:Using\s+)?(?:`[^`]+`(?:\s+and\s+`[^`]+`)*\s+skills?\.?\s*)",
    re.IGNORECASE,
)

INTERNAL_MARKERS = (
    "the user",
    "system reminder",
    "need respond",
    "we should",
    "we must",
    "we can use",
    "we need to",
    "we have to",
    "let's invoke",
    "since the user",
    "invoke the skill",
    "skill tool",
    "skills loaded",
    "maybe also",
    "however per",
    "per superpowers",
    "now respond",
    "now i need",
    "could say",
    "maybe answer",
    "being thorough",
    "drwxr",
    "total 8",
    "to resume this session",
    "context says",
    "context indicates",
    "if both produce",
    "also mention",
    "but if we",
    "i think answer",
    "need to decide",
    "must follow skill",
    "must invoke",
    "bash ls",
)


def _split_bullets(text: str) -> List[str]:
    parts = re.split(r"\s*•\s*", text)
    return [part.strip() for part in parts if part and part.strip()]


def _extract_skills(text: str) -> List[str]:
    if not re.search(r"skills?", text, re.IGNORECASE):
        return []
    seen: List[str] = []
    for match in re.finditer(r"`([^`]+)`", text):
        skill = match.group(1).strip()
        if skill and skill not in seen:
            seen.append(skill)
    return seen


def _strip_skill_prefix(text: str) -> str:
    return SKILL_PREFIX_RE.sub("", text).strip()


def _is_internal(text: str) -> bool:
    if not text:
        return True
    lower = text.lower()
    if any(marker in lower for marker in INTERNAL_MARKERS):
        return True
    if len(text) > 420 and any(word in lower for word in ("respond", "invoke", "skill", "context")):
        return True
    return False


def format_chat_response(raw: str) -> Dict[str, Any]:
    """Turn noisy CLI output into a user-facing reply plus optional trace metadata."""
    if not raw or not raw.strip():
        return {"text": "", "reply": "", "meta": {}, "trace": []}

    cleaned = strip_ansi(raw).strip()
    session_hint = ""
    session_match = SESSION_RE.search(cleaned)
    if session_match:
        session_hint = session_match.group(0).replace("To resume this session:", "").strip()
    cleaned = SESSION_RE.sub("", cleaned).strip()

    bullets = _split_bullets(cleaned)
    if not bullets:
        bullets = [cleaned]

    skills: List[str] = []
    reply_parts: List[str] = []
    trace: List[str] = []

    for part in bullets:
        part = part.strip()
        if not part:
            continue
        for skill in _extract_skills(part):
            if skill not in skills:
                skills.append(skill)
        stripped = _strip_skill_prefix(part)
        if not stripped:
            continue
        if _is_internal(stripped):
            trace.append(part[:600])
            continue
        reply_parts.append(stripped)

    reply = "\n\n".join(reply_parts).strip()
    if not reply:
        fallback = _strip_skill_prefix(bullets[0])
        fallback = SESSION_RE.sub("", fallback).strip()
        if fallback and not _is_internal(fallback):
            reply = fallback
        else:
            reply = "I couldn't produce a clean reply. Check the agent logs for details."
            trace.extend(bullets)

    meta: Dict[str, Any] = {}
    if skills:
        meta["skills"] = skills
    if session_hint:
        meta["sessionHint"] = session_hint

    return {
        "text": reply,
        "reply": reply,
        "meta": meta,
        "trace": trace,
    }
