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

    for command in ("ask", "study"):
        tutor_cmd = subparsers.add_parser(command, help="Grounded medical tutor (requires explicit upload opt-in)")
        tutor_cmd.add_argument("topic", help="Your question (ask), or study topic (study)")
        tutor_cmd.add_argument("--library", type=Path, default=Path("library"))
        tutor_cmd.add_argument("--model", default="gpt-4.1-mini", help="OpenAI API model identifier")
        tutor_cmd.add_argument("--send-notes", action="store_true",
                               help="Allow sending selected lecture excerpts to the OpenAI API")

    args = parser.parse_args(argv)
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

        try:
            tutor = MedicalTutor(args.library, OpenAIResponsesClient(model=args.model))
            if args.command == "ask":
                print(tutor.answer(args.topic))
            else:
                interactive_study(tutor, args.topic)
        except (ModelError, EOFError, KeyboardInterrupt) as exc:
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
