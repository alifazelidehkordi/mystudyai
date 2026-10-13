"""Find figures already imported from the student's professor's lecture files.

Never trust paths embedded in JSON metadata to point outside the local library.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .retrieval import Excerpt, retrieve


@dataclass(frozen=True)
class LocalFigure:
    source: str
    location: str
    path: Path
    sha256: str

    def markdown(self) -> str:
        return f"![Figure from {self.source}, {self.location}]({self.path.as_uri()})"


def nearby_figures(library: str | Path, topic: str, limit: int = 8,
                   *, excerpts: list[Excerpt] | None = None) -> list[LocalFigure]:
    """Find professor-supplied images attached to text hits on the same slide/page.

    A slide may contain unrelated figures. Results are unverified suggestions.
    """
    root = Path(library).expanduser().resolve()
    if not root.is_dir() or limit <= 0:
        return []
    excerpts = excerpts if excerpts is not None else retrieve(topic, root, limit=10)
    keyed = {(ex.source_sha256, ex.source, ex.location) for ex in excerpts}
    found: list[LocalFigure] = []
    seen = set()
    for folder in sorted(root.iterdir()):
        record = folder / "document.json"
        if not folder.is_dir() or not record.is_file():
            continue
        try:
            if record.stat().st_size > 20_000_000:
                continue
            obj = json.loads(record.read_text(encoding="utf-8"))
            source = str(obj.get("source_name", ""))[:240]
            sha = str(obj.get("source_sha256", ""))
            for info in obj.get("figures", []):
                location = str(info.get("location", ""))[:120]
                if (sha, source, location) not in keyed:
                    continue
                path = (folder / str(info.get("path", ""))).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file():
                    continue
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}:
                    continue
                key = (sha, location, str(path))
                if key not in seen:
                    found.append(LocalFigure(source, location, path, str(info.get("sha256", ""))))
                    seen.add(key)
                    if len(found) >= limit:
                        return found
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return found
