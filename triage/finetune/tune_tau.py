"""Re-tune the safety threshold tau of the exported model on the VALIDATION set only.

    python manage.py shell -c "from triage.finetune.tune_tau import main; main()"          # report
    python manage.py shell -c "from triage.finetune.tune_tau import main; main(write=True)"  # save

Rule: among taus whose validation under-triage <= MAX_UNDER, take the one with the best
exact severity match. The holdout set is never looked at here.
"""
import json
from pathlib import Path

import numpy as np

from triage import student

DATA = Path(__file__).resolve().parent / "data"
MAX_UNDER = 0.03
RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def main(write=False, max_under=MAX_UNDER):
    session, tok, config = student._load()
    rows = [json.loads(l) for l in (DATA / "val.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    probs = []
    for r in rows:
        enc = tok.encode(r["text"] or "help")
        _, sev = session.run(None, {"input_ids": np.array([enc.ids], dtype=np.int64),
                                    "attention_mask": np.array([enc.attention_mask], dtype=np.int64)})
        probs.append(student._softmax(sev[0]))
    gold = [RANK[r["severity"]] for r in rows]

    results = []
    for tau in np.round(np.arange(0.05, 0.65, 0.05), 2):
        pred = [student.safe_severity(p, tau) for p in probs]
        n = len(rows)
        under = sum(p < g for g, p in zip(gold, pred)) / n
        exact = sum(p == g for g, p in zip(gold, pred)) / n
        crit = [i for i, g in enumerate(gold) if g == 3]
        recall = sum(pred[i] == 3 for i in crit) / len(crit)
        results.append((float(tau), under, exact, recall))
        print(f"tau {tau:.2f}  under {under:6.1%}  exact {exact:6.1%}  critical recall {recall:6.1%}")

    ok = [r for r in results if r[1] <= max_under] or [min(results, key=lambda r: r[1])]
    best = max(ok, key=lambda r: (r[2], r[0]))
    print(f"\nchosen tau = {best[0]} (val under {best[1]:.1%}, exact {best[2]:.1%}, "
          f"critical recall {best[3]:.1%}); previous {config['tau']}")
    if write:
        path = student.MODEL_DIR / "config.json"
        cfg = json.loads(path.read_text())
        cfg["tau"] = best[0]
        path.write_text(json.dumps(cfg, indent=2))
        print("saved to config.json")
