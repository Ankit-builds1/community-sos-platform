"""Publish / download the fine-tuned triage model via the Hugging Face Hub.

    python manage.py triage_model push --repo <user>/sos-triage-minilm   # needs HF_TOKEN in .env
    python manage.py triage_model pull                                      # used by the Dockerfile

The model (~115 MB int8 ONNX) is too big for GitHub, so it lives on the Hub and is
downloaded at image build time, like the embedding model.
"""
import os
import shutil

from django.core.management.base import BaseCommand, CommandError

from triage.student import MODEL_DIR

FILES = ["model.onnx", "tokenizer.json", "config.json", "metrics.json"]
DEFAULT_REPO = os.getenv("TRIAGE_MODEL_REPO", "Ankit-builds/sos-triage-minilm")

CARD = """---
language: [en, hi, or]
license: apache-2.0
pipeline_tag: text-classification
tags: [emergency, triage, multilingual, onnx, distillation]
base_model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
---
# SOS triage model (multilingual, int8 ONNX)

Classifies an emergency SOS message into a **category** (medical, fall, fire, security,
other) and a **severity** (low, medium, high, critical). English, Hinglish, Hindi and Odia.

Fine-tuned from `paraphrase-multilingual-MiniLM-L12-v2` (two heads, safety-weighted loss)
on LLM-generated messages that a second, independent LLM re-labelled (only agreements kept).
Used as the offline fallback of the triage agent in
[Community SOS](https://github.com/Ankit-builds1/community-sos-platform).

Evaluation (50 held-out, hand-written messages) is in `metrics.json`.

**Not a medical device.** Part of a portfolio project; in an emergency call 112 / 108.
"""


class Command(BaseCommand):
    help = "Push the fine-tuned triage model to, or pull it from, the Hugging Face Hub."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["push", "pull"])
        parser.add_argument("--repo", default=DEFAULT_REPO)

    def handle(self, action, repo, **opts):
        from huggingface_hub import HfApi, hf_hub_download

        if action == "push":
            token = os.getenv("HF_TOKEN")
            if not token:
                raise CommandError("Set HF_TOKEN in .env first.")
            missing = [f for f in FILES[:3] if not (MODEL_DIR / f).exists()]
            if missing:
                raise CommandError(f"Missing in {MODEL_DIR}: {missing}")
            (MODEL_DIR / "README.md").write_text(CARD, encoding="utf-8")
            api = HfApi(token=token)
            api.create_repo(repo, exist_ok=True)
            api.upload_folder(repo_id=repo, folder_path=str(MODEL_DIR),
                              allow_patterns=FILES + ["README.md"],
                              commit_message="Upload fine-tuned SOS triage model")
            self.stdout.write(self.style.SUCCESS(f"Uploaded: https://huggingface.co/{repo}"))
        else:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            for name in FILES:
                try:
                    path = hf_hub_download(repo, name)
                except Exception as exc:
                    if name == "metrics.json":
                        continue
                    raise CommandError(f"Could not download {name} from {repo}: {exc}")
                shutil.copy(path, MODEL_DIR / name)
            self.stdout.write(self.style.SUCCESS(f"Model ready in {MODEL_DIR}"))
