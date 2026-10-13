"""Local lexical retrieval over imported professor course notes.

No network calls. Chunks preserve the original source location, so the tutor
can cite the exact page, slide, document element, or line.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are as at be by can could do does for from how i in into is it "
    "its of on or our should that the their there these this to was were what "
    "when where which who why will with you your explain describe tell me "
    "about lecture lectures notes note process role main compare between"
    .split()
)
WORDS = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class Excerpt:
    ref: str
    source: str
    location: str
    text: str
    source_sha256: str

    @property
    def citation(self) -> str:
        return f"[{self.ref}] {self.source}, {self.location}"


def terms(text: str) -> list[str]:
    return [term for term in WORDS.findall(text.casefold()) if len(term) >= 2 and term not in STOPWORDS]


def _chunks(text: str, size: int = 1400, overlap: int = 150) -> list[str]:
    """Split text, favouring whitespace breaks and retaining a little context."""
    if not text.strip():
        return []
    result = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            split_at = text.rfind(" ", start + size // 2, end)
            if split_at != -1:
                end = split_at
        result.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [item for item in result if item]


def load_excerpts(library: Path, *, max_documents: int = 250) -> list[Excerpt]:
    """Read importer-generated document.json files; never execute note content."""
    library = Path(library).expanduser().resolve()
    if not library.is_dir():
        return []
    excerpts: list[Excerpt] = []
    folders = sorted(library.iterdir())
    for folder in folders[:max_documents]:
        file = folder / "document.json"
        if not folder.is_dir() or not file.is_file():
            continue
        if file.stat().st_size > 20_000_000:
            continue
        try:
            doc = json.loads(file.read_text(encoding="utf-8"))
            source = str(doc["source_name"])[:240]
            checksum = str(doc.get("source_sha256", ""))
            blocks = doc["blocks"]
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                location = str(block["location"])[:120]
                text = str(block["text"])
                for snippet in _chunks(text):
                    excerpts.append(Excerpt("", source, location, snippet, checksum))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return excerpts


def retrieve(query: str, library: Path, *, limit: int = 6, budget: int = 10_000) -> list[Excerpt]:
    """Return matching note excerpts with stable per-query source labels S1, S2..."""
    requested = Counter(terms(query))
    if not requested:
        return []
    chunks = load_excerpts(library)
    if not chunks:
        return []
    total = len(chunks)
    doc_freq = Counter()
    for chunk in chunks:
        doc_freq.update(set(terms(chunk.text)))

    ranked: list[tuple[float, Excerpt]] = []
    for excerpt in chunks:
        word_counts = Counter(terms(excerpt.text))
        overlap = requested.keys() & word_counts.keys()
        if not overlap:
            continue
        score = sum(
            (1 + math.log1p(min(word_counts[word], 4)))
            * math.log1p((total + 1) / (1 + doc_freq[word]))
            for word in overlap
        )
        score += sum(0.7 for word in requested if word in terms(excerpt.source))
        if query.strip().casefold() in excerpt.text.casefold():
            score += 2
        ranked.append((score, excerpt))

    ranked.sort(key=lambda item: (-item[0], item[1].source, item[1].location))
    selected: list[Excerpt] = []
    used_chars = 0
    seen: set[tuple[str, str, str]] = set()
    for _, excerpt in ranked:
        key = (excerpt.source_sha256, excerpt.location, excerpt.text)
        if key in seen or used_chars + len(excerpt.text) > budget:
            continue
        selected.append(Excerpt(f"S{len(selected) + 1}", excerpt.source, excerpt.location,
                                excerpt.text, excerpt.source_sha256))
        used_chars += len(excerpt.text)
        seen.add(key)
        if len(selected) >= limit:
            break
    return selected


def format_context(excerpts: list[Excerpt]) -> str:
    if not excerpts:
        return "(No relevant excerpts were retrieved.)"
    return "\n\n".join(
        f"{ex.citation}\n<untrusted_lecture_excerpt>\n{ex.text}\n</untrusted_lecture_excerpt>"
        for ex in excerpts
    )
