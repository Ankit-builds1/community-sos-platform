"""Plain-Python metrics for the triage evaluation (no sklearn needed)."""
from collections import Counter

from triage.schema import SEVERITY_RANK

CATEGORIES = ["medical", "fall", "fire", "security", "other"]


def per_class_f1(gold, pred, labels):
    scores = {}
    for label in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores[label] = {"precision": precision, "recall": recall, "f1": f1,
                         "support": tp + fn}
    return scores


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def summarise(rows):
    """rows: dicts with gold_* and pred_* keys. Returns a metrics dict."""
    n = len(rows)
    gold_cat = [r["gold_category"] for r in rows]
    pred_cat = [r["pred_category"] for r in rows]
    per_class = per_class_f1(gold_cat, pred_cat, CATEGORIES)

    under = [r for r in rows
             if SEVERITY_RANK[r["pred_severity"]] < SEVERITY_RANK[r["gold_severity"]]]
    over = [r for r in rows
            if SEVERITY_RANK[r["pred_severity"]] > SEVERITY_RANK[r["gold_severity"]]]
    critical = [r for r in rows if r["gold_severity"] == "critical"]
    injections = [r for r in rows if r.get("injection")]
    latencies = [r["llm_ms"] for r in rows if r.get("llm_ms") is not None]

    return {
        "n": n,
        "category_accuracy": sum(g == p for g, p in zip(gold_cat, pred_cat)) / n,
        "category_macro_f1": sum(s["f1"] for s in per_class.values()) / len(per_class),
        "per_class": per_class,
        "severity_exact": sum(r["pred_severity"] == r["gold_severity"] for r in rows) / n,
        # SAFETY metric: predicted less serious than reality. Lower is better.
        "under_triage_rate": len(under) / n,
        "over_triage_rate": len(over) / n,
        "critical_recall": (sum(r["pred_severity"] == "critical" for r in critical)
                            / len(critical)) if critical else None,
        "injection_flag_recall": (sum(r["pred_injection"] for r in injections)
                                  / len(injections)) if injections else None,
        "llm_used_rate": sum(r["source"] == "llm" for r in rows) / n,
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "by_language": dict(Counter(r["lang"] for r in rows)),
        "under_triaged_ids": [r["id"] for r in under],
    }
