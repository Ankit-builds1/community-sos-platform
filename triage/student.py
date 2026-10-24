"""Fine-tuned triage model ("student"), distilled from the LLM teacher.

Runs locally with onnxruntime + tokenizers (both already installed for fastembed):
no API, no GPU, about 20-50 ms per message. Used when the LLM is unavailable,
rate-limited, over budget or unsure, instead of falling straight to keyword rules.

Model files (from triage/finetune/train.py) live in triage/finetune/model/:
    model.onnx  tokenizer.json  config.json
If they are missing, available() returns False and the agent skips this step.
"""
import json
import logging
import threading
from pathlib import Path

import numpy as np
from django.conf import settings

from .schema import TriageResult

logger = logging.getLogger(__name__)
MODEL_DIR = Path(__file__).resolve().parent / "finetune" / "model"
_lock = threading.Lock()
_loaded = None  # (session, tokenizer, config) once loaded


def available():
    return (getattr(settings, "TRIAGE_STUDENT_ENABLED", True)
            and (MODEL_DIR / "model.onnx").exists() and (MODEL_DIR / "tokenizer.json").exists())


def _load():
    """Lazy, thread-safe: the model is only loaded the first time it is needed."""
    global _loaded
    if _loaded is None:
        with _lock:
            if _loaded is None:
                import onnxruntime as ort
                from tokenizers import Tokenizer

                config = json.loads((MODEL_DIR / "config.json").read_text())
                tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
                tok.enable_truncation(config.get("max_length", 128))
                tok.no_padding()
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                session = ort.InferenceSession(str(MODEL_DIR / "model.onnx"), opts,
                                               providers=["CPUExecutionProvider"])
                _loaded = (session, tok, config)
    return _loaded


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def safe_severity(probs, tau):
    """Most serious level whose cumulative probability P(sev >= level) reaches tau
    (same decision rule the model was tuned with)."""
    cum = np.cumsum(probs[::-1])[::-1]
    for k in range(len(probs) - 1, -1, -1):
        if cum[k] >= tau:
            return k
    return int(np.argmax(probs))


SUMMARY = {
    "medical": "A medical emergency was reported",
    "fall": "A fall was reported",
    "fire": "A fire or gas emergency was reported",
    "security": "A security emergency was reported",
    "other": "An emergency was reported",
}


def predict(message: str) -> TriageResult:
    session, tok, config = _load()
    enc = tok.encode(message or "help")
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    cat_logits, sev_logits = session.run(None, {"input_ids": ids, "attention_mask": mask})
    cat_p, sev_p = _softmax(cat_logits[0]), _softmax(sev_logits[0])

    category = config["categories"][int(cat_p.argmax())]
    severity = config["severities"][safe_severity(sev_p, config.get("tau", 0.35))]
    confidence = float(min(cat_p.max(), sev_p.max()))
    return TriageResult(
        category=category, severity=severity, confidence=round(confidence, 3),
        guardian_summary=f"{SUMMARY[category]} ({severity} priority). Responders have been alerted.",
        source="model", model="fine-tuned " + config.get("base", "").split("/")[-1],
    )
