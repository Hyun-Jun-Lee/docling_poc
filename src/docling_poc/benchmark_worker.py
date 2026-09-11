"""One fresh process per extraction; uses the project's native Tesseract paths."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import subprocess
import sys
import traceback
from pathlib import Path


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(json_safe(data), ensure_ascii=False, indent=2,
                               allow_nan=False), encoding="utf-8")


def run_docling(args):
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat

    from docling_poc.docling_raw import (
        build_docling_converter,
        conversion_status,
        export_conversion_result,
    )

    converter = build_docling_converter()
    options = converter.format_to_options[InputFormat.PDF].pipeline_options
    options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CPU, num_threads=args.threads
    )
    result = converter.convert(args.source, raises_on_error=False)
    status = conversion_status(result)
    raw = export_conversion_result(result)
    markdown = result.document.export_to_markdown()
    times = raw.get("timings", {}).get("pipeline_total", {}).get("times", [])
    return raw, markdown, {
        "status": status, "errors": [str(e) for e in result.errors],
        "internal_seconds": sum(times) if times else None,
        "internal_scope": "Docling timings.pipeline_total.times (seconds)",
        "ocr_options": options.ocr_options.model_dump(mode="json"),
        "ocr_scope": "PDF native region selection; Office native parser (no added image OCR)",
    }


def run_tika(args):
    command = [args.java, "-Dfile.encoding=UTF-8", "-jar", args.jar,
               "--config=" + args.config, "--jsonRecursive", "--pretty-print",
               "--encoding=UTF-8", str(args.source)]
    with (args.output / "tika-output.json").open("wb") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=sys.stderr,
                                   cwd=Path(args.jar).parent, check=False)
    if completed.returncode:
        raise RuntimeError(f"Tika process exited with code {completed.returncode}; see worker.log")
    raw = json.loads((args.output / "tika-output.json").read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Tika recursive output is not a nonempty array")
    errors = [{"item": i, "key": k, "value": v}
              for i, item in enumerate(raw) for k, v in item.items()
              if ("exception" in k.lower() or "limit-reached" in k.lower())
              and v not in (False, "false", [], "", None)]
    root = raw[0]
    millis = root.get("tk:parse-time-millis", root.get("X-TIKA:parse_time_millis"))
    return raw, root.get("tk:content", root.get("X-TIKA:content", "")), {
        "status": "partial_success" if errors else "success", "errors": errors,
        "internal_seconds": float(millis) / 1000 if millis is not None else None,
        "internal_scope": "Tika root parse time including embedded parsing; excludes JVM startup",
        "ocr_pages": root.get("pdf:ocr-page-count"),
        "ocr_scope": "Tika native Tesseract; PDF AUTO, 216 DPI RGB; embedded parsing enabled",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", choices=["tika", "docling"], required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--java")
    parser.add_argument("--jar")
    parser.add_argument("--config")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        raw, markdown, metadata = run_tika(args) if args.tool == "tika" else run_docling(args)
        with gzip.open(args.output / "raw.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(json_safe(raw), stream, ensure_ascii=False, allow_nan=False)
        (args.output / "content.md").write_text(markdown, encoding="utf-8")
        write_json(args.output / "run.json", metadata)
        raise SystemExit(0 if metadata["status"] in {"success", "partial_success"} else 1)
    except Exception as exc:  # noqa: BLE001 - preserve errors from optional native dependencies
        traceback.print_exc()
        write_json(args.output / "run.json", {"status": "failure", "error": str(exc)})
        raise SystemExit(1)


if __name__ == "__main__":
    main()
