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

    args = parser.parse_args(argv)
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
