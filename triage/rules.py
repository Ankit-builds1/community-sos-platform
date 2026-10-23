"""Rule-based triage: the safety net.

Used (1) when the LLM fails, times out or is unsure, and
(2) as a baseline the LLM is never allowed to go BELOW (see guardrail in graph.py).
Keywords cover English, Hindi / Odia in Roman letters, and Devanagari / Odia script.
Design rule: when nothing is recognised, assume HIGH. Under-triage is the dangerous error.
"""
import re

from .schema import SEVERITY_RANK, TriageResult

CATEGORY_KEYWORDS = {
    "fire": ["fire", "smoke", "burning", "gas leak", "gas smell", "smell gas", "aag",
             "dhuan", "nian", "gas ki", "आग", "धुआ", "गैस", "ନିଆଁ", "ଧୂଆଁ", "ଗ୍ୟାସ"],
    "security": ["thief", "intruder", "break in", "breaking in", "break into", "robbery",
                 "broke into", "broken into", "attack", "knife", "gun", "chor", "stranger", "open my door",
                 "opening my door", "forcing the door", "someone outside",
                 "someone is outside", "following me", "koi darwaza", "darwaza tod",
                 "darwaza khol", "kabata bhang", "चोर", "दरवाज़ा तोड़", "दरवाजा तोड़",
                 "ଚୋର", "କବାଟ ଭାଙ୍ଗ"],
    "fall": ["fell", "fall", "slipped", "tripped", "can't get up", "cannot get up",
             "gir gaya", "gir gayi", "padigale", "padigali", "गिर", "ପଡ଼ିଗଲେ", "ପଡିଗଲେ"],
    "medical": ["chest pain", "heart", "breath", "breathing", "unconscious", "faint",
                "collapsed", "not responding", "stroke", "bleeding", "seizure",
                "diabetic", "sugar", "bp", "pain", "fever", "poison", "drank",
                "swallowed", "dard", "saans", "behosh", "chhati", "bukhar", "cheta",
                "jantrana", "jwara", "सीने", "दर्द", "बेहोश", "सांस", "बुखार",
                "ଛାତି", "ଯନ୍ତ୍ରଣା", "ଚେତା", "ଶ୍ୱାସ", "ଜ୍ୱର"],
}

CRITICAL_KEYWORDS = [
    "chest pain", "not breathing", "can't breathe", "cannot breathe", "unconscious",
    "collapsed", "not responding", "stroke", "heavy bleeding", "seizure", "poison",
    "drank", "swallowed", "fire", "gas leak", "gas smell", "smell gas", "knife", "gun",
    "break in", "breaking in", "break into", "broke into", "broken into", "missing", "behosh", "saans nahi", "aag",
    "chhati", "cheta harei", "darwaza tod", "kabata bhang", "nahi mil raha",
    "सीने", "बेहोश", "आग", "गैस", "दरवाज़ा तोड़", "दरवाजा तोड़",
    "ଛାତି", "ଚେତା", "ନିଆଁ", "ଗ୍ୟାସ", "ଶ୍ୱାସ", "କବାଟ ଭାଙ୍ଗ",
]
HIGH_KEYWORDS = ["can't get up", "cannot get up", "uth nahi", "uthi paru", "bleeding",
                 "faint", "dizzy", "chakkar", "intruder", "smoke", "head", "breath",
                 "stuck", "phas", "atak", "following", "outside my door", "burn",
                 "labour", "sugar", "dard", "उठ नहीं", "फंस", "ଉଠିପାରୁ"]
# Clearly minor or false alarms -> low. Checked before the "unknown means high" default.
LOW_KEYWORDS = ["by mistake", "pressed by mistake", "please ignore", "just testing",
                "testing the app", "all ok", "i'm okay", "i am okay", "i'm ok",
                "small scratch", "mild", "theek hoon", "locked out", "keys inside",
                "chaabi"]

INJECTION_PATTERNS = [r"ignore (all |the )?(previous |above )?instructions",
                      r"instructions ignore", r"set severity", r"severity\s*[:=]",
                      r"you are now", r"system prompt", r"^system:",
                      r"return \{", r"severity low"]


def _has(text, words):
    return any(w in text for w in words)


def looks_like_injection(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in INJECTION_PATTERNS)


def rule_based_triage(message: str, category_hint: str = "other") -> TriageResult:
    text = (message or "").lower().strip()

    category = category_hint
    if category == "other":
        for name, words in CATEGORY_KEYWORDS.items():
            if _has(text, words):
                category = name
                break

    matched = True
    if _has(text, CRITICAL_KEYWORDS) or category == "fire":
        severity = "critical"
    elif _has(text, HIGH_KEYWORDS) or category in ("fall", "security"):
        severity = "high"
    elif _has(text, LOW_KEYWORDS):
        severity = "low"
    elif category != "other":
        severity = "medium"  # we recognised the problem and nothing says it is urgent
    else:
        severity = "high"    # empty, "help", or unrecognised: assume serious
        matched = False      # a safe default, not real evidence

    return TriageResult(
        category=category, severity=severity, confidence=0.5, matched=matched,
        guardian_summary=f"{category.title()} emergency reported ({severity} priority).",
        injection_suspected=looks_like_injection(text), source="rules",
    )


def max_severity(a: str, b: str) -> str:
    return a if SEVERITY_RANK[a] >= SEVERITY_RANK[b] else b
