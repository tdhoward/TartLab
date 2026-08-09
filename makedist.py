"""Build a clean, deterministic TartLab device filesystem.

The command is deliberately noninteractive. Existing output is rejected unless
``--clean`` is supplied, which prevents stale files from surviving a build.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from release_utils import canonical_source_bytes, ensure_safe_output, file_inventory


IDE_FOLDER = "ide"
WEB_FOLDER = "www"
COPY_EXCLUDES = {"__pycache__"}


def source_date_epoch() -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH")
    if configured is not None:
        return int(configured)
    try:
        return int(subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"], cwd=ROOT,
            text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def _is_excluded(path: Path) -> bool:
    return any(part in COPY_EXCLUDES for part in path.parts) or \
        path.suffix.lower() in (".pyc", ".pyo")


def _write_source_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_source_bytes(source))


def _minifier():
    try:
        from python_minifier import minify
    except ImportError as error:
        raise RuntimeError(
            "Python minification is enabled. Install the pinned dependencies "
            "with: python -m pip install --require-hashes -r requirements-build.txt"
        ) from error
    return minify


def copy_file(source: Path, target: Path, minify_python: bool) -> None:
    if source.suffix == ".py" and minify_python:
        source_code = canonical_source_bytes(source).decode("utf-8")
        minified = _minifier()(source_code, remove_annotations=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(minified, encoding="utf-8", newline="\n")
    else:
        _write_source_file(source, target)


def copy_tree(source: Path, target: Path, minify_python: bool) -> None:
    if not source.is_dir():
        raise FileNotFoundError("Source directory does not exist: %s" % source)
    for path in sorted(source.rglob("*")):
        if not path.is_file() or _is_excluded(path.relative_to(source)):
            continue
        copy_file(path, target / path.relative_to(source), minify_python)


def copy_top_level(source: Path, target: Path, minify_python: bool = False) -> None:
    for path in sorted(item for item in source.iterdir() if item.is_file()):
        if not _is_excluded(path.relative_to(source)):
            copy_file(path, target / path.name, minify_python)


def npm_executable() -> str:
    candidates = ("npm.cmd", "npm") if os.name == "nt" else ("npm", "npm.cmd")
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise FileNotFoundError("npm was not found on PATH")


def build_web_app(web_source: Path, install_dependencies: bool = False) -> None:
    npm = npm_executable()
    if install_dependencies:
        subprocess.run([npm, "ci"], cwd=web_source, check=True)
    subprocess.run([npm, "run", "build"], cwd=web_source, check=True)


def compress_large_files(folder: Path, epoch: int, size_threshold: int = 2048) -> None:
    for path in sorted(item for item in folder.rglob("*") if item.is_file()):
        if path.stat().st_size <= size_threshold:
            continue
        target = path.with_name(path.name + ".gz")
        with path.open("rb") as source, target.open("wb") as raw:
            with gzip.GzipFile(
                    filename="", mode="wb", fileobj=raw, mtime=epoch,
                    compresslevel=9) as compressed:
                shutil.copyfileobj(source, compressed)
        path.unlink()


def prepare_output(output: Path, source: Path, clean: bool) -> Path:
    output = ensure_safe_output(output, (ROOT, source))
    if output.exists():
        if not clean:
            raise FileExistsError(
                "Output already exists; rerun with --clean to remove it first: %s" % output)
        shutil.rmtree(output)
    output.mkdir(parents=True)
    return output


def build_distribution(
        source: Path, output: Path, *, clean: bool = False,
        minify_python: bool = True, build_web: bool = True,
        install_web_dependencies: bool = False, epoch: int | None = None,
) -> dict[str, object]:
    source = source.resolve()
    output = prepare_output(output, source, clean)
    epoch = source_date_epoch() if epoch is None else epoch
    web_source = source / IDE_FOLDER / WEB_FOLDER

    if build_web:
        build_web_app(web_source, install_web_dependencies)
    web_dist = web_source / "dist"
    if not web_dist.is_dir():
        raise FileNotFoundError(
            "Web output is missing. Run without --skip-web-build: %s" % web_dist)

    copy_top_level(source, output)
    for relative in ("files", "configs", "defaults", "recovery"):
        copy_tree(source / relative, output / relative, False)
    copy_tree(source / "lib", output / "lib", minify_python)
    copy_top_level(source / IDE_FOLDER, output / IDE_FOLDER, minify_python)
    copy_tree(web_dist, output / IDE_FOLDER / WEB_FOLDER, False)
    compress_large_files(output / IDE_FOLDER / WEB_FOLDER, epoch)

    inventory = file_inventory(output)
    return {
        "file_count": len(inventory),
        "expanded_bytes": sum(int(item["size"]) for item in inventory),
        "source_date_epoch": epoch,
        "minified": minify_python,
        "output": str(output),
        "inventory_sha256": hashlib.sha256(json.dumps(
            inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument(
        "--clean", action="store_true",
        help="remove the exact output directory before building")
    parser.add_argument(
        "--no-minify", action="store_true",
        help="copy Python sources verbatim (intended for diagnostics only)")
    parser.add_argument(
        "--skip-web-build", action="store_true",
        help="reuse an existing ignored src/ide/www/dist directory")
    parser.add_argument(
        "--install-web-dependencies", action="store_true",
        help="run npm ci before the web build")
    parser.add_argument("--source-date-epoch", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_distribution(
        args.source, args.output, clean=args.clean,
        minify_python=not args.no_minify,
        build_web=not args.skip_web_build,
        install_web_dependencies=args.install_web_dependencies,
        epoch=args.source_date_epoch)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
