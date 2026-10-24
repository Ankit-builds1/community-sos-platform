"""Where do the generator label and the teacher label disagree? (data-quality report)

    python triage/finetune/analyze.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def load(name):
    return [json.loads(l) for l in (DATA / name).read_text(encoding="utf-8").splitlines() if l.strip()]


teacher = {r["id"]: r for r in load("teacher.jsonl")}
raw = load("raw.jsonl")
by_scenario, by_lang, ok_lang = defaultdict(Counter), Counter(), Counter()
for r in raw:
    t = teacher.get(r["id"])
    if not t:
        continue
    same = (t["category"], t["severity"]) == (r["category"], r["severity"])
    by_scenario[r["scenario"]]["ok" if same else f"{t['category']}/{t['severity']}"] += 1
    by_lang[r["lang"]] += 1
    ok_lang[r["lang"]] += same

for scenario, c in sorted(by_scenario.items(), key=lambda kv: kv[1]["ok"] / sum(kv[1].values())):
    n = sum(c.values())
    worst = [(k, v) for k, v in c.most_common(4) if k != "ok"][:3]
    print(f"{scenario:17} agree {c['ok'] / n:4.0%}  teacher said {worst}")
print({lang: f"{ok_lang[lang] / n:.0%}" for lang, n in by_lang.items()})
