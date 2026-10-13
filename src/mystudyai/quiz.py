"""Offline, harness-agnostic question banks and spaced-repetition tracking.

The active Codex/Pi agent authors review questions from cited lectures.
This module only validates files, grades multiple-choice answers and
stores local study progress. It never invokes a model or contacts a service.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta, timezone, datetime
from pathlib import Path
from typing import Callable


class QuizError(ValueError):
    """Invalid or unsafe local question-bank content."""


@dataclass(frozen=True)
class Question:
    id: str
    concept: str
    stem: str
    options: tuple[str, ...]
    correct_index: int
    explanation: str
    source: str
    location: str
    key: str


def library_path(library: str | Path) -> Path:
    return Path(library).expanduser().resolve()


def quiz_path(path: str | Path, library: str | Path) -> Path:
    root = library_path(library)
    p = Path(path).expanduser().resolve()
    if not p.is_relative_to(root / "quizzes") or p.suffix.lower() != ".json":
        raise QuizError("Quiz banks must be JSON files inside library/quizzes/")
    return p


def _field(obj: dict, name: str, max_length: int = 1500) -> str:
    value = obj.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise QuizError(f"Question field '{name}' must be non-empty text (max {max_length} characters).")
    return value.strip()


def _known_sources(library: Path) -> set[tuple[str, str]]:
    """Read the same document.json records created by our lecture importer."""
    refs: set[tuple[str, str]] = set()
    if not library.is_dir():
        return refs
    for folder in library.iterdir():
        path = folder / "document.json"
        if not folder.is_dir() or not path.is_file() or path.stat().st_size > 20_000_000:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            name = doc["source_name"]
            for item in doc.get("blocks", []) + doc.get("figures", []):
                location = item.get("location")
                if isinstance(name, str) and isinstance(location, str):
                    refs.add((name, location))
        except (OSError, KeyError, TypeError, ValueError):
            continue
    return refs


def load_bank(path: str | Path, library: str | Path) -> tuple[str, list[Question]]:
    root = library_path(library)
    bank_path = quiz_path(path, root)
    if not bank_path.is_file():
        raise QuizError(f"Quiz bank does not exist: {bank_path}")
    if bank_path.stat().st_size > 2_000_000:
        raise QuizError("Quiz bank is too large (2 MB maximum).")
    try:
        bank = json.loads(bank_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise QuizError(f"Could not read quiz bank: {exc}") from None
    if not isinstance(bank, dict) or bank.get("version") != 1:
        raise QuizError("Quiz bank must have version: 1.")
    title = _field(bank, "title", 120)
    records = bank.get("questions")
    if not isinstance(records, list) or not 1 <= len(records) <= 500:
        raise QuizError("Quiz bank must contain 1–500 questions.")
    references = _known_sources(root)
    if not references:
        raise QuizError("Import relevant course documents before creating source-cited quiz questions.")
    seen_ids: set[str] = set()
    questions = []
    for i, item in enumerate(records, 1):
        if not isinstance(item, dict):
            raise QuizError(f"Question {i} must be an object.")
        uid = _field(item, "id", 64)
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", uid):
            raise QuizError(f"Question {i} has invalid id; use letters, digits, '-' or '_'.")
        if uid in seen_ids:
            raise QuizError(f"Duplicate question id: {uid}")
        seen_ids.add(uid)
        concept = _field(item, "concept", 160)
        stem = _field(item, "stem")
        explanation = _field(item, "explanation", 2500)
        choices = item.get("options")
        if (not isinstance(choices, list) or not 2 <= len(choices) <= 5
                or any(not isinstance(x, str) or not x.strip() or len(x) > 600 for x in choices)):
            raise QuizError(f"Question {uid}: options must be 2–5 non-empty strings.")
        if len({x.strip().casefold() for x in choices}) != len(choices):
            raise QuizError(f"Question {uid}: options must be distinct.")
        answer = item.get("correct_index")
        if type(answer) is not int or not 0 <= answer < len(choices):
            raise QuizError(f"Question {uid}: correct_index must point to an option (0-based).")
        source = item.get("source")
        if not isinstance(source, dict):
            raise QuizError(f"Question {uid}: source must contain name and location.")
        source_name = _field(source, "name", 240)
        location = _field(source, "location", 120)
        if (source_name, location) not in references:
            raise QuizError(
                f"Question {uid}: source '{source_name}, {location}' was not found in imported lectures."
            )
        normalized = json.dumps({
            "id": uid, "stem": stem, "options": choices,
            "correct_index": answer, "explanation": explanation,
            "source": [source_name, location],
        }, sort_keys=True, ensure_ascii=False)
        path_id = bank_path.relative_to(root).as_posix()
        digest = hashlib.sha256((path_id + "\n" + normalized).encode("utf-8")).hexdigest()[:24]
        questions.append(Question(uid, concept, stem,
                                  tuple(x.strip() for x in choices), answer,
                                  explanation, source_name, location, digest))
    return title, questions


def scaffold(topic: str, library: str | Path) -> Path:
    topic = topic.strip()
    if not topic or len(topic) > 120:
        raise QuizError("Topic must be 1–120 characters.")
    name = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")[:55] or "quiz"
    root = library_path(library)
    folder = root / "quizzes"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    if path.exists():
        raise QuizError(f"Quiz file already exists; refusing to overwrite: {path}")
    # Empty scaffold is intentionally not playable until the agent authors cited questions.
    path.write_text(json.dumps({"version": 1, "title": topic, "questions": []},
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _progress_path(library: str | Path) -> Path:
    return library_path(library) / "quiz-progress.json"


def read_progress(library: str | Path) -> dict:
    path = _progress_path(library)
    if not path.exists():
        return {"version": 1, "cards": {}}
    if path.stat().st_size > 10_000_000:
        raise QuizError("Progress file is too large.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise QuizError("Quiz progress file is damaged or unreadable.") from None
    if (not isinstance(value, dict) or value.get("version") != 1
            or not isinstance(value.get("cards"), dict)):
        raise QuizError("Unrecognized quiz progress format.")
    return value


def _save_progress(library: str | Path, progress: dict) -> None:
    root = library_path(library)
    root.mkdir(parents=True, exist_ok=True)
    dest = _progress_path(root)
    fd, temp = tempfile.mkstemp(prefix=".quiz-progress-", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(progress, out, indent=2, ensure_ascii=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def due(questions: list[Question], progress: dict, today: date | None = None) -> list[Question]:
    today = today or datetime.now(timezone.utc).date()
    records = progress["cards"]
    def due_date(q: Question) -> str:
        state = records.get(q.key)
        return str(state.get("due_date", "")) if isinstance(state, dict) else ""
    available = [q for q in questions if not due_date(q) or due_date(q) <= today.isoformat()]
    return sorted(available, key=lambda q: (due_date(q) or "0000-00-00", q.id))


def grade(progress: dict, question: Question, correct: bool, *,
          confident: bool = False, today: date | None = None) -> dict:
    """Small SM-2-inspired scheduler: missed=next day; first success=1 day;
    second success=6 days; later successes scale by ease.

    For medical competence, this is a *study reminder*, not a mastery certificate.
    """
    today = today or datetime.now(timezone.utc).date()
    existing = progress["cards"].get(question.key, {})
    repetitions = int(existing.get("repetitions", 0))
    interval = int(existing.get("interval_days", 0))
    ease = float(existing.get("ease", 2.5))
    attempts = int(existing.get("attempts", 0)) + 1
    misses = int(existing.get("misses", 0)) + (not correct)
    quality = 0 if not correct else (5 if confident else 3)
    ease = max(1.3, round(ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)), 2))
    if not correct:
        repetitions = 0
        interval = 1
    else:
        repetitions += 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = max(1, round(interval * ease))
    state = {
        "id": question.id, "concept": question.concept,
        "source": question.source, "location": question.location,
        "attempts": attempts, "misses": misses, "repetitions": repetitions,
        "interval_days": interval, "ease": ease,
        "last_correct": bool(correct), "last_reviewed": today.isoformat(),
        "due_date": (today + timedelta(days=interval)).isoformat(),
    }
    progress["cards"][question.key] = state
    return state


def run_quiz(
    questions: list[Question], library: str | Path, *,
    all_questions: bool = False, limit: int = 10,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    today: date | None = None,
) -> tuple[int, int]:
    if not 1 <= limit <= 100:
        raise QuizError("Quiz limit must be 1–100.")
    progress = read_progress(library)
    selected = (questions if all_questions else due(questions, progress, today))[:limit]
    correct_count = 0
    completed = 0
    if not selected:
        output_fn("No questions are due. Use 'quiz due' to check your next review.")
        return 0, 0
    for q in selected:
        output_fn(f"\n{completed + 1}/{len(selected)} — {q.concept}")
        output_fn(q.stem)
        for i, option in enumerate(q.options):
            output_fn(f"  {chr(65 + i)}. {option}")
        while True:
            choice = input_fn("Choose a letter (or q to quit): ").strip().casefold()
            if choice in {"q", "quit", "/quit", "exit"}:
                return correct_count, completed
            if len(choice) == 1 and "a" <= choice <= chr(96 + len(q.options)):
                break
            output_fn("Enter a valid option letter, or q to quit.")
        correct = ord(choice) - 97 == q.correct_index
        correct_count += int(correct)
        completed += 1
        output_fn("Correct." if correct else f"Not quite. Correct answer: {chr(65 + q.correct_index)}.")
        output_fn(f"Explanation: {q.explanation}")
        output_fn(f"Professor source: {q.source}, {q.location}")
        confident = False
        if correct:
            rating = input_fn("Confidence: [1] shaky / [2] confident (Enter = shaky): ").strip()
            confident = rating == "2"
        state = grade(progress, q, correct, confident=confident, today=today)
        _save_progress(library, progress)  # Persist each answer, including early exits.
        output_fn(f"Next review (UTC): {state['due_date']}")
    output_fn(f"Finished: {correct_count}/{completed} correct.")
    return correct_count, completed


def stats(questions: list[Question], progress: dict, today: date | None = None) -> dict:
    practiced = [q for q in questions if q.key in progress["cards"]]
    due_today = due(questions, progress, today)
    missed = [q for q in practiced if not progress["cards"][q.key]["last_correct"]]
    return {
        "questions": len(questions), "practiced": len(practiced),
        "new": len(questions) - len(practiced), "due": len(due_today),
        "last_attempt_incorrect": len(missed),
    }
