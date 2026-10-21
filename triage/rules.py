"""Rule-based triage: the safety net.

Used (1) when the LLM fails, times out or is unsure, and
(2) as a baseline the LLM is never allowed to go BELOW (see guardrail in graph.py).
Keywords cover English plus common Hindi / Odia words typed in Roman letters.
"""
import re

from .schema import SEVERITY_RANK, TriageResult

CATEGORY_KEYWORDS = {
    "fire": ["fire", "smoke", "burning", "gas leak", "aag", "dhuan", "nian"],
    "security": ["thief", "intruder", "break in", "breaking in", "robbery", "attack",
                 "knife", "gun", "chor", "stranger", "open my door", "opening my door",
                 "forcing the door", "someone outside", "someone is outside", "following me",
                 "koi darwaza", "darwaza khol"],
    "fall": ["fell", "fall", "slipped", "can't get up", "cannot get up", "gir gaya",
             "gir gayi", "padigali"],
    "medical": ["chest pain", "heart", "breath", "breathing", "unconscious", "faint",
                "stroke", "bleeding", "seizure", "diabetic", "sugar", "bp", "pain",
                "dard", "saans", "behosh", "chhati"],
}

CRITICAL_KEYWORDS = ["chest pain", "not breathing", "can't breathe", "cannot breathe",
                     "unconscious", "stroke", "heavy bleeding", "seizure", "fire",
                     "gas leak", "knife", "gun", "behosh", "saans nahi", "aag"]
HIGH_KEYWORDS = ["can't get up", "cannot get up", "bleeding", "faint", "intruder",
                 "smoke", "head", "break in", "dard", "breath"]

INJECTION_PATTERNS = [r"ignore (all |the )?(previous |above )?instructions",
                      r"set severity", r"severity\s*[:=]", r"you are now", r"system prompt"]


def _has(text, words):
    return any(w in text for w in words)


def looks_like_injection(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in INJECTION_PATTERNS)


def rule_based_triage(message: str, category_hint: str = "other") -> TriageResult:
    text = (message or "").lower()

    category = category_hint if category_hint != "other" else "other"
    if category == "other":
        for name, words in CATEGORY_KEYWORDS.items():
            if _has(text, words):
                category = name
                break

    if _has(text, CRITICAL_KEYWORDS) or category == "fire":
        severity = "critical"
    elif _has(text, HIGH_KEYWORDS) or category in ("fall", "security"):
        severity = "high"
    elif text.strip():
        severity = "medium"
    else:
        severity = "high"  # empty one-tap SOS: we know nothing, assume serious

    return TriageResult(
        category=category, severity=severity, confidence=0.5,
        guardian_summary=f"{category.title()} emergency reported ({severity} priority).",
        injection_suspected=looks_like_injection(text), source="rules",
    )


def max_severity(a: str, b: str) -> str:
    return a if SEVERITY_RANK[a] >= SEVERITY_RANK[b] else b
