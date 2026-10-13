"""Command-line entry point for MyStudyAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ingest import import_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mystudyai", description="Course-first medical study toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import", help="Import a professor's lecture file")
    importer.add_argument("files", nargs="+", type=Path, help="PDF, PPTX, DOCX, MD or TXT")
    importer.add_argument("--library", type=Path, default=Path("library"), help="Where imported notes are stored")

    inspector = subparsers.add_parser("inspect", help="Show document provenance and import warnings")
    inspector.add_argument("folder", type=Path, help="Imported document folder")

    previews = subparsers.add_parser("sources", help="Preview lecture excerpts locally (no API request)")
    previews.add_argument("topic", help="Question or topic")
    previews.add_argument("--library", type=Path, default=Path("library"))

    figures_cmd = subparsers.add_parser("figures", help="Show relevant figures embedded in your lectures (offline)")
    figures_cmd.add_argument("topic")
    figures_cmd.add_argument("--library", type=Path, default=Path("library"))

    images_cmd = subparsers.add_parser("image-search", help="Search openly licensed Wikimedia Commons pictures")
    images_cmd.add_argument("topic")
    images_cmd.add_argument("--limit", type=int, default=8)
    images_cmd.add_argument("--library", type=Path, default=Path("library"))
    images_cmd.add_argument("--add-to", type=Path, help="Existing imported notes.md to append an image to")
    images_cmd.add_argument("--select", type=int, help="Image number in the current search results (1-based)")
    images_cmd.add_argument("--reviewed", action="store_true",
                            help="Confirm you reviewed medical relevance and the license on Commons")

    evidence_cmd = subparsers.add_parser("evidence", help="Look up PubMed records and abstracts")
    evidence_cmd.add_argument("topic")
    evidence_cmd.add_argument("--limit", type=int, default=4)

    for command in ("ask", "study"):
        tutor_cmd = subparsers.add_parser(command, help="Grounded medical tutor (requires explicit upload opt-in)")
        tutor_cmd.add_argument("topic", help="Your question (ask), or study topic (study)")
        tutor_cmd.add_argument("--library", type=Path, default=Path("library"))
        tutor_cmd.add_argument("--model", default="gpt-4.1-mini", help="OpenAI API model identifier")
        tutor_cmd.add_argument("--with-evidence", action="store_true",
                               help="Search PubMed abstracts to compare separately with lecture notes")
        tutor_cmd.add_argument("--send-notes", action="store_true",
                               help="Allow sending selected lecture excerpts to the OpenAI API")

    args = parser.parse_args(argv)
    if args.command == "figures":
        from .figures import nearby_figures
        figures = nearby_figures(args.library, args.topic)
        if not figures:
            print("No figures found near matching lecture text. Images without nearby selectable text may not appear.")
            return 0
        for figure in figures:
            print(f"{figure.source}, {figure.location}: {figure.path}")
        return 0

    if args.command == "image-search":
        from .commons import ImageSearchError, search_commons, add_image
        try:
            images = search_commons(args.topic, args.limit)
            if not images:
                print("No images with supported licenses and formats were found.")
                return 0
            for index, item in enumerate(images, start=1):
                print(f"{index}. {item.title}\n   Author: {item.author}\n"
                      f"   License: {item.license_name} {item.license_url}\n"
                      f"   File page: {item.file_page}")
            if args.add_to:
                if args.select is None or not (1 <= args.select <= len(images)):
                    print("Use --select N with an index shown above.", file=sys.stderr)
                    return 2
                path = add_image(images[args.select - 1], args.add_to, args.library,
                                 reviewed=args.reviewed)
                print(f"Appended reviewed image to notes; stored at {path}")
            elif args.select or args.reviewed:
                print("--select and --reviewed only apply together with --add-to.", file=sys.stderr)
                return 2
            return 0
        except (ImageSearchError, ValueError, OSError) as exc:
            print(f"Image error: {exc}", file=sys.stderr)
            return 1

    if args.command == "evidence":
        from .evidence import EvidenceError, search_pubmed
        try:
            papers = search_pubmed(args.topic, args.limit)
            if not papers:
                print("No PubMed records found.")
            for paper in papers:
                print(f"{paper.citation}\nAbstract: {paper.abstract or '(no abstract)'}\n")
            print("These records are candidates for manual review, not verified medical conclusions.")
            return 0
        except (EvidenceError, ValueError) as exc:
            print(f"Evidence error: {exc}", file=sys.stderr)
            return 1

    if args.command in {"sources", "ask", "study"}:
        from .retrieval import retrieve

        excerpts = retrieve(args.topic, args.library)
        if not excerpts:
            print("No matching imported lecture text found. Import notes first or try another topic.")
            return 1
        if args.command == "sources":
            for ex in excerpts:
                print(f"{ex.citation}\n  {ex.text[:320].replace(chr(10), ' ')}\n")
            return 0

        if not args.send_notes:
            print("No data sent. Preview selected excerpts using 'mystudyai sources TOPIC'.", file=sys.stderr)
            print("To send those excerpts to OpenAI, re-run with --send-notes.", file=sys.stderr)
            return 2
        from .model import ModelError, OpenAIResponsesClient
        from .tutor import MedicalTutor, interactive_study
        from .evidence import EvidenceError, search_pubmed

        try:
            papers = search_pubmed(args.topic) if args.with_evidence else []
            tutor = MedicalTutor(args.library, OpenAIResponsesClient(model=args.model), papers=papers)
            if args.command == "ask":
                print(tutor.answer(args.topic))
            else:
                interactive_study(tutor, args.topic)
        except (ModelError, EvidenceError, EOFError, KeyboardInterrupt) as exc:
            if isinstance(exc, (KeyboardInterrupt, EOFError)):
                print("\nStudy session ended.", file=sys.stderr)
            else:
                print(f"Tutor error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "import":
        failures = 0
        for source in args.files:
            try:
                output = import_document(source, args.library)
                print(f"Imported {source.name} → {output}")
                print(f"  Notes: {output / 'notes.md'}")
            except (OSError, ValueError, RuntimeError) as exc:
                failures += 1
                print(f"Failed to import {source}: {exc}", file=sys.stderr)
        return 1 if failures else 0

    try:
        obj = json.loads((args.folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Cannot inspect {args.folder}: {exc}", file=sys.stderr)
        return 1
    print(f"Source: {obj['source_name']} ({obj['source_type']})")
    print(f"Text blocks: {len(obj['blocks'])}; embedded figures: {len(obj['figures'])}")
    for warning in obj.get("warnings", []):
        print(f"Warning: {warning}")
    return 0
