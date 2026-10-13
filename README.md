# MyStudyAI

**A course-first AI study workflow for medical school.** Built step-by-step from your actual lecture notes; planned learning flow: **probe → plan → teach → quiz → review**. Inspired by [amosblomqvist/learn](https://github.com/amosblomqvist/learn) (conceptual workflow; no upstream source copied).

## Current milestone: Step 1 — import notes ✅

Turn lectures into Markdown notes and structured JSON with traceable source locations. The importer currently supports:

| File | Text source references | Embedded images |
| --- | --- | --- |
| PDF | Page number | Yes |
| PowerPoint (.pptx) | Slide number | Yes |
| Word (.docx) | Document element number (page numbers unavailable) | Yes, position not tracked |
| Text / Markdown | Line number | N/A |

**Not yet available:** AI teaching/chat, quiz engine, internet image search, OCR for scans, medical source checking, Pi/Obsidian integration. The prompt in `prompts/medical-tutor.md` is a *specification* for Step 2, not a connected AI model.

## Install (Python 3.10+)

```bash
# From your cloned MyStudyAI repository
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Use

```bash
mystudyai import "course-materials/Cardiology Lecture.pdf"
mystudyai import "my-slides.pptx" "notes.docx" --library library
mystudyai inspect library/<imported-folder>
pytest -q
```

Each import creates:

```text
library/
  cardiology-lecture-<file-hash>/
    document.json    # Original file name, SHA-256, text blocks, references, figures, warnings
    notes.md         # Readable Markdown with source page/slide/line references and image links
    images/          # Embedded figures extracted from the file
```

Identical files reuse a content-hash folder, preventing collisions across repeated imports. Imported course material in `library/` and `course-materials/` is intentionally excluded from Git commits. **Avoid committing university materials, private patient information, or copyrighted figures without permission.**

### Known limitations

- Image-only/scanned PDF pages are flagged for OCR; OCR is **not implemented** in Step 1. Review warnings before trusting the notes.
- Order within individual slides is based on PowerPoint's shape order, not necessarily the natural reading order.
- PowerPoint speaker notes, media embedded outside normal picture shapes, and vector chart rendering are not yet extracted.
- DOCX doesn't contain reliable physical page references. Images are saved but not precisely matched to nearby paragraphs.
- An extracted diagram is **not** medical validation. Inspect labels and content before using it to study.

## Planned milestones

1. **Importer (this PR)** — structured course notes, page/slide references, embedded figures, unit tests.
2. **Tutor** — AI answers grounded in imported notes, source citations, concept explanations, probe/plan/teach flow.
3. **Images and evidence** — sourced anatomy/histology search, verified figures, license tracking, verified medical references.
4. **Learning** — adaptive quizzes, misconceptions, and spaced repetition.
5. **Study workspace** — Pi/Obsidian integration and end-to-end testing on real lectures.

See `prompts/medical-tutor.md` for the medical teaching rules.
