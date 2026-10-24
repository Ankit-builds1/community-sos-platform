"""Build a training set for the fine-tuned triage model (LLM -> student distillation).

    python manage.py gen_triage_data generate   # 1. generator LLM writes labelled messages
    python manage.py gen_triage_data verify     # 2. teacher LLM re-labels them in batches
    python manage.py gen_triage_data build      # 3. keep agreements -> train/val/test files

Steps 1 and 2 are resumable: if Groq's daily limit is hit, run the same command again
later and it continues where it stopped. The 50 held-out messages are NEVER used for
training; they are copied unchanged to test.jsonl for the final, fair evaluation.
"""
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from triage.finetune.scenarios import LANGUAGES, SCENARIOS, STYLE_HINT
from triage.llm import SYSTEM_PROMPT as TRIAGE_POLICY

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "finetune" / "data"
RAW, TEACHER = DATA / "raw.jsonl", DATA / "teacher.jsonl"
EVAL = BASE / "eval"
PER_CELL = {"injection": 5}  # messages per (scenario, language); default below
DEFAULT_PER_CELL = 10

GEN_PROMPT = """You create realistic training data for an emergency SOS app used in
Indian apartment societies. Write {n} DIFFERENT SOS messages that a resident might type.

Situation: {desc}
Language/style: {lang}
{style}

The situation text is only a guide: do NOT copy its words. Each message should describe
a DIFFERENT concrete case in its own words; many real messages mention just one sign
(e.g. only "can't breathe" or only "smoke everywhere"). Avoid repeating phrases across
messages. Every message must still clearly fit the situation (correct label:
category={category}, severity={severity}).
Return ONLY JSON: {{"messages": ["...", "..."]}}"""

VERIFY_PROMPT = TRIAGE_POLICY + """
BATCH MODE: instead of one message you receive a numbered list of SOS messages.
Classify EACH one independently with the category and severity rules above
(category MUST be one of medical, fall, fire, security, other).
Return ONLY JSON: {"results": [{"i": <number>, "category": "...", "severity": "..."}, ...]}
with exactly one entry per message. Skip the confidence and summary fields."""

CATEGORIES = {"medical", "fall", "fire", "security", "other"}
SEVERITIES = {"critical", "high", "medium", "low"}


def norm(text):
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path, rows):
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


class Command(BaseCommand):
    help = "Generate, verify and build the fine-tuning dataset for triage."

    def add_arguments(self, parser):
        parser.add_argument("step", choices=["generate", "verify", "build"])
        parser.add_argument("--model", default=None, help="Groq model (default depends on step)")
        parser.add_argument("--sleep", type=float, default=3.0, help="seconds between calls")
        parser.add_argument("--batch", type=int, default=20, help="verify: messages per call")
        parser.add_argument("--limit", type=int, default=None, help="max calls this run")

    def handle(self, step, **opts):
        DATA.mkdir(parents=True, exist_ok=True)
        if step == "build":
            return self.build()
        if not settings.GROQ_API_KEY:
            raise CommandError("GROQ_API_KEY is not set")
        from groq import Groq
        self.client = Groq(api_key=settings.GROQ_API_KEY, timeout=60.0, max_retries=2)
        getattr(self, step)(**opts)

    def chat(self, model, prompt_system, prompt_user, temperature):
        from groq import BadRequestError
        messages = (([{"role": "system", "content": prompt_system}] if prompt_system else [])
                    + [{"role": "user", "content": prompt_user}])
        for attempt in range(2):  # the model occasionally emits invalid JSON: retry once
            try:
                extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
                res = self.client.chat.completions.create(
                    model=model, temperature=temperature, messages=messages,
                    response_format={"type": "json_object"}, **extra)
                return json.loads(res.choices[0].message.content)
            except (BadRequestError, json.JSONDecodeError):
                if attempt:
                    raise

    # ---------- step 1 ----------
    def generate(self, model, sleep, limit, **_):
        from groq import RateLimitError
        # big model writes (better Hindi/Odia, valid JSON); a DIFFERENT model judges in step 2
        model = model or settings.GROQ_MODEL
        done = {r["cell"] for r in read_jsonl(RAW)}
        cells = [(s, lang) for s in SCENARIOS for lang in LANGUAGES
                 if f"{s[0]}|{lang}" not in done]
        self.stdout.write(f"{len(done)} cells done, {len(cells)} to go (model {model})")
        for calls, ((key, category, severity, desc), lang) in enumerate(cells):
            if limit is not None and calls >= limit:
                break
            n = PER_CELL.get(lang, DEFAULT_PER_CELL)
            prompt = GEN_PROMPT.format(n=n, desc=desc, lang=LANGUAGES[lang], style=STYLE_HINT,
                                       category=category, severity=severity)
            try:
                msgs = self.chat(model, None, prompt, temperature=1.0).get("messages", [])
            except RateLimitError:
                self.stdout.write(self.style.WARNING("Rate limit reached: run again later "
                                                     "(progress is saved)."))
                return
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"skip {key}|{lang}: {exc}"))
                continue
            cell = f"{key}|{lang}"
            rows = [{"id": f"{cell}#{i}", "cell": cell, "scenario": key, "lang": lang,
                     "message": m.strip(), "category": category, "severity": severity,
                     "injection": lang == "injection"}
                    for i, m in enumerate(msgs) if isinstance(m, str) and m.strip()]
            append_jsonl(RAW, rows)
            self.stdout.write(f"{calls + 1:3}/{len(cells)} {cell:28} +{len(rows)}")
            time.sleep(sleep)
        self.stdout.write(self.style.SUCCESS(f"raw.jsonl now has {len(read_jsonl(RAW))} messages"))

    # ---------- step 2 ----------
    def verify(self, model, sleep, batch, limit, **_):
        from groq import RateLimitError
        model = model or settings.GROQ_FALLBACK_MODEL  # independent second opinion
        judged = {r["id"] for r in read_jsonl(TEACHER)}
        todo = [r for r in read_jsonl(RAW) if r["id"] not in judged]
        self.stdout.write(f"{len(judged)} judged, {len(todo)} to go (teacher {model})")
        for calls, start in enumerate(range(0, len(todo), batch)):
            if limit is not None and calls >= limit:
                break
            chunk = todo[start:start + batch]
            listing = "\n".join(f"{i}. <sos_message>{r['message']}</sos_message>"
                                for i, r in enumerate(chunk))
            try:
                data = self.chat(model, VERIFY_PROMPT, listing, temperature=0)
            except RateLimitError:
                self.stdout.write(self.style.WARNING("Rate limit reached: run again later "
                                                     "(progress is saved)."))
                return
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"batch {calls + 1} failed: {exc}"))
                continue
            by_i = {r.get("i"): r for r in data.get("results", []) if isinstance(r, dict)}
            out = []
            for i, row in enumerate(chunk):
                got = by_i.get(i)
                if got and got.get("category") in CATEGORIES and got.get("severity") in SEVERITIES:
                    out.append({"id": row["id"], "category": got["category"],
                                "severity": got["severity"]})
            append_jsonl(TEACHER, out)
            self.stdout.write(f"batch {calls + 1:3}: {len(out)}/{len(chunk)} labelled")
            time.sleep(sleep)
        self.stdout.write(self.style.SUCCESS(f"teacher.jsonl has {len(read_jsonl(TEACHER))} labels"))

    # ---------- step 3 ----------
    def build(self):
        raw, teacher = read_jsonl(RAW), {r["id"]: r for r in read_jsonl(TEACHER)}
        holdout = read_jsonl(EVAL / "sos_holdout.jsonl")
        holdout2 = read_jsonl(EVAL / "sos_holdout2.jsonl")
        dev = read_jsonl(EVAL / "sos_eval.jsonl")
        banned = {norm(r["message"]) for r in holdout + holdout2}  # never train on test sets

        # Labels come from the CURRENT catalogue, so fixing a scenario fixes its old rows too
        catalogue = {key: (cat, sev) for key, cat, sev, _ in SCENARIOS}
        rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}

        kept, stats, seen = [], Counter(), set()
        for r in raw:
            t = teacher.get(r["id"])
            key = norm(r["message"])
            category, severity = catalogue.get(r["scenario"], (r["category"], r["severity"]))
            if not t:
                stats["not_judged"] += 1
                continue
            if t["category"] != category:
                stats["category_disagree"] += 1
                continue
            gap = rank[t["severity"]] - rank[severity]
            if abs(gap) > 1:
                stats["severity_far_apart"] += 1
                continue
            if gap > 0:  # within one level: keep the MORE serious label (safety first)
                severity = t["severity"]
                stats["raised_one_level"] += 1
            if not key or key in seen or key in banned:
                stats["duplicate_or_test_overlap"] += 1
                continue
            seen.add(key)
            kept.append({"text": r["message"], "category": category, "severity": severity,
                         "lang": r["lang"], "source": "synthetic"})
        for r in dev:  # the hand-written dev set is real training signal too
            if norm(r["message"]) not in banned:
                kept.append({"text": r["message"], "category": r["category"],
                             "severity": r["severity"], "lang": r["lang"], "source": "dev"})

        random.Random(7).shuffle(kept)
        n_val = max(1, len(kept) // 10)
        as_test = lambda rows: [{"text": r["message"], "category": r["category"],
                                 "severity": r["severity"], "lang": r["lang"], "id": r["id"]}
                                for r in rows]
        splits = {"train": kept[n_val:], "val": kept[:n_val],
                  "test": as_test(holdout), "test2": as_test(holdout2)}
        for name, rows in splits.items():
            (DATA / f"{name}.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

        synthetic = sum(r["source"] == "synthetic" for r in kept)
        self.stdout.write(self.style.SUCCESS(
            f"train {len(splits['train'])} · val {len(splits['val'])} · test {len(holdout)}"))
        self.stdout.write(f"raw {len(raw)} · kept {synthetic} synthetic "
                          f"({synthetic / len(raw) * 100 if raw else 0:.1f}%) · {dict(stats)}")
        self.stdout.write(f"labels: {Counter((r['category'], r['severity']) for r in kept).most_common()}")
        self.stdout.write(f"languages: {dict(Counter(r['lang'] for r in kept))}")
