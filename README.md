# MyStudyAI

**A course-first AI study workflow for medical school.** Built step-by-step from your actual lecture notes; planned learning flow: **probe → plan → teach → quiz → review**. Inspired by [amosblomqvist/learn](https://github.com/amosblomqvist/learn) (conceptual workflow; no upstream source copied).

## Milestones: Step 1 — Import notes ✅ · Step 2 — Medical tutor ✅ · Step 3 — Images and PubMed lookup ✅

Turn lectures into Markdown notes and structured JSON with traceable source locations. The importer currently supports:

| File | Text source references | Embedded images |
| --- | --- | --- |
| PDF | Page number | Yes |
| PowerPoint (.pptx) | Slide number | Yes |
| Word (.docx) | Document element number (page numbers unavailable) | Yes, position not tracked |
| Text / Markdown | Line number | N/A |

**Now available:** source-grounded AI study, lecturer-provided figures near matching slide/page text, Commons image discovery and opt-in insertion, and PubMed abstract lookup. **Not yet available:** actual automatic medical claim verification, true adaptive grading/spaced repetition, image interpretation, OCR, Pi/Obsidian integration or a graphical interface.

## Step 2: Medical AI tutor (requires an OpenAI API key)

Import your course documents first using the Step 1 commands below. Then:

```bash
# Review exactly which note excerpts will be considered (local, NO API call)
mystudyai sources "cardiac output" --library library

# Set the OpenAI key in your terminal (do not paste it into a public repository)
# macOS/Linux: export OPENAI_API_KEY=...
# PowerShell: $env:OPENAI_API_KEY = '...'

# Ask one sourced question
mystudyai ask "How does preload affect stroke volume?" --library library --send-notes

# Interactive probe → plan → teach → check loop
mystudyai study "cardiac output" --library library --send-notes

# Optionally choose a different model
mystudyai ask "Cardiac cycle" --model gpt-4.1-mini --send-notes
```

**Privacy and cost:** The `sources` command runs fully offline. The `ask` and `study` commands refuse to contact the model until you explicitly add `--send-notes`. With that flag they send **selected text excerpts** from your imported lectures, your question, and any answer you type to OpenAI over HTTPS; API usage may incur charges. Images are not sent. The API request specifies `store: false` but external processing still occurs. Never import or upload identifiable patient data or confidential teaching material without permission. Your API key is read from the `OPENAI_API_KEY` environment variable, not committed to Git.

**Source limits:** The tutor retrieves up to six text excerpts using local keyword overlap; it may miss relevant slides or diagrams. It requires some lexical overlap with your query. Citation identifiers `[S1]` are checked to ensure they point to excerpts supplied during that answer, but **a valid citation label does NOT prove that the AI's medical statement is supported by that excerpt**. Always check original slides and trusted medical references. Neither medical fact verification nor diagnostic use is implemented. The study session is in memory only, and there is no persistent progress tracker yet.

**If a topic isn't found:** Import the correct lecture, use `mystudyai sources` to inspect retrieval, or try more specific words from your professor's slides.

## Step 3: Images and scientific literature

Use **existing lecture pictures first** (this command is offline):

```bash
mystudyai figures "left ventricle" --library library
```

The tutor will also append **potentially relevant local figures** when they are on the same slide/page as retrieved lecture text. It does not interpret or medically validate those images. Images without nearby extracted text and some Word-document images cannot yet be associated with a topic.

Find candidate educational images using Wikimedia Commons (search terms are sent to Commons, **not** your private notes):

```bash
mystudyai image-search "human coronary arteries labeled" --limit 8

# Review the image's Wikimedia Commons FILE PAGE and license manually.
# Then explicitly choose a result number and the imported Markdown note to update:
mystudyai image-search "human coronary arteries labeled" \
  --add-to "library/heart-123abc/notes.md" --select 1 --reviewed
```

**Caution:** Image search results may change between searches; check the result number again. The image must have a supported Wikimedia Commons license and be a JPEG/PNG/WebP thumbnail. Inserting requires `--reviewed`, downloads an image into the note's `external-images/` folder and adds creator, license, original file-page URL and retrieval date. Manual review is **not** the same as expert medical validation, and metadata/license claims can be mistaken. Respect any share-alike or attribution requirements and your university's content policies. Images are never silently inserted.

Search PubMed for research citations and abstracts via NCBI E-utilities (your topic string, not lecture excerpts, is sent to NCBI):

```bash
mystudyai evidence "Frank Starling preload stroke volume" --limit 4

# Optional: pass separately cited PubMed abstracts into a grounded tutor response
mystudyai ask "How does preload affect stroke volume?" --with-evidence --send-notes
mystudyai study "cardiac output" --with-evidence --send-notes
```

When `--with-evidence` is enabled, the tutor distinguishes `[S1]` course passage references from `[P1]` PubMed literature references, and compares possible agreement or disagreements. The tutor checks whether citation IDs exist but **does not prove that cited papers support an AI claim**. PubMed records and abstracts are not reviewed medical guidelines or fact-checking. The learner should inspect methods, full text, study limitations and authoritative guidelines before relying on results.

Network access is required for Commons/PubMed. The automated tests mock external HTTP services; live third-party availability, rights, image accuracy and API model behavior are not guaranteed.


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
2. **Tutor (this PR)** — AI answers based on locally retrieved lecture excerpts, citations and interactive probe/plan/teach/check.
3. **Images and PubMed (this PR)** — local lecture figures, optional Commons image insertion with attribution, separate PubMed abstract discovery (not independent medical verification).
4. **Learning (next)** — adaptive quizzes, misconceptions, and spaced repetition.
5. **Study workspace** — Pi/Obsidian integration and end-to-end testing on real lectures.

Medical teaching safeguards are enforced through `src/mystudyai/tutor.py`. See also `prompts/medical-tutor.md`.
