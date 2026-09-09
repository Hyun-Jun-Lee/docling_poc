from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from docling_poc.docling_raw import (
    convert_document,
    create_hierarchical_chunks,
    export_document,
    export_hierarchical_chunks,
)
from docling_poc.semantic import build_semantic_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Docling document representations.")
    parser.add_argument(
        "source",
        type=Path,
        help="Source document, or a Docling JSON export when --to semantic-json is selected.",
    )
    parser.add_argument("--out", type=Path, help="Output path. Defaults to stdout.")
    parser.add_argument(
        "--to",
        choices=("json", "markdown", "hierarchical-chunks", "semantic-json"),
        default="json",
        help="Output format.",
    )
    parser.add_argument("--max-num-pages", type=int, help="Maximum pages or slides to process.")
    parser.add_argument("--max-file-size", type=int, help="Maximum input size in bytes.")
    args = parser.parse_args()
    if args.out and args.out.resolve() == args.source.resolve():
        parser.error("--out must be different from the source document path.")

    if args.to == "semantic-json":
        try:
            with args.source.open(encoding="utf-8") as source_file:
                document_json = json.load(source_file)
            if not isinstance(document_json, dict):
                raise TypeError("Docling JSON root must be an object.")
            exported = build_semantic_document(document_json)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f"Could not build semantic JSON: {exc}")
    else:
        result = convert_document(
            args.source,
            max_num_pages=args.max_num_pages,
            max_file_size=args.max_file_size,
        )
        if _conversion_status(result) not in {"success", "partial_success"}:
            parser.error(_conversion_failure_message(result))

        if args.to == "hierarchical-chunks":
            exported = export_hierarchical_chunks(create_hierarchical_chunks(result.document))
        else:
            exported = export_document(result.document, output_format=args.to)

    payload = json.dumps(exported, ensure_ascii=False, indent=2) if args.to != "markdown" else exported

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=args.out.parent,
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)
        os.replace(temp_path, args.out)
    else:
        print(payload)


def _conversion_status(result: object) -> str:
    status = getattr(result, "status", "unknown")
    return str(getattr(status, "value", status)).lower()


def _conversion_failure_message(result: object) -> str:
    errors = getattr(result, "errors", None) or []
    messages = [
        str(getattr(error, "error_message", getattr(error, "message", error)))
        for error in errors
    ]
    details = "; ".join(message for message in messages if message)
    return f"Docling conversion failed ({_conversion_status(result)}): {details or 'no error details'}"


if __name__ == "__main__":
    main()
