from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from docling_poc.processor import DoclingProcessConfig, process_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a document with Docling into AI-ready JSON.")
    parser.add_argument("source", type=Path, help="PDF, PPT/PPTX, DOC/DOCX file to parse.")
    parser.add_argument("--out", type=Path, help="Output JSON path. Defaults to stdout.")
    parser.add_argument("--max-chunk-chars", type=int, default=DoclingProcessConfig.max_chunk_chars)
    parser.add_argument("--min-chunk-chars", type=int, default=DoclingProcessConfig.min_chunk_chars)
    parser.add_argument("--ocr-lang", action="append", dest="ocr_languages", default=[])
    parser.add_argument("--disable-ocr", action="store_true")
    args = parser.parse_args()
    if args.out and args.out.resolve() == args.source.resolve():
        parser.error("--out must be different from the source document path.")

    config = DoclingProcessConfig(
        max_chunk_chars=args.max_chunk_chars,
        min_chunk_chars=args.min_chunk_chars,
        enable_ocr=not args.disable_ocr,
        ocr_languages=tuple(args.ocr_languages) or DoclingProcessConfig.ocr_languages,
    )
    processed = process_document(args.source, config=config)
    payload = json.dumps(processed.to_dict(), ensure_ascii=False, indent=2)

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


if __name__ == "__main__":
    main()
