# MyStudyAI

**A medical-school learning system that works inside your agent harness.** Use your **ChatGPT/Codex subscription** in Codex CLI or Pi. No separately billed language-model API key, no duplicated tutor server, no model-specific backend.

Inspired by the foundations-first, probe → plan → teach workflow and skills/extensions architecture in [amosblomqvist/learn](https://github.com/amosblomqvist/learn). This project implements its own medical course-first study skill and note tools.

## Get started with Codex and a ChatGPT account

Requirements: Git, Python 3.10+, an installed Codex CLI, and a ChatGPT account eligible for Codex sign-in.

```bash
git clone https://github.com/alifazelidehkordi/mystudyai.git
cd mystudyai
python -m pip install -e ".[dev]"

mystudyai import "path/to/Physiology Lecture.pdf"
mystudyai context "cardiac output"

# Use ChatGPT account sign-in, not an API key:
codex login
codex
```

Inside Codex, say:

> Use the medical-study skill. Teach me cardiac output based on my imported physiology lecture, starting with a diagnostic question. Show me the learning plan, include professor slide references and useful figures, then quiz me as we go.

Codex loads the repository's `AGENTS.md` and the skill at `.agents/skills/medical-study/SKILL.md`. The **agent itself** does the teaching, not a second model service.

[Official Codex with ChatGPT setup](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)

## Or use Pi with the Codex subscription

Install [Pi](https://github.com/earendil-works/pi) according to its docs, then run `pi` from the **MyStudyAI root directory**:

```bash
cd mystudyai
pi
```

Use Pi's `/login`, select the ChatGPT/Codex subscription authentication option supported by your installed version, and choose the authenticated model from `/model` if necessary. Pi loads `.pi/skills/medical-study/SKILL.md`. Ask Pi to teach the same way as in the Codex example.

**Never set `OPENAI_API_KEY` for MyStudyAI.** We do not run `codex exec` from another harness, proxy subscription credentials, or charge a separate model API. Your active harness handles authentication, permissions and model limits. Which plans and models are supported depends on the harness version and your subscription.

### Other compatible harnesses

Give your harness the `medical-study` SKILL.md and permission to run the local `mystudyai` commands. The skill contains portable, conversational instructions, not Pi-only APIs or Codex-only tool calls. Other harnesses might need to register the skill manually; not all are individually tested.

## Small local toolbox

| Command | Purpose | Network |
|---|---|---|
| `mystudyai import "lecture.pdf"` | Parse professor's PDF, PowerPoint, Word, Markdown or plain text notes; extract images and preserve citations | No |
| `mystudyai context "topic"` | Full cited excerpts for an agent to read | No |
| `mystudyai sources "topic"` | Short preview of matching lecture excerpts | No |
| `mystudyai figures "topic"` | Nearby lecture figures on matched pages/slides | No |
| `mystudyai image-search "topic"` | Search Wikimedia Commons with license/author metadata | Yes, public Commons website API |
| `mystudyai evidence "topic"` | Search PubMed papers and abstracts | Yes, public NCBI website API |

**No paid model API is called by this toolbox.** Commons/NCBI searches use optional public HTTP endpoints, which are technically APIs but **not model APIs** and do not require an OpenAI key. The active agent harness may send material it reads to its own model service under its own permissions; do not use it on confidential or identifiable patient data.

The old `mystudyai ask` and `mystudyai study` commands have been **removed**. They used a separate OpenAI Responses API integration, which conflicts with your subscription-only requirement. Instead start `codex` or `pi` in the repo and speak to the medical-study agent directly.

## How the medical teaching works

**Probe → Plan → Teach → Check → Reinforce**

- **Probe:** Identify which anatomy/physiology/biochemistry prerequisites the student understands and what requires explanation.
- **Plan:** Show a dependency map from core mechanisms to the professor's objective.
- **Teach:** Motivate each concept from first principles, connect it to known facts, explain medical exceptions, and cite the original page/slide.
- **Check:** Ask one diagnostic, conceptual or application question at a time and respond to mistakes.
- **Reinforce:** Summarize weak areas, missed concepts, and a review path. Session logs may be written into `library/study-sessions/` with the learner's permission.

**Course-first does not mean lecture-infallible.** The professor's course determines exam emphasis, but authoritative medical references should be used to flag disputed material. A PubMed record/abstract is a research lead, not automatic verification of a scientific claim.

## Step 4: Quiz practice and spaced review (offline)

**Your existing Codex/Pi agent authors questions; the local MyStudyAI CLI checks source references, grades choices and records spaced-review dates. No LLM API is involved.**

1. Import your real lecture first: `mystudyai import "Physiology.pdf"`.
2. In Codex or Pi, ask: *"Using the medical-study skill and my imported lecture, create 10 high-quality misconception-based MCQs for cardiac output. Write them to the quiz bank, verify original slide/page citations and validate them."*
3. Or create the file yourself:

```bash
mystudyai quiz init "cardiac output"          # Creates an empty private bank
# Your agent edits library/quizzes/cardiac-output.json and adds sourced questions.
mystudyai quiz validate library/quizzes/cardiac-output.json
mystudyai quiz run library/quizzes/cardiac-output.json
mystudyai quiz due library/quizzes/cardiac-output.json
mystudyai quiz mistakes library/quizzes/cardiac-output.json
mystudyai quiz stats library/quizzes/cardiac-output.json
```

Question bank format (`correct_index` is **zero-based**; `source.name` and `source.location` must match your imported course metadata):

```json
{
  "version": 1,
  "title": "Cardiac output",
  "questions": [
    {
      "id": "co-01",
      "concept": "Cardiac output relationship",
      "stem": "Which expression represents cardiac output?",
      "options": ["HR × SV", "HR + SV", "HR / SV", "SV / HR"],
      "correct_index": 0,
      "explanation": "Cardiac output is the product of heart rate and stroke volume.",
      "source": {"name": "Physiology.pdf", "location": "page 7"}
    }
  ]
}
```

This is an **illustrative example**—only use the source reference if it actually exists in your imported lecture. There is no built-in medical question generator; the authenticated harness writes the bank. Validation confirms the lecture location exists but **does not independently verify the medical correctness of a question or explanation**.

The terminal quiz shows the explanation only after answering, asks whether a correct answer was confident, and records misses under the cited concept. Progress is stored locally in `library/quiz-progress.json`. Unseen and due questions come first; `quiz run --all` forces the full bank. A missed answer is scheduled for the next UTC day; successful reviews extend from 1 day to 6 days to increasing intervals, according to a simple SM-2-inspired rule. This is a **study reminder** rather than a scientifically validated medical competence metric. There is no cloud sync, automatic notifications or Pi popup yet.

## Pictures, lectures and citations

- Start with images from imported professor slides and lecture PDFs. PDF text has page references; PPTX text has slide references; DOCX has element markers instead of reliable page numbers.
- To explore images beyond a lecture, search Wikimedia Commons and review the **original source, labels and license** before choosing a figure. For example:

```bash
mystudyai figures "cardiac cycle"
mystudyai image-search "labeled human coronary arteries"
# Confirm the image/license on Commons. Recheck the search result number.
mystudyai image-search "labeled human coronary arteries" \
  --add-to "library/example/notes.md" --select 1 --reviewed
```

The `--reviewed` flag represents **your explicit manual check**, not automatic medical or legal validation. The note will include available author/license/source metadata. Image search may change between calls.

- Text search cannot yet OCR scanned notes or medically interpret histology/CT/X-ray images. Check original images before trusting them.
- `library/` and `course-materials/` are excluded from git. Never commit copyrighted university handouts without permission or upload identifiable patient records.
- This is a medical-school education system, **not** an individual diagnosis or clinical treatment tool.

## Maintain / test

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Repository architecture:

- `AGENTS.md` — cross-harness repo rules, including subscription-only model access.
- `.agents/skills/medical-study/SKILL.md` — Codex skill.
- `.pi/skills/medical-study/SKILL.md` — identical Pi skill, checked by tests.
- `src/mystudyai/` — local importer, text context, figures, optional Commons/PubMed tooling.
- `tests/` — offline tests, mocked third-party HTTP calls.

### Roadmap

1. ✅ Import notes, preserve original source references and extract lecture figures.
2. ✅ Deliver foundations-first tutoring through subscription-authenticated agent skills (no separate LLM API).
3. ✅ Find lecturer images and search attributed Commons/PubMed resources when needed.
4. ✅ Local cited MCQ banks, interactive terminal quiz grading, concept-level mistakes and spaced repetition; optional Pi quiz popups are still future work.
5. ⏳ Add optional Pi/Obsidian quiz popup, diagram and Markdown session-log extensions without losing harness portability.

