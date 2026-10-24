"""Structured output of the triage agent. The LLM must return exactly this shape."""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["medical", "fall", "fire", "security", "other"]
Severity = Literal["critical", "high", "medium", "low"]

# higher number = more serious; used by the guardrail
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class TriageResult(BaseModel):
    category: Category
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    guardian_summary: str = Field(max_length=200,
                                  description="One calm sentence for the guardian.")
    injection_suspected: bool = False
    source: Literal["llm", "model", "rules"] = "llm"  # model = fine-tuned student
    # rules only: True if a keyword actually matched (vs. the "unknown -> high" default)
    matched: bool = False
    model: str = ""  # which LLM produced it (main or backup)
