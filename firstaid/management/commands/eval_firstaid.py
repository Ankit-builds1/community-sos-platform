"""Evaluate first-aid RAG retrieval and guardrails.

    python manage.py eval_firstaid                  # with query rewriting, 1 run
    python manage.py eval_firstaid --runs 3         # average + range over 3 runs
    python manage.py eval_firstaid --no-rewrite     # ablation: raw question only

In-scope questions:     hit@1, hit@3, MRR, answered (top score >= MIN_SCORE)
Out-of-scope questions: correctly says "no guide"
Dose / diagnosis:       correctly refused
Mirrors assistant.answer() retrieval logic; only the small rewrite LLM call is used.
"""
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from firstaid.assistant import MIN_SCORE, _is_blocked, rewrite_query
from firstaid.vectorstore import search

EVAL_FILE = Path(__file__).resolve().parents[2] / "eval" / "firstaid_eval.jsonl"
LANGS = ["en", "hinglish", "hi", "or", "or-roman"]


def retrieve(question, use_rewrite):
    """Same decision path as assistant.answer(is_sos=False)."""
    if not use_rewrite:
        return question, search(question, k=3)
    query = rewrite_query(question)
    if query is None:  # rewriter says out of scope -> confirm with a raw search
        hits = search(question, k=3)
        return None, (hits if hits[0]["score"] >= MIN_SCORE else [])
    return query, search(query, k=3)


class Command(BaseCommand):
    help = "Measure RAG retrieval accuracy (hit@1, hit@3, MRR) and guardrails."

    def add_arguments(self, parser):
        parser.add_argument("--no-rewrite", action="store_true")
        parser.add_argument("--runs", type=int, default=1)
        # ~600 tokens per rewrite; free tier allows 8,000 tokens/min -> keep <= 12 calls/min
        parser.add_argument("--sleep", type=float, default=5.0)

    def handle(self, *args, no_rewrite, runs, sleep, **options):
        cases = [json.loads(l) for l in EVAL_FILE.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        all_runs = []
        for run in range(1, runs + 1):
            self.stdout.write(self.style.SUCCESS(f"\n--- Run {run}/{runs} ---"))
            all_runs.append(self.one_run(cases, not no_rewrite, sleep))

        mode = "raw question" if no_rewrite else "with query rewriting"
        self.stdout.write(self.style.SUCCESS(
            f"\n===== First-aid RAG eval ({mode}, {runs} run(s)) ====="))
        for key, label in [("hit1", "Hit@1"), ("hit3", "Hit@3"), ("mrr", "MRR"),
                           ("answered", f"Answered (>= {MIN_SCORE})"),
                           ("oos", "Out-of-scope -> no guide"),
                           ("refuse", "Dose/diagnosis refused")] + \
                          [(f"hit1_{l}", f"  Hit@1 {l}") for l in LANGS]:
            values = [r[key] for r in all_runs if r.get(key) is not None]
            if not values:
                continue
            mean = sum(values) / len(values)
            spread = f"  (range {min(values):.3f}-{max(values):.3f})" if runs > 1 else ""
            shown = f"{mean:.3f}" if key == "mrr" else f"{mean * 100:.1f}%"
            self.stdout.write(f"{label:26}: {shown}{spread}")

    def one_run(self, cases, use_rewrite, sleep):
        in_scope, oos, refuse = [], [], []
        for case in cases:
            q, gold = case["question"], case["gold"]
            if gold == "REFUSE":
                refuse.append(_is_blocked(q))
                continue

            query, hits = retrieve(q, use_rewrite)
            if use_rewrite:
                time.sleep(sleep)
            ids = [h["id"] for h in hits]
            top = hits[0]["score"] if hits else 0.0

            if gold is None:
                ok = top < MIN_SCORE
                oos.append(ok)
                if not ok:
                    self.stdout.write(f"-- out-of-scope answered: {q}  (top {top:.2f})")
                continue

            rank = ids.index(gold) + 1 if gold in ids else None
            row = {"hit1": rank == 1, "hit3": rank is not None, "rr": 1 / rank if rank else 0.0,
                   "answered": top >= MIN_SCORE, "lang": case["lang"]}
            in_scope.append(row)
            if not (row["hit1"] and row["answered"]):
                self.stdout.write(f"-- [{case['lang']:9}] {q}\n      query: {query}  ->  "
                                  f"{ids[0] if ids else 'NO GUIDE'} ({top:.2f}), gold {gold}")

        mean = lambda xs: sum(xs) / len(xs) if xs else None
        result = {"hit1": mean([r["hit1"] for r in in_scope]),
                  "hit3": mean([r["hit3"] for r in in_scope]),
                  "mrr": mean([r["rr"] for r in in_scope]),
                  "answered": mean([r["answered"] for r in in_scope]),
                  "oos": mean(oos), "refuse": mean(refuse)}
        for lang in LANGS:
            result[f"hit1_{lang}"] = mean([r["hit1"] for r in in_scope if r["lang"] == lang])
        return result
