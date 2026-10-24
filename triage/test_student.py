"""Routing tests for the fine-tuned student model (uses a fake model, no files needed)."""
from unittest import mock

import numpy as np
from django.test import SimpleTestCase

from triage import student
from triage.graph import run_triage
from triage.schema import TriageResult

LLM_DOWN = mock.patch("triage.graph.llm_triage", side_effect=RuntimeError("groq down"))


def fake(category="medical", severity="high", confidence=0.9):
    return TriageResult(category=category, severity=severity, confidence=confidence,
                        guardian_summary="x", source="model", model="fine-tuned test")


class StudentRoutingTests(SimpleTestCase):

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=True)
    @mock.patch("triage.student.predict", return_value=fake("medical", "high"))
    def test_llm_down_uses_fine_tuned_model(self, *_):
        final = run_triage("my mother feels very dizzy and weak")["final"]
        self.assertEqual(final.source, "model")
        self.assertEqual(final.category, "medical")

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=True)
    @mock.patch("triage.student.predict", return_value=fake("fire", "medium"))
    def test_rules_floor_still_applies_to_the_model(self, *_):
        # "gas leak" is a rules keyword for critical: the model may not go below it
        final = run_triage("there is a gas leak smell in the kitchen")["final"]
        self.assertEqual(final.severity, "critical")

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=True)
    @mock.patch("triage.student.predict", return_value=fake(confidence=0.3))
    def test_unsure_model_falls_back_to_rules(self, *_):
        self.assertEqual(run_triage("help")["final"].source, "rules")

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=True)
    @mock.patch("triage.student.predict",
                return_value=fake("medical", "critical", confidence=0.3))
    def test_unsure_model_can_still_raise_severity(self, *_):
        # rules alone would not say critical here; the unsure model's severity is a floor
        final = run_triage("bete ne kuch pee liya")["final"]
        self.assertEqual(final.source, "rules")
        self.assertEqual(final.severity, "critical")

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=False)
    def test_no_model_files_falls_back_to_rules(self, *_):
        self.assertEqual(run_triage("help")["final"].source, "rules")

    @LLM_DOWN
    @mock.patch("triage.student.available", return_value=True)
    @mock.patch("triage.student.predict", side_effect=ValueError("corrupt model"))
    def test_model_crash_never_breaks_triage(self, *_):
        self.assertEqual(run_triage("help")["final"].source, "rules")


class SafeSeverityTests(SimpleTestCase):

    def test_picks_more_serious_level_when_mass_is_close(self):
        # argmax says "high" (0.45) but P(critical) = 0.40 >= tau 0.35 -> critical
        self.assertEqual(student.safe_severity(np.array([0.05, 0.10, 0.45, 0.40]), 0.35), 3)

    def test_clear_low_stays_low(self):
        self.assertEqual(student.safe_severity(np.array([0.90, 0.06, 0.03, 0.01]), 0.35), 0)
