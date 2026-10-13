"""Step 4: offline source-grounded quizzes, local reviews and safety tests."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from mystudyai.cli import main
from mystudyai.quiz import (
    QuizError, scaffold, load_bank, grade, due, stats, read_progress, run_quiz,
)


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    p = root / "physiology-1234"
    p.mkdir(parents=True)
    (p / "document.json").write_text(json.dumps({
        "source_name": "Physiology.pptx",
        "source_sha256": "aabb",
        "blocks": [
            {"location": "slide 7", "text": "Heart rate multiplied by stroke volume is cardiac output."},
            {"location": "slide 8", "text": "Stroke volume is influenced by ventricular preload."},
        ],
        "figures": [],
    }), encoding="utf-8")
    return root


def bank_data():
    return {
        "version": 1, "title": "Heart physiology",
        "questions": [
            {
                "id": "heart-q1",
                "concept": "Cardiac output",
                "stem": "Which expression matches cardiac output?",
                "options": ["HR × SV", "HR + SV", "SV / HR", "HR / SV"],
                "correct_index": 0,
                "explanation": "Cardiac output depends on heart rate times stroke volume.",
                "source": {"name": "Physiology.pptx", "location": "slide 7"},
            },
            {
                "id": "heart-q2",
                "concept": "Ventricular preload",
                "stem": "Which property influences stroke volume?",
                "options": ["Skin color", "Ventricular preload"],
                "correct_index": 1,
                "explanation": "Preload changes ventricular filling and can affect stroke volume.",
                "source": {"name": "Physiology.pptx", "location": "slide 8"},
            },
        ],
    }


def write_bank(library, content=None):
    path = library / "quizzes" / "heart.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content if content is not None else bank_data()),
                    encoding="utf-8")
    return path


def test_scaffold_creates_private_editable_file_without_questions(library):
    path = scaffold("Heart Physiology", library)
    assert path == library / "quizzes" / "heart-physiology.json"
    assert json.loads(path.read_text())["questions"] == []
    with pytest.raises(QuizError, match="already exists"):
        scaffold("Heart Physiology", library)
    with pytest.raises(QuizError, match="1–500"):
        load_bank(path, library)  # Agent must fill before use.


def test_validate_cited_bank_and_stable_keys(library):
    bank = write_bank(library)
    title, questions = load_bank(bank, library)
    assert title == "Heart physiology"
    assert len(questions) == 2
    assert questions[0].source == "Physiology.pptx"
    assert questions[0].location == "slide 7"
    assert questions[0].key == load_bank(bank, library)[1][0].key


def test_reject_nonexistent_citation(library):
    data = bank_data()
    data["questions"][0]["source"]["location"] = "slide 99"
    with pytest.raises(QuizError, match="not found in imported lectures"):
        load_bank(write_bank(library, data), library)


@pytest.mark.parametrize("update,reason", [
    (lambda d: d["questions"][0].update({"correct_index": True}), "correct_index"),
    (lambda d: d["questions"][0].update({"correct_index": 5}), "correct_index"),
    (lambda d: d["questions"][0].update({"options": ["same", "same"]}), "distinct"),
    (lambda d: d["questions"][0].update({"options": ["one"]}), "options"),
    (lambda d: d["questions"][1].update({"id": "heart-q1"}), "Duplicate"),
    (lambda d: d["questions"][0].update({"id": "../../hack"}), "invalid id"),
])
def test_bank_validation_rejects_invalid_cards(library, update, reason):
    obj = bank_data()
    update(obj)
    with pytest.raises(QuizError, match=reason):
        load_bank(write_bank(library, obj), library)


def test_blocks_bank_outside_private_library(library, tmp_path):
    outside = tmp_path / "public-bank.json"
    outside.write_text(json.dumps(bank_data()))
    with pytest.raises(QuizError, match="inside library/quizzes"):
        load_bank(outside, library)


def test_content_edit_resets_card_key(library):
    bank = write_bank(library)
    old = load_bank(bank, library)[1][0].key
    obj = bank_data()
    obj["questions"][0]["stem"] += " (edited)"
    bank.write_text(json.dumps(obj))
    assert load_bank(bank, library)[1][0].key != old


def test_sm2_style_schedule_wrong_then_successes(library):
    q = load_bank(write_bank(library), library)[1][0]
    review = {"version": 1, "cards": {}}
    now = date(2026, 10, 13)
    assert due([q], review, now) == [q]
    a = grade(review, q, False, today=now)
    assert a["due_date"] == "2026-10-14"
    assert a["misses"] == 1 and a["repetitions"] == 0
    assert due([q], review, now) == []
    assert due([q], review, now + timedelta(days=1)) == [q]
    b = grade(review, q, True, today=now + timedelta(days=1))
    assert b["interval_days"] == 1 and b["repetitions"] == 1
    c = grade(review, q, True, today=now + timedelta(days=2), confident=True)
    assert c["interval_days"] == 6 and c["repetitions"] == 2
    d = grade(review, q, True, today=now + timedelta(days=8), confident=True)
    assert d["interval_days"] >= 7
    assert d["attempts"] == 4 and d["misses"] == 1
    assert d["ease"] >= 1.3


def test_run_grades_and_saves_each_answer(library):
    qs = load_bank(write_bank(library), library)[1]
    given = iter(["x", "a", "2", "a"])
    messages = []
    correct, completed = run_quiz(qs, library,
                                  input_fn=lambda _: next(given),
                                  output_fn=messages.append,
                                  today=date(2026, 10, 13))
    assert (correct, completed) == (1, 2)
    state = read_progress(library)
    assert len(state["cards"]) == 2
    assert stats(qs, state, date(2026, 10, 13)) == {
        "questions": 2, "practiced": 2, "new": 0, "due": 0,
        "last_attempt_incorrect": 1,
    }
    assert any("Enter a valid option" in x for x in messages)
    assert any("Correct answer: B" in x for x in messages)
    assert any("Professor source: Physiology.pptx, slide 8" in x for x in messages)
    assert all("OPENAI_API_KEY" not in x for x in messages)


def test_early_exit_preserves_previous_answer(library):
    qs = load_bank(write_bank(library), library)[1]
    given = iter(["a", "", "q"])
    right, completed = run_quiz(qs, library,
                                input_fn=lambda _: next(given),
                                output_fn=lambda _: None,
                                today=date(2026, 10, 13))
    assert (right, completed) == (1, 1)
    assert len(read_progress(library)["cards"]) == 1


def test_due_only_and_review_again(library):
    qs = load_bank(write_bank(library), library)[1]
    progress = {"version": 1, "cards": {}}
    grade(progress, qs[0], True, today=date(2026, 10, 13))
    assert due(qs, progress, date(2026, 10, 13)) == [qs[1]]
    assert {q.id for q in due(qs, progress, date(2026, 10, 14))} == {
        "heart-q1", "heart-q2",
    }


def test_cli_scaffold_validate_due_stats_and_errors(library, capsys):
    assert main(["quiz", "init", "Heart Physiology", "--library", str(library)]) == 0
    scaffold_path = library / "quizzes" / "heart-physiology.json"
    scaffold_path.write_text(json.dumps(bank_data()))
    assert main(["quiz", "validate", str(scaffold_path), "--library", str(library)]) == 0
    assert "2 questions" in capsys.readouterr().out
    assert main(["quiz", "due", str(scaffold_path), "--library", str(library)]) == 0
    assert "Due now (UTC): 2" in capsys.readouterr().out
    assert main(["quiz", "stats", str(scaffold_path), "--library", str(library)]) == 0
    assert "2 new" in capsys.readouterr().out
    assert main(["quiz", "mistakes", str(scaffold_path), "--library", str(library)]) == 0
    assert "Questions previously missed: 0" in capsys.readouterr().out
    assert main(["quiz", "validate", str(library / "quizzes" / "missing.json"),
                 "--library", str(library)]) == 1
    assert "Quiz error" in capsys.readouterr().err


def test_no_billed_api_used_by_quizzes(library, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError("quiz commands must never connect to the network")
                        ))
    bank = write_bank(library)
    assert main(["quiz", "validate", str(bank), "--library", str(library)]) == 0
    assert main(["quiz", "due", str(bank), "--library", str(library)]) == 0

def test_mistake_report_includes_source_citation(library, capsys):
    bank = write_bank(library)
    _, qs = load_bank(bank, library)
    inputs = iter(["b", "q"])
    run_quiz(qs, library, input_fn=lambda _: next(inputs),
             output_fn=lambda _: None, today=date(2026, 10, 13))
    assert main(["quiz", "mistakes", str(bank), "--library", str(library)]) == 0
    out = capsys.readouterr().out
    assert "Cardiac output" in out
    assert "1 misses" in out
    assert "slide 7" in out
