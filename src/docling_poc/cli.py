from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from docling_poc.docling_raw import (
    conversion_error_details,
    conversion_status,
    convert_document,
    create_hierarchical_chunks,
    export_document,
    export_hierarchical_chunks,
)
from docling_poc.semantic import build_semantic_document, matches_semantic_rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Docling document representations.")
    parser.add_argument(
        "source",
        type=Path,
        help="Source document, or a Docling JSON export for semantic output modes.",
    )
    parser.add_argument("--out", type=Path, help="Output path. Defaults to stdout.")
    parser.add_argument(
        "--to",
        choices=("json", "markdown", "hierarchical-chunks", "semantic-json", "semantic-rules"),
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--ocr-pictures",
        action="store_true",
        help="OCR embedded picture data URIs with RapidOCR (semantic-json only).",
    )
    parser.add_argument(
        "--picture-classifier",
        action="store_true",
        help="Classify PDF pictures with Docling's picture classifier.",
    )
    parser.add_argument(
        "--picture-desc",
        action="store_true",
        help="Generate PDF picture descriptions with Docling's vision-language model.",
    )
    parser.add_argument("--max-num-pages", type=int, help="Maximum pages or slides to process.")
    parser.add_argument("--max-file-size", type=int, help="Maximum input size in bytes.")
    args = parser.parse_args()
    if args.out and args.out.resolve() == args.source.resolve():
        parser.error("--out must be different from the source document path.")
    if args.ocr_pictures and args.to != "semantic-json":
        parser.error("--ocr-pictures can only be used with --to semantic-json.")
    if (args.picture_classifier or args.picture_desc) and (
        args.to in {"semantic-json", "semantic-rules"} or args.source.suffix.lower() != ".pdf"
    ):
        parser.error("--picture-classifier and --picture-desc require PDF conversion output.")

    if args.to in {"semantic-json", "semantic-rules"}:
        try:
            if args.max_file_size is not None and args.source.stat().st_size > args.max_file_size:
                raise ValueError(f"Input file exceeds --max-file-size ({args.max_file_size} bytes).")
            with args.source.open(encoding="utf-8") as source_file:
                document_json = json.load(source_file)
            if not isinstance(document_json, dict):
                raise TypeError("Docling JSON root must be an object.")
            exported = (
                build_semantic_document(document_json, ocr_pictures=args.ocr_pictures)
                if args.to == "semantic-json"
                else matches_semantic_rules(document_json)
            )
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            action = "build semantic JSON" if args.to == "semantic-json" else "evaluate semantic rules"
            parser.error(f"Could not {action}: {exc}")
    else:
        result = convert_document(
            args.source,
            max_num_pages=args.max_num_pages,
            max_file_size=args.max_file_size,
            picture_classifier=args.picture_classifier,
            picture_desc=args.picture_desc,
        )
        if conversion_status(result) not in {"success", "partial_success"}:
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


def _conversion_failure_message(result: object) -> str:
    details = conversion_error_details(result)
    return f"Docling conversion failed ({conversion_status(result)}): {details or 'no error details'}"


if __name__ == "__main__":
    main()
