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
    # first-person chain-of-thought markers that leak from backends
    "i should",
    "i need to",
    "i have to",
    "i must",
    "i can",
    "i will",
    "i would",
    "i could",
    "i think",
    "i believe",
    "i suppose",
    "i guess",
    "let me",
    "wait,",
    "actually,",
    "looking at",
    "given the",
    "the instruction says",
    "output only your final message",
    "use the same language",
    "final response should be",
    "humanizer skill",
    "skill is loaded",
    "loaded. now",
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
    if len(text) > 420 and sum(word in lower for word in ("respond", "invoke", "skill", "context")) >= 2:
        return True
    return False


def _split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs, respecting bullet markers."""
    # Split on double newlines or bullet markers, keeping bullets as separators.
    parts = re.split(r"\s*•\s*|\n\n+", text)
    return [part.strip() for part in parts if part and part.strip()]


def _looks_like_reasoning(text: str) -> bool:
    """Heuristic for first-person reasoning leaked by CLI backends."""
    lower = text.lower().strip()
    # First person modal verbs at the start of a paragraph strongly indicate CoT.
    if re.match(
        r"^(i|let me|wait,|actually,|so,|okay,|ok,|well,|now,)\s+"
        r"(should|need|must|can|will|would|could|think|believe|guess|suppose|check|look|try)",
        lower,
    ):
        return True
    # Spanish first-person reasoning markers.
    if re.match(
        r"^(debo|tengo\s+que|necesito|debería|podría|puedo|voy\s+a|pienso|creo\s+que|supongo\s+que|espera,|en\s+realidad,|bueno,|ok,|ahora,)\s+",
        lower,
    ):
        return True
    # Explicit meta-commentary about skills, the prompt, or the user message.
    if re.search(
        r"\bskill\s+is\s+loaded\b|\bnow\s+i\s+need\s+to\s+respond\b|\bthe\s+instruction\s+says\b|\boutput\s+only\s+your\s+final\s+message\b|\bel\s+usuario\s+(saluda|pregunta|escribe|dice)\b|\brazonamiento\s+interno\b|\bno\s+mostrar\s+razonamiento\b|\bresponder\s+en\s+español\b",
        lower,
    ):
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

    # If the model explicitly marked a final response, use it.
    final_match = re.search(r"FINAL RESPONSE:\s*(.+?)(?=\n\n|\n•|$)", cleaned, re.IGNORECASE | re.DOTALL)
    if final_match:
        reply = final_match.group(1).strip()
        if reply:
            return {"text": reply, "reply": reply, "meta": {"skills": _extract_skills(reply)}, "trace": []}

    # Often the model wraps the final answer in quotes after long reasoning.
    # Prefer the last long quoted block that is not internal/reasoning.
    for match in reversed(list(re.finditer(r'[""]([^""]{40,})[""]', cleaned))):
        quoted = match.group(1).strip()
        stripped = _strip_skill_prefix(quoted)
        if stripped and not _is_internal(stripped) and not _looks_like_reasoning(stripped):
            # Ignore quotes that appear to repeat the user's question.
            prefix = cleaned[:match.start()].lower()
            if "user asked" in prefix[-200:] or "user said" in prefix[-200:] or "user wrote" in prefix[-200:]:
                continue
            return {"text": stripped, "reply": stripped, "meta": {"skills": _extract_skills(stripped)}, "trace": []}

    paragraphs = _split_paragraphs(cleaned)
    if not paragraphs:
        paragraphs = [cleaned]

    skills: List[str] = []
    reply_parts: List[str] = []
    trace: List[str] = []

    for part in paragraphs:
        part = part.strip()
        if not part:
            continue
        for skill in _extract_skills(part):
            if skill not in skills:
                skills.append(skill)
        stripped = _strip_skill_prefix(part)
        if not stripped:
            continue
        if _is_internal(stripped) or _looks_like_reasoning(stripped):
            trace.append(part[:800])
            continue
        reply_parts.append(stripped)

    reply = "\n\n".join(reply_parts).strip()
    if not reply:
        # Fallback 1: last paragraph that is not obviously reasoning.
        for candidate in reversed(paragraphs):
            stripped = _strip_skill_prefix(candidate.strip())
            if stripped and not _is_internal(stripped) and not _looks_like_reasoning(stripped):
                reply = stripped
                break
        # Fallback 2: very last paragraph, cleaned of session hints.
        if not reply:
            last = _strip_skill_prefix(paragraphs[-1].strip())
            reply = SESSION_RE.sub("", last).strip() if last else ""
        if not reply:
            reply = "I couldn't produce a clean reply. Check the agent logs for details."
            trace.extend(paragraphs)

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
