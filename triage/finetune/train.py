"""Fine-tune a multilingual transformer for SOS triage (category + severity).

Runs on a free Kaggle GPU (T4/P100). Usage in a Kaggle notebook cell:
    !pip -q install onnx onnxruntime
    !python /kaggle/input/<dataset>/train.py --data /kaggle/input/<dataset>

Outputs in /kaggle/working/triage_model/:
    model.onnx (int8)  tokenizer.json  config.json  metrics.json
Download that folder and put it in  triage/finetune/model/  in the project.

Design
- One shared encoder (mean pooling) + two linear heads (5 categories, 4 severities).
- Safety-weighted severity loss: predicting a LESS serious level costs extra
  (under-triage is the dangerous mistake), plus a decision threshold tuned on val:
  pick the most serious level whose cumulative probability >= tau.
- The 50 held-out messages (test.jsonl) are only used once, at the very end.
"""
import argparse
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

CATEGORIES = ["medical", "fall", "fire", "security", "other"]
SEVERITIES = ["low", "medium", "high", "critical"]  # index = seriousness rank
UNDER_PENALTY = 4.0  # extra loss weight when the gold label is more serious (v2 used 2.0)


def load(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


class TriageModel(nn.Module):
    def __init__(self, base):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base)
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.cat_head = nn.Linear(hidden, len(CATEGORIES))
        self.sev_head = nn.Linear(hidden, len(SEVERITIES))

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).float()
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-6)  # mean pooling
        pooled = self.dropout(pooled)
        return self.cat_head(pooled), self.sev_head(pooled)


def severity_loss(logits, gold):
    """Cross-entropy, weighted up for examples the model currently under-triages."""
    ce = F.cross_entropy(logits, gold, reduction="none")
    pred = logits.argmax(-1)
    weight = torch.where(pred < gold, torch.full_like(ce, UNDER_PENALTY), torch.ones_like(ce))
    return (ce * weight).mean()


def safe_severity(probs, tau):
    """Most serious level whose cumulative probability P(sev >= level) reaches tau."""
    cum = np.cumsum(probs[::-1])[::-1]  # cum[k] = P(sev >= k)
    for k in range(len(SEVERITIES) - 1, -1, -1):
        if cum[k] >= tau:
            return k
    return int(np.argmax(probs))


def metrics(rows, cat_pred, sev_pred):
    gold_c = [CATEGORIES.index(r["category"]) for r in rows]
    gold_s = [SEVERITIES.index(r["severity"]) for r in rows]
    n = len(rows)
    f1s = []
    for c in range(len(CATEGORIES)):
        tp = sum(g == c and p == c for g, p in zip(gold_c, cat_pred))
        fp = sum(g != c and p == c for g, p in zip(gold_c, cat_pred))
        fn = sum(g == c and p != c for g, p in zip(gold_c, cat_pred))
        pr, rc = (tp / (tp + fp) if tp + fp else 0), (tp / (tp + fn) if tp + fn else 0)
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0)
    crit = [i for i, g in enumerate(gold_s) if g == 3]
    return {
        "n": n,
        "category_accuracy": sum(g == p for g, p in zip(gold_c, cat_pred)) / n,
        "category_macro_f1": sum(f1s) / len(f1s),
        "severity_exact": sum(g == p for g, p in zip(gold_s, sev_pred)) / n,
        "under_triage_rate": sum(p < g for g, p in zip(gold_s, sev_pred)) / n,
        "over_triage_rate": sum(p > g for g, p in zip(gold_s, sev_pred)) / n,
        "critical_recall": (sum(sev_pred[i] == 3 for i in crit) / len(crit)) if crit else None,
    }


@torch.no_grad()
def predict(model, tok, rows, device, bs=64):
    model.eval()
    cat_p, sev_p = [], []
    for i in range(0, len(rows), bs):
        enc = tok([r["text"] for r in rows[i:i + bs]], padding=True, truncation=True,
                  max_length=128, return_tensors="pt").to(device)
        c, s = model(enc["input_ids"], enc["attention_mask"])
        cat_p.append(F.softmax(c, -1).cpu().numpy())
        sev_p.append(F.softmax(s, -1).cpu().numpy())
    return np.concatenate(cat_p), np.concatenate(sev_p)


def train_one(base, train, val, args, device):
    torch.manual_seed(args.seed); random.seed(args.seed); np.random.seed(args.seed)
    tok = AutoTokenizer.from_pretrained(base)
    model = TriageModel(base).to(device)

    def collate(batch):
        enc = tok([b["text"] for b in batch], padding=True, truncation=True,
                  max_length=128, return_tensors="pt")
        enc["cat"] = torch.tensor([CATEGORIES.index(b["category"]) for b in batch])
        enc["sev"] = torch.tensor([SEVERITIES.index(b["severity"]) for b in batch])
        return enc

    loader = DataLoader(train, batch_size=args.batch, shuffle=True, collate_fn=collate)
    # small models need a higher learning rate than XLM-R base
    lr = args.lr if args.lr else (2e-5 if "xlm-roberta" in base else 6e-5)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    steps = len(loader) * args.epochs
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    best, best_state = -1, None
    for epoch in range(args.epochs):
        model.train()
        total = 0.0
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            c, s = model(batch["input_ids"], batch["attention_mask"])
            loss = F.cross_entropy(c, batch["cat"]) + severity_loss(s, batch["sev"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            total += loss.item()
        cp, sp = predict(model, tok, val, device)
        m = metrics(val, cp.argmax(1).tolist(), sp.argmax(1).tolist())
        # model selection: category F1 + severity exact - 2x under-triage (safety first)
        score = m["category_macro_f1"] + m["severity_exact"] - 4 * m["under_triage_rate"]
        print(f"[{base.split('/')[-1]}] epoch {epoch + 1}: loss {total / len(loader):.3f} "
              f"val catF1 {m['category_macro_f1']:.3f} sev {m['severity_exact']:.3f} "
              f"under {m['under_triage_rate']:.3f}")
        if score > best:
            best = score
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, tok


def tune_tau(sev_probs, rows):
    """Choose tau on validation: best exact match, with under-triage weighted 3x
    (an under-triaged emergency costs more than an over-triaged one)."""
    gold = [SEVERITIES.index(r["severity"]) for r in rows]
    best = None
    for tau in np.arange(0.20, 0.65, 0.05):
        pred = [safe_severity(p, tau) for p in sev_probs]
        under = sum(p < g for g, p in zip(gold, pred)) / len(rows)
        exact = sum(p == g for g, p in zip(gold, pred)) / len(rows)
        score = exact - 3 * under
        if best is None or score > best[0]:
            best = (score, float(round(tau, 2)))
    return best[1]


def export_onnx(model, tok, out_dir):
    from onnxruntime.quantization import QuantType, quantize_dynamic
    model = model.cpu().eval()
    enc = tok(["papa gir gaye jaldi aao"], return_tensors="pt")
    fp32 = out_dir / "model-fp32.onnx"
    kwargs = dict(input_names=["input_ids", "attention_mask"],
                  output_names=["category_logits", "severity_logits"],
                  dynamic_axes={"input_ids": {0: "b", 1: "t"},
                                "attention_mask": {0: "b", 1: "t"},
                                "category_logits": {0: "b"}, "severity_logits": {0: "b"}},
                  opset_version=17)
    try:  # newer PyTorch defaults to the dynamo exporter; use the classic one
        torch.onnx.export(model, (enc["input_ids"], enc["attention_mask"]), str(fp32),
                          dynamo=False, **kwargs)
    except TypeError:  # older PyTorch without the `dynamo` argument
        torch.onnx.export(model, (enc["input_ids"], enc["attention_mask"]), str(fp32), **kwargs)
    quantize_dynamic(str(fp32), str(out_dir / "model.onnx"), weight_type=QuantType.QInt8)
    fp32.unlink()
    tok.backend_tokenizer.save(str(out_dir / "tokenizer.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=".")
    ap.add_argument("--out", default="/kaggle/working/triage_model")
    ap.add_argument("--bases", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2,"
                                       "xlm-roberta-base")
    ap.add_argument("--deploy", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                    help="which base to export (must fit a 512 MB server)")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=None, help="default: 6e-5 MiniLM, 2e-5 XLM-R")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = Path(args.data)
    train, val, test = load(data / "train.jsonl"), load(data / "val.jsonl"), load(data / "test.jsonl")
    test2 = load(data / "test2.jsonl") if (data / "test2.jsonl").exists() else []
    print(f"device {device} · train {len(train)} · val {len(val)} · test {len(test)}")

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    report = {}
    for base in [b.strip() for b in args.bases.split(",") if b.strip()]:
        started = time.time()
        model, tok = train_one(base, train, val, args, device)
        _, val_sev = predict(model, tok, val, device)
        tau = tune_tau(val_sev, val)
        cat_p, sev_p = predict(model, tok, test, device)
        test_m = metrics(test, cat_p.argmax(1).tolist(), [safe_severity(p, tau) for p in sev_p])
        test_m_argmax = metrics(test, cat_p.argmax(1).tolist(), sev_p.argmax(1).tolist())
        name = base.split("/")[-1]
        test2_m = None
        if test2:
            c2, s2 = predict(model, tok, test2, device)
            test2_m = metrics(test2, c2.argmax(1).tolist(), [safe_severity(p, tau) for p in s2])
            print(f"\n== {name} on HOLDOUT-2 (tau={tau}) ==\n{json.dumps(test2_m, indent=2)}")
        report[name] = {"tau": tau, "holdout": test_m, "holdout_argmax": test_m_argmax,
                        "holdout2": test2_m,
                        "train_minutes": round((time.time() - started) / 60, 1),
                        "predictions": [
                            {"id": r.get("id"), "lang": r["lang"], "text": r["text"],
                             "gold": f"{r['category']}/{r['severity']}",
                             "pred": f"{CATEGORIES[int(c.argmax())]}/"
                                     f"{SEVERITIES[safe_severity(s, tau)]}"}
                            for r, c, s in zip(test, cat_p, sev_p)]}
        wrong = [p for p in report[name]["predictions"] if p["gold"] != p["pred"]]
        print(f"{len(wrong)} holdout mistakes:")
        for p in wrong:
            print(f"  [{p['lang']:9}] gold {p['gold']:18} pred {p['pred']:18} | {p['text'][:70]}")
        print(f"\n== {name} on HOLDOUT (tau={tau}) ==\n{json.dumps(test_m, indent=2)}")
        if base == args.deploy:
            export_onnx(model, tok, out)
            (out / "config.json").write_text(json.dumps({
                "base": base, "categories": CATEGORIES, "severities": SEVERITIES,
                "tau": tau, "max_length": 128}, indent=2))
        del model; torch.cuda.empty_cache()

    (out / "metrics.json").write_text(json.dumps(report, indent=2))
    size = (out / "model.onnx").stat().st_size / 1e6 if (out / "model.onnx").exists() else 0
    print(f"\nSaved to {out} (model.onnx {size:.0f} MB)")


if __name__ == "__main__":
    main()
