"""Tests for the first-aid RAG assistant. Search and LLM are mocked (offline, free)."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .assistant import answer
from .chunker import chunk_markdown, load_chunks

CHUNK = {"id": "choking#adult", "doc": "choking", "title": "Choking",
         "section": "Adult or child over 1 year", "score": 0.72,
         "text": "1. Encourage coughing.\n2. Give up to 5 back blows.\n3. Give abdominal thrusts."}


def llm_reply(content):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class ChunkerTests(SimpleTestCase):

    def test_splits_by_section_and_keeps_title(self):
        chunks = chunk_markdown("demo", "# Demo\n\n## First\nA\n\n## Second\nB")
        self.assertEqual([c.section for c in chunks], ["First", "Second"])
        self.assertEqual(chunks[0].title, "Demo")
        self.assertEqual(chunks[1].id, "demo#second")

    def test_knowledge_base_loads_one_chunk_per_guide(self):
        chunks = load_chunks()
        self.assertGreaterEqual(len(chunks), 14)
        cpr = next(c for c in chunks if c.doc == "cpr_not_breathing")
        self.assertIn("What to do", cpr.text)  # sections are kept inside the guide chunk


@override_settings(GROQ_API_KEY="test", GROQ_MODEL="test-model")
class AssistantTests(SimpleTestCase):

    def setUp(self):
        # query rewriting is tested separately; here it must never call the network
        patcher = patch("firstaid.assistant.rewrite_query", side_effect=lambda q: q)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("firstaid.assistant.search", return_value=[{
        **CHUNK, "text": "Warning signs:\n- Blue lips\n\nWhat to do:\n1. Call 108.\n2. Back blows."}])
    @patch("firstaid.assistant.Groq", side_effect=TimeoutError("down"))
    def test_extractive_fallback_prefers_what_to_do_steps(self, *_):
        self.assertEqual(answer("choking")["steps"], ["Call 108.", "Back blows."])

    def test_dose_question_is_refused_without_search(self):
        with patch("firstaid.assistant.search") as search:
            result = answer("How many mg of aspirin should I give?")
        self.assertEqual(result["status"], "refused")
        search.assert_not_called()

    @patch("firstaid.assistant.search", return_value=[{**CHUNK, "score": 0.1}])
    def test_irrelevant_question_gets_no_match_not_a_guess(self, _):
        result = answer("what is the cricket score")
        self.assertEqual(result["status"], "no_match")
        self.assertIn("108", result["emergency"])

    @patch("firstaid.assistant.Groq")
    @patch("firstaid.assistant.search", return_value=[CHUNK])
    def test_grounded_answer_with_sources(self, _, groq_cls):
        groq_cls.return_value.chat.completions.create.return_value = llm_reply(
            '{"steps": ["Encourage coughing", "Give 5 back blows"], "used_sources": [1]}')
        result = answer("my son is choking")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["sources"][0]["id"], "choking#adult")

    @patch("firstaid.assistant.Groq", side_effect=TimeoutError("down"))
    @patch("firstaid.assistant.search", return_value=[CHUNK])
    def test_llm_failure_returns_guide_text_directly(self, *_):
        result = answer("my son is choking")
        self.assertEqual(result["status"], "extractive")
        self.assertEqual(result["steps"][1], "Give up to 5 back blows.")


@override_settings(GROQ_API_KEY="test", GROQ_MODEL="main", GROQ_FALLBACK_MODEL="small")
class QueryRewriteTests(SimpleTestCase):

    @patch("firstaid.assistant.Groq")
    def test_hinglish_is_rewritten_to_english(self, groq_cls):
        from .assistant import rewrite_query
        groq_cls.return_value.chat.completions.create.return_value = llm_reply(
            '{"query": "father has chest pain"}')
        self.assertEqual(rewrite_query("papa ko chhati mein dard"), "father has chest pain")

    @patch("firstaid.assistant.Groq", side_effect=TimeoutError("down"))
    def test_rewrite_failure_falls_back_to_original_text(self, _):
        from .assistant import rewrite_query
        self.assertEqual(rewrite_query("papa ko chhati mein dard"), "papa ko chhati mein dard")

    @patch("firstaid.assistant.Groq")
    def test_out_of_scope_question_returns_none(self, groq_cls):
        from .assistant import rewrite_query
        groq_cls.return_value.chat.completions.create.return_value = llm_reply('{"query": ""}')
        self.assertIsNone(rewrite_query("Recommend a good restaurant nearby"))

    @patch("firstaid.assistant.search", return_value=[{**CHUNK, "score": 0.1}])
    @patch("firstaid.assistant.rewrite_query", return_value=None)
    def test_out_of_scope_confirmed_by_raw_search_says_no_guide(self, *_):
        result = answer("Recommend a good restaurant nearby")
        self.assertEqual(result["status"], "no_match")

    @patch("firstaid.assistant.Groq", side_effect=TimeoutError("down"))
    @patch("firstaid.assistant.search", return_value=[{**CHUNK, "score": 0.2}])
    @patch("firstaid.assistant.rewrite_query", return_value=None)
    def test_sos_incident_is_never_dropped_as_out_of_scope(self, *_):
        # even with a weak match, an SOS incident must still get guidance if any exists
        result = answer("kie jane ghara bhitaraku pasuchi", is_sos=True)
        self.assertEqual(result["status"], "no_match")  # 0.2 < MIN_SCORE: honest no-guide
        with patch("firstaid.assistant.search", return_value=[CHUNK]):
            result = answer("kie jane ghara bhitaraku pasuchi", is_sos=True)
        self.assertEqual(result["status"], "extractive")  # searched and answered
