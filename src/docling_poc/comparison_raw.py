"""Read current plain JSON outputs and legacy gzip benchmark outputs."""

import gzip
from pathlib import Path


def raw_result_path(directory: Path) -> Path:
    path = directory / "raw.pretty.json"
    return path if path.is_file() else directory / "raw.json.gz"


def read_raw_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8")
