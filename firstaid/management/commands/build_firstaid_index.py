"""python manage.py build_firstaid_index   -> embed the first-aid guides into the vector index.

Run again whenever you add or edit a file in firstaid/knowledge/.
python manage.py build_firstaid_index --query "papa ko chhati mein dard"   -> test a search
"""
import time

from django.core.management.base import BaseCommand

from firstaid.vectorstore import EMBED_MODEL, build_index, search


class Command(BaseCommand):
    help = "Build the first-aid vector index (local embeddings, no API needed)."

    def add_arguments(self, parser):
        parser.add_argument("--query", default=None, help="run a test search afterwards")

    def handle(self, *args, query, **options):
        self.stdout.write(f"Embedding model: {EMBED_MODEL} (first run downloads it once)")
        started = time.perf_counter()
        count = build_index()
        self.stdout.write(self.style.SUCCESS(
            f"Indexed {count} chunks in {time.perf_counter() - started:.1f}s"))

        if query:
            self.stdout.write(f"\nTop matches for: {query!r}")
            for hit in search(query, k=3):
                self.stdout.write(f"  {hit['score']:.3f}  {hit['title']} > {hit['section']}")
