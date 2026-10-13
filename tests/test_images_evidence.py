"""Step 3: test source linking, safe image insertion and PubMed provenance."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from mystudyai import commons, evidence
from mystudyai.cli import main
from mystudyai.commons import CommonsImage, ImageSearchError, add_image, allowed_license, search_commons
from mystudyai.evidence import EvidenceError, Paper, format_papers, search_pubmed
from mystudyai.figures import nearby_figures
from mystudyai.tutor import MedicalTutor


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    folder = root / "heart-abc"
    (folder / "images").mkdir(parents=True)
    (folder / "images" / "heart.png").write_bytes(b"\x89PNG\r\n\x1a\nsample")
    (folder / "notes.md").write_text("# Heart\n", encoding="utf-8")
    (folder / "document.json").write_text(json.dumps({
        "source_name": "Heart.pptx", "source_sha256": "abc",
        "blocks": [
            {"location": "slide 3", "text": "The left ventricle ejects blood to the aorta."},
            {"location": "slide 4", "text": "The pulmonary artery carries blood to the lungs."}
        ],
        "figures": [
            {"location": "slide 3", "path": "images/heart.png", "sha256": "fake", "mime_type": "image/png"},
            {"location": "slide 4", "path": "../../outside.png", "sha256": "fake", "mime_type": "image/png"},
        ]
    }), encoding="utf-8")
    return root


def sample_commons_image():
    return CommonsImage(
        "File:Heart.png", "https://commons.wikimedia.org/wiki/File:Heart.png",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/heart.png",
        "Dr. Example", "CC BY-SA 4.0",
        "https://creativecommons.org/licenses/by-sa/4.0/", "image/png",
        "An illustration of a heart",
    )


def test_nearby_figures_uses_exact_slide_and_ignores_escaping_paths(library, tmp_path):
    (tmp_path / "outside.png").write_bytes(b"test")
    figures = nearby_figures(library, "left ventricle")
    assert len(figures) == 1
    assert figures[0].source == "Heart.pptx"
    assert figures[0].location == "slide 3"
    assert figures[0].path.name == "heart.png"
    assert "file://" in figures[0].markdown()
    assert nearby_figures(library, "pulmonary artery") == []


def test_cli_figures_stays_local(library, capsys):
    assert main(["figures", "left ventricle", "--library", str(library)]) == 0
    assert "Heart.pptx, slide 3:" in capsys.readouterr().out


def test_license_allowlist_rejects_restricted_images():
    for value in ["CC BY 4.0", "CC BY-SA 4.0", "CC0 1.0", "Public domain", "CC-BY-SA-3.0"]:
        assert allowed_license(value), value
    for value in ["", "All rights reserved", "CC BY-NC 4.0", "CC BY-ND 4.0", "unknown"]:
        assert not allowed_license(value), value


def test_commons_search_filters_license_and_attributes(monkeypatch):
    data = {"query": {"pages": [
        {"title": "File:Heart.png", "imageinfo": [{
            "mime": "image/png",
            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/test.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Heart.png",
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                "Artist": {"value": '<a href="/wiki/Doctor">Doctor</a> Example'},
                "ImageDescription": {"value": "Heart &amp; aorta"},
            }
        }]},
        {"title": "File:Restricted.jpg", "imageinfo": [{
            "mime": "image/jpeg",
            "thumburl": "https://upload.wikimedia.org/restricted.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Restricted.jpg",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 4.0"}}
        }]},
        {"title": "File:WrongHost.png", "imageinfo": [{
            "mime": "image/png",
            "thumburl": "https://evil.test/image.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:WrongHost.png",
            "extmetadata": {"LicenseShortName": {"value": "CC0 1.0"}}
        }]}
    ]}}
    monkeypatch.setattr(commons, "_json_get", lambda url: data)
    found = search_commons("heart anatomy")
    assert len(found) == 1
    assert found[0].author == "Doctor Example"
    assert found[0].description == "Heart & aorta"


class FakeResponse:
    def __init__(self, data, mime="image/png"):
        self.data = data
        self.headers = type("Headers", (), {"get_content_type": lambda self: mime})()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit=-1):
        return self.data[:limit] if limit != -1 else self.data


def test_add_commons_image_requires_explicit_review_and_appends_credit(library, monkeypatch):
    note = library / "heart-abc" / "notes.md"
    image = sample_commons_image()
    with pytest.raises(ValueError, match="--reviewed"):
        add_image(image, note, library)
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"a" * 90
    monkeypatch.setattr(commons, "urlopen", lambda request, timeout: FakeResponse(image_bytes))
    saved = add_image(image, note, library, reviewed=True)
    assert saved.is_file()
    text = note.read_text()
    assert "Dr. Example" in text and "CC BY-SA 4.0" in text
    assert "commons.wikimedia.org" in text and "not independently verified" in text


def test_reject_image_mime_lie_and_writes_nothing(library, monkeypatch):
    note = library / "heart-abc" / "notes.md"
    before = note.read_text()
    monkeypatch.setattr(commons, "urlopen", lambda *args, **kwargs: FakeResponse(b"some dangerous text"))
    with pytest.raises(ImageSearchError, match="does not match"):
        add_image(sample_commons_image(), note, library, reviewed=True)
    assert note.read_text() == before


def test_reject_note_outside_library(library, tmp_path):
    note = tmp_path / "outside.md"
    note.write_text("Cannot modify")
    with pytest.raises(ValueError, match="inside"):
        add_image(sample_commons_image(), note, library, reviewed=True)


def test_pubmed_search_xml_and_pmids(monkeypatch):
    xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation>
    <PMID>123456</PMID><Article><ArticleTitle>The left ventricle and cardiac output</ArticleTitle>
    <Journal><Title>Journal of Anatomy</Title><JournalIssue><PubDate><Year>2023</Year></PubDate></JournalIssue></Journal>
    <Abstract><AbstractText Label="Background">Cardiac output depends on stroke volume.</AbstractText>
    <AbstractText Label="Results">The heart pumps blood.</AbstractText></Abstract>
    </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""
    calls = []
    def mock_download(endpoint, params):
        calls.append((endpoint, params))
        if endpoint == "esearch.fcgi":
            return json.dumps({"esearchresult": {"idlist": ["123456"]}}).encode()
        return xml
    monkeypatch.setattr(evidence, "_download", mock_download)
    papers = search_pubmed("cardiac output")
    assert len(papers) == 1
    assert papers[0].ref == "P1"
    assert papers[0].pmid == "123456"
    assert "2023" in papers[0].citation
    assert "Cardiac output" in papers[0].abstract
    assert "pubmed.ncbi.nlm.nih.gov/123456/" in format_papers(papers)
    assert calls[0][1]["term"] == "cardiac output"  # query only; never notes


def test_pubmed_rejects_unsafe_xml(monkeypatch):
    monkeypatch.setattr(evidence, "_download", lambda endpoint, params:
        json.dumps({"esearchresult": {"idlist": ["123"]}}).encode()
        if endpoint.startswith("esearch") else b"<!DOCTYPE fake [<!ENTITY x 'bad'>]><root/>")
    with pytest.raises(EvidenceError, match="Unsafe"):
        search_pubmed("heart")


def test_tutor_external_citations_and_local_figures(library):
    paper = Paper("P1", "123456", "Paper about cardiac function",
                  "Example Journal", "2024", "The paper examines cardiac output.")
    class Model:
        def complete(self, instructions, prompt):
            assert "EXTERNAL SCIENTIFIC LITERATURE" in prompt
            assert "[P1]" in prompt
            return "Your lecture discusses the ventricle [S1]. An article discusses cardiac output [P1]. Bad source [P999]."
    reply = MedicalTutor(library, Model(), papers=[paper]).answer("left ventricle")
    assert "[P1]" in reply
    assert "[P999]" not in reply
    assert "123456" in reply
    assert "heart.png" in reply


def test_evidence_cli_uses_mocked_pubmed(monkeypatch, capsys):
    monkeypatch.setattr(evidence, "search_pubmed",
                        lambda topic, limit: [Paper("P1", "123", "Title", "J", "2020", "Abstract")])
    assert main(["evidence", "cardiac output"]) == 0
    output = capsys.readouterr().out
    assert "PMID: 123" in output
    assert "not verified medical conclusions" in output
