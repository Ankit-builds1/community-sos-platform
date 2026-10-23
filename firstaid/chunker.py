"""Split the markdown first-aid guides into retrievable chunks (one per '## ' section)."""
from dataclasses import asdict, dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"


@dataclass
class Chunk:
    id: str          # e.g. "choking#baby-under-1-year"
    doc: str         # file stem, e.g. "choking"
    title: str       # document title, e.g. "Choking"
    section: str     # section heading, e.g. "Baby under 1 year"
    text: str        # the section body

    def embedding_text(self):
        # title + section give the embedding model context about what the text is for
        return f"{self.title}. {self.section}. {self.text}"

    def to_dict(self):
        return asdict(self)


def _slug(text):
    return "-".join(text.lower().replace("(", "").replace(")", "").split())


def chunk_markdown(doc: str, markdown: str) -> list[Chunk]:
    title, section, lines, chunks = doc, "Overview", [], []

    def flush():
        body = "\n".join(lines).strip()
        if body:
            chunks.append(Chunk(id=f"{doc}#{_slug(section)}", doc=doc, title=title,
                                section=section, text=body))

    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section, lines = line[3:].strip(), []
        else:
            lines.append(line)
    flush()
    return chunks


def chunk_document(doc: str, markdown: str) -> Chunk:
    """The whole guide as ONE chunk. Guides are short (~15 lines), and keeping
    'What to do' and 'Do not' together retrieves better than tiny section chunks."""
    sections = chunk_markdown(doc, markdown)
    title = sections[0].title if sections else doc
    body = "\n\n".join(f"{s.section}:\n{s.text}" for s in sections)
    return Chunk(id=doc, doc=doc, title=title, section="Full guide", text=body)


def load_chunks(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    return [chunk_document(path.stem, path.read_text(encoding="utf-8"))
            for path in sorted(knowledge_dir.glob("*.md"))]
