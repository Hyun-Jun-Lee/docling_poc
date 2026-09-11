"""Offline, resumable serial extraction benchmark. Run with python -m docling_poc.comparison."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from docling_poc.benchmark_worker import write_json
from docling_poc.comparison_data import docling_snapshot, tika_snapshot

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def find_java():
    java = shutil.which("java")
    if java:
        return java
    candidates = []
    if os.getenv("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]) / "bin/java.exe")
    if os.name == "nt":
        import winreg

        for hive, subkey in ((winreg.HKEY_CURRENT_USER, "Environment"),
                             (winreg.HKEY_LOCAL_MACHINE,
                              r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    try:
                        home = winreg.QueryValueEx(key, "JAVA_HOME")[0]
                        candidates.append(Path(home) / "bin/java.exe")
                    except OSError:
                        pass
                    try:
                        path = winreg.QueryValueEx(key, "Path")[0]
                        candidates.extend(Path(os.path.expandvars(p.strip('"'))) / "java.exe"
                                          for p in path.split(";") if p)
                    except OSError:
                        pass
            except OSError:
                pass
    return str(next((p for p in candidates if p.is_file()), "java"))


def version(command):
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        return (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"


def kill_tree(process):
    import psutil

    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
        psutil.wait_procs(children + [parent], timeout=10)
    except psutil.NoSuchProcess:
        pass


def execute(command, directory, timeout, env):
    started = time.perf_counter()
    with (directory / "worker.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(process)
            code = process.wait()
        except BaseException:
            kill_tree(process)
            process.wait()
            raise
    elapsed = time.perf_counter() - started
    path = directory / "run.json"
    metadata = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if timed_out or code != 0:
        metadata.update(status="failure", error="timeout" if timed_out else
                        metadata.get("error", f"process exit {code}"))
    metadata.update(total_seconds=elapsed, exit_code=code, timeout=timed_out,
                    total_scope="fresh worker startup through raw JSON/Markdown save and process exit")
    write_json(path, metadata)
    return metadata


def save_manifest(output, manifest):
    path = output / "manifest.new.json"
    write_json(path, manifest)
    os.replace(path, output / "manifest.json")


def validate_ocr_config(config):
    """Read the actual Docling settings and reject a different Tika OCR setup."""
    from docling_poc.docling_raw import build_tesseract_ocr_options

    options = build_tesseract_ocr_options()
    tika = next(p["tesseract-ocr-parser"] for p in config["parsers"]
                if "tesseract-ocr-parser" in p)
    command, data = Path(options.tesseract_cmd), Path(options.path)
    same = (
        (Path(tika["tesseractPath"]) / command.name).resolve() == command.resolve()
        and Path(tika["tessdataPath"]).resolve() == data.resolve()
        and sorted(tika["language"].split("+")) == sorted(options.lang)
        and str(tika["pageSegMode"]) == str(options.psm)
        and tika.get("skipOcr") is False
    )
    if not same:
        raise ValueError("Tika and Docling Tesseract paths/languages/PSM must match")
    return command, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "samples")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds per tool/document/run")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--java", default=find_java())
    parser.add_argument("--jar", type=Path, default=ROOT / "tika-app-4.0.0/tika-app-4.0.0.jar")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if min(args.repeat, args.timeout, args.threads) < 1:
        parser.error("repeat, timeout and threads must be positive")
    if args.resume and args.output is None:
        parser.error("--resume requires --output")
    load_dotenv(ROOT / ".env", override=False)
    output = (args.output or ROOT / "reports" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")).resolve()
    config = ROOT / "tika-config.json"
    tika_config = json.loads(config.read_text(encoding="utf-8"))
    tesseract, tessdata_dir = validate_ocr_config(tika_config)
    code_hashes = {p.name: sha256(p) for p in (Path(__file__),
                  Path(__file__).with_name("benchmark_worker.py"),
                  Path(__file__).with_name("comparison_data.py"),
                  Path(__file__).with_name("docling_raw.py"))}
    if args.resume:
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if manifest["settings"]["code_hashes"] != code_hashes:
            parser.error("Worker/runner code changed: use a new output directory")
        if manifest["settings"]["tika_config"] != tika_config:
            parser.error("Tika configuration changed: use a new output directory")
        if args.repeat != manifest["settings"]["repeat"] or args.threads != manifest["settings"]["threads"]:
            parser.error("Resume requires the original repeat and threads values")
        settings = manifest["settings"]
        if sha256(args.jar) != settings["tika_jar_sha256"]:
            parser.error("Tika JAR changed: use a new output directory")
        for name, expected in settings["packages"].items():
            try:
                actual = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                actual = None
            if actual != expected:
                parser.error(f"Package changed: {name}; use a new output directory")
        model_root = Path(os.environ.get("DOCLING_ARTIFACTS_PATH", Path.home() / ".cache/docling/models"))
        for relative, expected in settings["model_sha256"].items():
            if sha256(model_root / relative) != expected:
                parser.error("Model changed: use a new output directory")
        for name, expected in settings["tessdata_sha256"].items():
            if sha256(tessdata_dir / name) != expected:
                parser.error("Tessdata changed: use a new output directory")
        if version([args.java, "-version"]) != settings["java"] or version(
                [str(tesseract), "--version"]
        ) != settings["tesseract"]:
            parser.error("Java/Tesseract changed: use a new output directory")
    else:
        if output.exists() and any(output.iterdir()):
            parser.error("Output is not empty; use a new directory or --resume")
        source = args.input.resolve()
        sources = ([source] if source.is_file() else sorted(
            p for p in source.rglob("*") if p.is_file()
            and p.suffix.lower() in {".pdf", ".docx", ".pptx"}))
        if not sources or any(p.suffix.lower() not in {".pdf", ".docx", ".pptx"} for p in sources):
            parser.error("No PDF/DOCX/PPTX inputs found")
        output.mkdir(parents=True, exist_ok=True)
        model_root = Path(os.environ.get("DOCLING_ARTIFACTS_PATH", Path.home() / ".cache/docling/models"))
        models = {str(p.relative_to(model_root)): sha256(p) for p in model_root.rglob("*")
                  if p.is_file() and p.suffix in {".safetensors", ".onnx", ".json"}
                  and ".cache" not in p.parts}
        tessdata = {p.name: sha256(p) for p in tessdata_dir.glob("*.traineddata")}
        packages = {}
        for name in ("docling", "docling-core", "torch", "python-dotenv", "onnxruntime", "psutil"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = None
        manifest = {"schema_version": 1, "created": datetime.now(UTC).isoformat(),
                    "settings": {"repeat": args.repeat, "threads": args.threads,
                    "timeout_seconds": args.timeout, "python": sys.version,
                    "platform": platform.platform(), "cpu": platform.processor(),
                    "packages": packages, "java": version([args.java, "-version"]),
                    "tesseract": version([str(tesseract), "--version"]),
                    "tessdata_sha256": tessdata, "model_sha256": models,
                    "artifacts_path": str(model_root), "code_hashes": code_hashes,
                    "tika_jar_sha256": sha256(args.jar),
                    "tika_config": tika_config,
                    "order": "serial; alternate tool order per repetition; fresh process each time",
                    "warmup": "none; run 1 separately visible; all five retained"}, "documents": []}
        archive = output / "execution-code"
        archive.mkdir()
        for name in code_hashes:
            shutil.copy2(Path(__file__).with_name(name), archive / name)
        for i, source in enumerate(sources, 1):
            folder = output / f"document-{i:03}"
            (folder / "input").mkdir(parents=True)
            target = folder / "input" / source.name
            shutil.copy2(source, target)
            manifest["documents"].append({"id": folder.name, "name": source.name,
                                          "sha256": sha256(source), "bytes": source.stat().st_size,
                                          "source": target.relative_to(output).as_posix(),
                                          "runs": {"tika": [], "docling": []}})
        save_manifest(output, manifest)
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE="1", OMP_NUM_THREADS=str(args.threads),
               OMP_THREAD_LIMIT=str(args.threads), PYTHONIOENCODING="utf-8")
    for doc in manifest["documents"]:
        source = output / doc["source"]
        if sha256(source) != doc["sha256"]:
            raise ValueError(f"Input copy changed: {source}")
        for run in range(1, args.repeat + 1):
            for tool in (["tika", "docling"] if run % 2 else ["docling", "tika"]):
                if any(r["number"] == run for r in doc["runs"][tool]):
                    continue
                directory = output / doc["id"] / f"{tool}-{run}"
                if directory.exists() and any(directory.iterdir()):
                    # An interrupted run is kept; the replacement gets a new attempt directory.
                    directory = output / doc["id"] / f"{tool}-{run}-retry-{time.time_ns()}"
                directory.mkdir(parents=True, exist_ok=True)
                command = [sys.executable, "-m", "docling_poc.benchmark_worker", "--tool", tool,
                           "--source", str(source), "--output", str(directory),
                           "--threads", str(args.threads), "--java", args.java,
                           "--jar", str(args.jar.resolve()), "--config", str(config.resolve())]
                print(f"[{doc['name']}] {tool} {run}/{args.repeat} started", flush=True)
                result = {}
                try:
                    result = execute(command, directory, args.timeout, env)
                    if result["status"] in {"success", "partial_success"}:
                        with gzip.open(directory / "raw.json.gz", "rt", encoding="utf-8") as stream:
                            raw = json.load(stream)
                        snapshot = docling_snapshot(raw) if tool == "docling" else tika_snapshot(raw)
                        write_json(directory / "snapshot.json", snapshot)
                        result["chars"] = len(snapshot["text"])
                        result["counts"] = snapshot["counts"]
                except Exception as exc:  # noqa: BLE001 - record failure and continue other runs
                    result.update(status="failure", error=str(exc))
                result.update(number=run, path=directory.relative_to(output).as_posix())
                doc["runs"][tool].append(result)
                save_manifest(output, manifest)
                print(f"  {result['status']}; total={result.get('total_seconds')} seconds", flush=True)
    from docling_poc.comparison_report import generate

    generate(output)
    print(f"Report: {output / 'index.html'}", flush=True)
    return int(any(r["status"] != "success" for d in manifest["documents"]
                   for runs in d["runs"].values() for r in runs))


if __name__ == "__main__":
    raise SystemExit(main())
