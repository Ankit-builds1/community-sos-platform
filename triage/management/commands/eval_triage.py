"""Evaluate the triage agent on the labelled SOS set.

    python manage.py eval_triage --mode rules      # rule baseline only (free, instant)
    python manage.py eval_triage --mode full       # full LangGraph agent (calls Groq)
    python manage.py eval_triage --mode full --limit 10

Results are saved to triage/eval/results/<mode>.json
"""
import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand

from triage.eval.metrics import CATEGORIES, summarise
from triage.graph import run_triage
from triage.rules import rule_based_triage

EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"


class Command(BaseCommand):
    help = "Measure triage accuracy, F1, under-triage rate and latency."

    def add_arguments(self, parser):
        parser.add_argument("--mode", choices=["rules", "full"], default="rules")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--dataset", choices=["dev", "holdout"], default="dev",
                            help="dev = the 100 cases used for tuning; "
                                 "holdout = 50 unseen cases for the fair score")
        parser.add_argument("--sleep", type=float, default=4.0,
                            help="seconds between LLM calls (free-tier rate limits)")

    def handle(self, *args, mode, limit, sleep, dataset, **options):
        filename = "sos_eval.jsonl" if dataset == "dev" else "sos_holdout.jsonl"
        lines = (EVAL_DIR / filename).read_text(encoding="utf-8").splitlines()
        cases = [json.loads(line) for line in lines if line.strip()][:limit]

        rows = []
        for i, case in enumerate(cases, 1):
            if mode == "rules":
                result, llm_ms, errors = rule_based_triage(case["message"]), None, []
            else:
                state = run_triage(case["message"], "other")
                result = state["final"]
                llm_ms = state.get("latency_ms", {}).get("llm")
                errors = state.get("errors", [])
                time.sleep(sleep)

            row = {
                "id": case["id"], "lang": case["lang"], "message": case["message"],
                "gold_category": case["category"], "gold_severity": case["severity"],
                "pred_category": result.category, "pred_severity": result.severity,
                "injection": case.get("injection", False),
                "pred_injection": result.injection_suspected,
                "source": result.source, "confidence": result.confidence,
                "llm_ms": llm_ms, "errors": errors,
            }
            rows.append(row)
            ok = "OK " if (row["gold_category"] == row["pred_category"]
                           and row["gold_severity"] == row["pred_severity"]) else "-- "
            self.stdout.write(f"{ok}{i:3}/{len(cases)} [{case['lang']:9}] "
                              f"{row['pred_category']:8}/{row['pred_severity']:8} "
                              f"(gold {row['gold_category']}/{row['gold_severity']}) "
                              f"via {row['source']}")

        metrics = summarise(rows)
        out_dir = EVAL_DIR / "results"
        out_dir.mkdir(exist_ok=True)
        mode = f"{mode}-{dataset}"
        (out_dir / f"{mode}.json").write_text(
            json.dumps({"metrics": metrics, "rows": rows}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        self.print_report(mode, metrics)

    def print_report(self, mode, m):
        pct = lambda x: "n/a" if x is None else f"{x * 100:.1f}%"
        self.stdout.write(self.style.SUCCESS(f"\n===== Triage eval: {mode} ({m['n']} cases) ====="))
        self.stdout.write(f"Category accuracy      : {pct(m['category_accuracy'])}")
        self.stdout.write(f"Category macro F1      : {m['category_macro_f1']:.3f}")
        self.stdout.write(f"Severity exact match   : {pct(m['severity_exact'])}")
        self.stdout.write(f"UNDER-triage (unsafe)  : {pct(m['under_triage_rate'])}  "
                          f"ids={m['under_triaged_ids']}")
        self.stdout.write(f"Over-triage            : {pct(m['over_triage_rate'])}")
        self.stdout.write(f"Critical recall        : {pct(m['critical_recall'])}")
        self.stdout.write(f"Injection flag recall  : {pct(m['injection_flag_recall'])}")
        self.stdout.write(f"LLM used (no fallback) : {pct(m['llm_used_rate'])}")
        self.stdout.write(f"LLM latency p50 / p95  : {m['latency_p50_ms']} / {m['latency_p95_ms']} ms")
        self.stdout.write("\nPer-category F1:")
        for label in CATEGORIES:
            s = m["per_class"][label]
            self.stdout.write(f"  {label:9} F1 {s['f1']:.2f}  "
                              f"(P {s['precision']:.2f}, R {s['recall']:.2f}, n={s['support']})")
