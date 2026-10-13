"""PubMed literature discovery for checking medical explanations against research.

Finding an abstract is NOT scientific verification. Students must check quality,
relevance, methods and full text before relying on a paper.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
USER_AGENT = "MyStudyAI/0.3 (medical education literature lookup)"
MAX_BYTES = 2_000_000


class EvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paper:
    ref: str
    pmid: str
    title: str
    journal: str
    year: str
    abstract: str

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    @property
    def citation(self) -> str:
        return f"[{self.ref}] {self.title} ({self.journal}, {self.year}). PMID: {self.pmid}. {self.url}"


def _download(path: str, params: dict[str, str]) -> bytes:
    request = Request(BASE + path + "?" + urlencode(params),
                      headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(MAX_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise EvidenceError("PubMed request failed. Check the network or try again.") from None
    if len(data) > MAX_BYTES:
        raise EvidenceError("PubMed response exceeded the size limit.")
    return data


def _flatten(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def search_pubmed(topic: str, limit: int = 4) -> list[Paper]:
    """Retrieve PubMed abstracts without transmitting professor course content."""
    if not topic.strip() or len(topic) > 180:
        raise ValueError("PubMed topic must be 1–180 characters.")
    if not 1 <= limit <= 8:
        raise ValueError("PubMed limit must be between 1 and 8.")
    try:
        hits = json.loads(_download("esearch.fcgi", {
            "db": "pubmed", "term": topic, "retmode": "json",
            "retmax": str(limit), "sort": "relevance", "tool": "mystudyai"
        }))
        ids = [str(x) for x in hits["esearchresult"]["idlist"] if str(x).isdigit()][:limit]
    except (ValueError, TypeError, KeyError):
        raise EvidenceError("Invalid PubMed search response.") from None
    if not ids:
        return []
    raw = _download("efetch.fcgi", {
        "db": "pubmed", "id": ",".join(ids), "retmode": "xml",
        "tool": "mystudyai"
    })
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise EvidenceError("Unsafe PubMed XML response.")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise EvidenceError("Invalid PubMed article response.") from None
    indexed: dict[str, Paper] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = _flatten(article.find("./MedlineCitation/PMID"))
        if pmid not in ids:
            continue
        med = article.find("./MedlineCitation/Article")
        if med is None:
            continue
        abstract = " ".join(
            _flatten(node) for node in med.findall("./Abstract/AbstractText")
        ).strip()
        pubdate = med.find("./Journal/JournalIssue/PubDate")
        year = _flatten(pubdate.find("Year")) if pubdate is not None else ""
        if not year and pubdate is not None:
            year = _flatten(pubdate.find("MedlineDate"))[:30]
        indexed[pmid] = Paper(
            ref="", pmid=pmid,
            title=_flatten(med.find("./ArticleTitle"))[:400],
            journal=_flatten(med.find("./Journal/Title"))[:200],
            year=year[:30] or "date unknown",
            abstract=abstract[:3500],
        )
    articles: list[Paper] = []
    for pid in ids:
        if pid in indexed:
            paper = indexed[pid]
            articles.append(Paper(f"P{len(articles) + 1}", paper.pmid,
                                  paper.title, paper.journal, paper.year, paper.abstract))
    return articles


def format_papers(papers: list[Paper]) -> str:
    return "\n\n".join(
        f"{paper.citation}\n<external_pubmed_abstract>\n"
        f"{paper.abstract or '(No abstract provided; only bibliographic metadata is available.)'}"
        "\n</external_pubmed_abstract>"
        for paper in papers
    )
