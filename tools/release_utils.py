"""Shared deterministic release helpers.

This module intentionally uses only the Python standard library so it can be
used by local builds and GitHub Actions before optional build dependencies are
installed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


CHUNK_SIZE = 64 * 1024
TEXT_SUFFIXES = {
    ".css", ".html", ".js", ".json", ".md", ".py", ".sh", ".svg", ".txt",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_source_bytes(path: Path) -> bytes:
    """Return checkout-independent bytes for text sources."""

    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def sha256_source_file(path: Path) -> str:
    return hashlib.sha256(canonical_source_bytes(path)).hexdigest()


def file_inventory(
        root: Path, *, normalize_source_text: bool = False,
) -> list[dict[str, object]]:
    """Return a stable, content-addressed inventory for all files under root."""

    root = root.resolve()
    result = []
    files = (item for item in root.rglob("*") if item.is_file())
    for path in sorted(
            files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix.lower() in (".pyc", ".pyo"):
            continue
        if normalize_source_text:
            data = canonical_source_bytes(path)
            size = len(data)
            content_hash = hashlib.sha256(data).hexdigest()
        else:
            size = path.stat().st_size
            content_hash = sha256_file(path)
        result.append({
            "path": relative.as_posix(),
            "size": size,
            "sha256": content_hash,
        })
    return result


def inventory_identifier(inventory: list[dict[str, object]]) -> str:
    """Hash paths, sizes, and content hashes without depending on JSON layout."""

    digest = hashlib.sha256()
    for item in sorted(inventory, key=lambda value: str(value["path"])):
        record = "%s\0%s\0%s\n" % (
            item["path"], item["size"], item["sha256"])
        digest.update(record.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def tree_identifier(root: Path) -> str:
    return inventory_identifier(file_inventory(root))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_safe_output(output: Path, protected_roots: tuple[Path, ...]) -> Path:
    """Reject output paths that could erase a source tree or broad directory."""

    output = output.resolve()
    if output == Path(output.anchor):
        raise ValueError("Output cannot be a filesystem root")
    for protected in protected_roots:
        protected = protected.resolve()
        if output == protected or output in protected.parents:
            raise ValueError("Output cannot be or contain %s" % protected)
    return output
