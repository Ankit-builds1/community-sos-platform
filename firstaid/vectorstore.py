"""Local embeddings + a small vector store with parent-document retrieval.

- Embeddings run on the CPU with fastembed (ONNX): free, no API.
- Parent-document ("small-to-big") retrieval: we SEARCH small pieces of each guide
  (its "Covers" line and each section, plus the whole guide), score each guide by its
  best-matching piece, and RETURN the whole guide so the LLM gets full context.
- Stored as .npy + .json; can move to pgvector when we switch to PostgreSQL.
"""
import json
from pathlib import Path

import numpy as np

from .chunker import KNOWLEDGE_DIR, chunk_markdown, load_chunks

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
INDEX_DIR = Path(__file__).resolve().parent / "index"

_embedder = None
_index = None  # (piece_vectors, piece_to_doc, docs)


def get_embedder():
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding  # imported lazily: slow first load
        _embedder = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder


def embed(texts):
    vectors = np.array(list(get_embedder().embed(list(texts))), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)  # unit length -> dot product = cosine


def build_index(index_dir: Path = INDEX_DIR):
    docs = load_chunks()  # one parent chunk per guide
    pieces, piece_to_doc = [], []
    for doc_index, doc in enumerate(docs):
        markdown = (KNOWLEDGE_DIR / f"{doc.doc}.md").read_text(encoding="utf-8")
        children = [c.embedding_text() for c in chunk_markdown(doc.doc, markdown)]
        for text in children + [doc.embedding_text()]:
            pieces.append(text)
            piece_to_doc.append(doc_index)

    matrix = embed(pieces)
    index_dir.mkdir(exist_ok=True)
    np.save(index_dir / "vectors.npy", matrix)
    np.save(index_dir / "piece_to_doc.npy", np.array(piece_to_doc))
    (index_dir / "chunks.json").write_text(
        json.dumps([d.to_dict() for d in docs], indent=2, ensure_ascii=False),
        encoding="utf-8")
    global _index
    _index = (matrix, np.array(piece_to_doc), [d.to_dict() for d in docs])
    return len(docs)


def load_index(index_dir: Path = INDEX_DIR):
    global _index
    if _index is None:
        if not (index_dir / "piece_to_doc.npy").exists():
            build_index(index_dir)
        else:
            _index = (np.load(index_dir / "vectors.npy"),
                      np.load(index_dir / "piece_to_doc.npy"),
                      json.loads((index_dir / "chunks.json").read_text(encoding="utf-8")))
    return _index


def search(query: str, k: int = 3):
    """Return the k best guides (whole documents) with 'score' = best piece cosine."""
    matrix, piece_to_doc, docs = load_index()
    piece_scores = matrix @ embed([query])[0]
    doc_scores = np.full(len(docs), -1.0, dtype=np.float32)
    np.maximum.at(doc_scores, piece_to_doc, piece_scores)  # best piece per guide
    best = np.argsort(-doc_scores)[:k]
    return [{**docs[i], "score": float(doc_scores[i])} for i in best]
