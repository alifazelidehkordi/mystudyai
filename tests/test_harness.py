"""No-API harness integration contract: the agent harness handles all reasoning."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from mystudyai.cli import main


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def library(tmp_path):
    notes = tmp_path / "library" / "heart-example"
    notes.mkdir(parents=True)
    (notes / "document.json").write_text(json.dumps({
        "source_name": "Professor Physiology.pdf",
        "source_sha256": "0123456789abcdef",
        "blocks": [
            {"location": "page 4", "text":
             "Cardiac output is heart rate multiplied by stroke volume. "
             "Mechanism: preload influences stroke volume according to Frank-Starling. "
             + "Physiology explanation. " * 25},
            {"location": "page 5", "text":
             "The heart pumps blood to pulmonary and systemic circulations."}
        ],
        "figures": [], "warnings": []
    }), encoding="utf-8")
    return tmp_path / "library"


def test_context_prints_full_cited_passages_no_network(library, monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("Local study context tried to contact a network service")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    assert main(["context", "cardiac output", "--library", str(library)]) == 0
    result = capsys.readouterr().out
    assert "[S1] Professor Physiology.pdf, page 4" in result
    assert "Physiology explanation. " * 10 in result
    assert "<untrusted_lecture_excerpt>" in result
    assert "no model API was contacted" in result


def test_context_rejects_bad_limit_without_network(library, capsys):
    assert main(["context", "cardiac output", "--library", str(library),
                 "--limit", "11"]) == 2
    assert "--limit must be" in capsys.readouterr().err


def test_context_no_notes_is_clear(tmp_path, capsys):
    assert main(["context", "cardiac output", "--library", str(tmp_path)]) == 1
    assert "No matching imported lecture text" in capsys.readouterr().out


def test_no_billed_model_commands_exist():
    with pytest.raises(SystemExit) as error:
        main(["ask", "cardiac output", "--send-notes"])
    assert error.value.code == 2


def test_skills_mirrored_for_codex_and_pi():
    codex_skill = PROJECT / ".agents/skills/medical-study/SKILL.md"
    pi_skill = PROJECT / ".pi/skills/medical-study/SKILL.md"
    assert codex_skill.read_text() == pi_skill.read_text()
    text = codex_skill.read_text()
    assert "name: medical-study" in text
    assert "mystudyai context" in text
    assert "probe" in text.casefold()
    assert "api key" in text.casefold()
    assert (PROJECT / "AGENTS.md").is_file()


def test_no_app_owned_llm_api_client():
    src = PROJECT / "src/mystudyai"
    assert not (src / "model.py").exists()
    assert not (src / "tutor.py").exists()
    assert "api.openai.com" not in (src / "cli.py").read_text()
    assert "OPENAI_API_KEY" not in (src / "cli.py").read_text()
