"""The triage agent as a LangGraph state machine.

    START
      -> baseline        rule-based triage (always runs, cheap, never fails)
      -> llm_classify    LLM + Pydantic validation
      -> confident?  -- no / error --> student (fine-tuned local model)
      |  yes                              -> confident? -- no / missing --> use_rules
      |                                   |  yes
      |  <--------------------------------+
      -> guardrail       final severity = max(LLM, rules); flag injection
      -> END

Safety: the SOS alerts are already sent before this graph runs.
The graph can only ADD information (severity, summary); it can never block an alert,
and it can never lower severity below the rule-based baseline.
"""
import logging
import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import rules, student
from .llm import llm_triage
from .schema import TriageResult

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6
STUDENT_CONFIDENCE_THRESHOLD = 0.5


class TriageState(TypedDict, total=False):
    message: str
    category_hint: str
    baseline: TriageResult
    llm_result: Optional[TriageResult]
    student_floor: Optional[str]  # severity from an unsure fine-tuned model
    final: TriageResult
    errors: list
    latency_ms: dict


def baseline_node(state: TriageState) -> TriageState:
    return {"baseline": rules.rule_based_triage(state["message"], state["category_hint"]),
            "errors": [], "latency_ms": {}}


def llm_node(state: TriageState) -> TriageState:
    started = time.perf_counter()
    try:
        result = llm_triage(state["message"], state["category_hint"])
        errors = state["errors"]
    except Exception as exc:  # timeout, bad JSON, schema mismatch, no key...
        logger.warning("LLM triage failed, falling back to rules: %s", exc)
        result, errors = None, state["errors"] + [f"llm: {exc}"]
    latency = {**state["latency_ms"], "llm": round((time.perf_counter() - started) * 1000)}
    return {"llm_result": result, "errors": errors, "latency_ms": latency}


def route_after_llm(state: TriageState) -> str:
    result = state.get("llm_result")
    if result is None or result.confidence < CONFIDENCE_THRESHOLD:
        return "student"
    return "guardrail"


def student_node(state: TriageState) -> TriageState:
    """Fine-tuned local model: second opinion when the LLM failed or was unsure."""
    if not student.available():
        return {"llm_result": None}
    started = time.perf_counter()
    try:
        result = student.predict(state["message"])
    except Exception as exc:
        logger.warning("Fine-tuned triage model failed, using rules: %s", exc)
        return {"llm_result": None, "errors": state["errors"] + [f"student: {exc}"]}
    latency = {**state["latency_ms"], "student": round((time.perf_counter() - started) * 1000)}
    if result.confidence < STUDENT_CONFIDENCE_THRESHOLD:
        # unsure: don't trust its category, but keep its severity as a safety floor
        return {"llm_result": None, "latency_ms": latency, "student_floor": result.severity}
    return {"llm_result": result, "latency_ms": latency}


def route_after_student(state: TriageState) -> str:
    return "guardrail" if state.get("llm_result") is not None else "use_rules"


def use_rules_node(state: TriageState) -> TriageState:
    base = state["baseline"]
    floor = state.get("student_floor")
    if floor:  # an unsure model may still RAISE severity, never lower it
        base = base.model_copy(update={"severity": rules.max_severity(base.severity, floor)})
    return {"final": base}


def guardrail_node(state: TriageState) -> TriageState:
    llm, base = state["llm_result"], state["baseline"]
    # The rules act as a floor only when they actually recognised something.
    # Their "unknown -> high" default is for when the LLM is missing, not a veto on it.
    floor = base.severity if base.matched else "low"
    final = llm.model_copy(update={
        # AI may RAISE severity, never lower it below the rule-based evidence
        "severity": rules.max_severity(llm.severity, floor),
        # keep the user's own category choice if they picked one
        "category": state["category_hint"] if state["category_hint"] != "other"
                    else llm.category,
        "injection_suspected": llm.injection_suspected or base.injection_suspected,
    })
    return {"final": final}


def build_graph():
    graph = StateGraph(TriageState)
    graph.add_node("baseline", baseline_node)
    graph.add_node("llm_classify", llm_node)
    graph.add_node("student", student_node)
    graph.add_node("use_rules", use_rules_node)
    graph.add_node("guardrail", guardrail_node)

    graph.add_edge(START, "baseline")
    graph.add_edge("baseline", "llm_classify")
    graph.add_conditional_edges("llm_classify", route_after_llm,
                                {"student": "student", "guardrail": "guardrail"})
    graph.add_conditional_edges("student", route_after_student,
                                {"use_rules": "use_rules", "guardrail": "guardrail"})
    graph.add_edge("use_rules", END)
    graph.add_edge("guardrail", END)
    return graph.compile()


triage_graph = build_graph()


def run_triage(message: str, category_hint: str = "other") -> TriageState:
    return triage_graph.invoke({"message": message or "", "category_hint": category_hint})
