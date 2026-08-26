"""Build deterministic filesystem assets for the isolated modern channel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import release as release_tools  # noqa: E402
from check_modern_profile import load_json, validate_profile  # noqa: E402
from release_utils import (  # noqa: E402
    ensure_safe_output, file_inventory, inventory_identifier, sha256_file,
    sha256_source_file, write_json,
)


DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"
DEFAULT_PACKAGES = ROOT / "tartlab_packages.json"
MODERN_VERSION = re.compile(r"^modern-v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def _git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True,
        stderr=subprocess.DEVNULL).strip()


def _epoch(configured: int | None) -> int:
    if configured is not None:
        return configured
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        return int(_git_value("log", "-1", "--format=%ct"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def _package_source(dist: Path, source_text: str) -> tuple[Path, bool]:
    top_only = source_text.endswith("*")
    relative = source_text.rstrip("*").replace("\\", "/")
    if relative == "dist/":
        relative = ""
    elif relative.startswith("dist/"):
        relative = relative[len("dist/"):]
    else:
        raise ValueError("Package source must be beneath dist/: %s" % source_text)
    source = (dist / relative.strip("/")).resolve()
    if source != dist and dist not in source.parents:
        raise ValueError("Package source escapes the modern distribution")
    return source, top_only


def _validate_package_identity(package: dict[str, Any], names: set[str]) -> None:
    name = package.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("Modern package name is unsafe")
    if name in names:
        raise ValueError("Duplicate modern package name: %s" % name)
    names.add(name)
    target = package.get("target")
    if not isinstance(target, str) or "\\" in target or \
            not target.startswith("/") or ".." in Path(target).parts or \
            (target != "/" and target != "/" + target.strip("/")):
        raise ValueError("Modern package target is unsafe: %r" % target)
    if not isinstance(package.get("clear_first"), bool):
        raise ValueError("Modern package clear_first must be boolean")


def _payload_inventory(archive_path: Path) -> list[dict[str, object]]:
    result = []
    with tarfile.open(archive_path, "r") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            content = stream.read()
            result.append({
                "path": member.name,
                "size": member.size,
                "sha256": hashlib.sha256(content).hexdigest(),
            })
    return result


def build_release(
        dist: Path, output: Path, version: str, *, clean: bool = False,
        profile_path: Path = DEFAULT_PROFILE,
        packages_path: Path = DEFAULT_PACKAGES,
        source_epoch: int | None = None,
        allow_dirty: bool = False) -> dict[str, object]:
    """Create a modern candidate without changing or reusing legacy manifest data."""

    dist = dist.resolve()
    if not dist.is_dir():
        raise ValueError("modern distribution not found: %s" % dist)
    output = ensure_safe_output(output, (ROOT, dist))
    if output.exists():
        if not clean:
            raise FileExistsError(
                "Output already exists; rerun with --clean: %s" % output)
        shutil.rmtree(output)
    output.mkdir(parents=True)
    if not MODERN_VERSION.fullmatch(version):
        raise ValueError("Modern versions must use modern-vMAJOR.MINOR[.PATCH]")

    profile = load_json(profile_path)
    validate_profile(profile)
    packages = json.loads(packages_path.read_text(encoding="utf-8"))
    if not isinstance(packages, list) or not packages:
        raise ValueError("modern package map must be a non-empty list")
    try:
        commit = _git_value("rev-parse", "HEAD")
        dirty = bool(_git_value("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
        dirty = True
    if dirty and not allow_dirty:
        raise ValueError("Modern release builds require a clean Git working tree")
    epoch = _epoch(source_epoch)

    package_entries = []
    payloads: dict[str, list[dict[str, object]]] = {}
    owned_paths: set[str] = set()
    package_names: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("modern package entry must be an object")
        _validate_package_identity(package, package_names)
        source, top_only = _package_source(dist, package["source"])
        if not source.is_dir():
            raise FileNotFoundError("Package source does not exist: %s" % source)
        archive_path = Path(release_tools.create_tarfile(
            package["name"], source, top_only, output,
            package.get("exclude", []), mtime=epoch))
        paths = release_tools.archive_paths(archive_path, package["target"])
        if not paths:
            raise ValueError("Package is empty: %s" % package["name"])
        release_tools.validate_archive_ownership(paths)
        overlap = owned_paths.intersection(paths)
        if overlap:
            raise ValueError("Archive ownership overlaps: %s" % sorted(overlap)[0])
        owned_paths.update(paths)
        payload = _payload_inventory(archive_path)
        payloads[package["name"]] = payload
        package_entries.append({
            "name": package["name"],
            "file_name": archive_path.name,
            "sha256": sha256_file(archive_path),
            "target": package["target"],
            "clear_first": package["clear_first"],
            "ownership": package.get("ownership", "system"),
            "archive_size": archive_path.stat().st_size,
            "expanded_size": sum(int(item["size"]) for item in payload),
        })

    dist_inventory = file_inventory(dist)
    required_paths = {
        "/" + str(item["path"]).strip("/") for item in dist_inventory
        if not release_tools.is_protected_path(item["path"])
    }
    if owned_paths != required_paths:
        missing = sorted(required_paths.difference(owned_paths))
        extra = sorted(owned_paths.difference(required_paths))
        detail = missing[0] if missing else extra[0]
        raise ValueError("Modern package ownership differs from distribution: %s" % detail)

    firmware = dict(profile["firmware_compatibility"])
    firmware["artifact_sha256_verified"] = True
    firmware["lock_sha256"] = sha256_source_file(ROOT / firmware["lock"])
    firmware["provenance_sha256"] = sha256_source_file(
        ROOT / firmware["provenance"])
    manifest: dict[str, Any] = {
        "schema": profile["release_builder"]["manifest_schema"],
        "kind": "tartlab-modern-release",
        "profile": profile["profile"],
        "version": version,
        "channel": {
            "repository": profile["release_channel"]["repository"],
            "manifest": profile["release_channel"]["manifest"],
        },
        "compatibility": {
            "runtime_profile": profile["profile"],
            "firmware": firmware,
            "runtime_identity": profile["runtime_identity"],
        },
        "packages": package_entries,
    }
    write_json(output / "modern-manifest.json", manifest)
    write_json(output / "payload_inventory.json", payloads)
    write_json(output / "dist_inventory.json", dist_inventory)
    metadata = {
        "schema": 1,
        "artifact_status": "promotion-gated-candidate",
        "profile": profile["profile"],
        "tartlab_version": version,
        "git_commit": commit,
        "git_dirty": dirty,
        "build_timestamp_utc": datetime.fromtimestamp(
            epoch, timezone.utc).isoformat().replace("+00:00", "Z"),
        "build_timestamp_basis": "SOURCE_DATE_EPOCH",
        "source_date_epoch": epoch,
        "release_repository": profile["release_channel"]["repository"],
        "manifest": "modern-manifest.json",
        "firmware_sha256": firmware["sha256"],
        "dist_identifier": inventory_identifier(dist_inventory),
        "inputs": {
            "profile_sha256": sha256_source_file(profile_path),
            "package_map_sha256": sha256_source_file(packages_path),
            "firmware_lock_sha256": firmware["lock_sha256"],
            "firmware_provenance_sha256": firmware["provenance_sha256"],
        },
        "totals": {
            "package_count": len(package_entries),
            "archive_bytes": sum(item["archive_size"] for item in package_entries),
            "expanded_bytes": sum(item["expanded_size"] for item in package_entries),
            "dist_files": len(dist_inventory),
        },
        "remaining_promotion_gates": profile["promotion_gates"],
    }
    write_json(output / "build_metadata.json", metadata)
    checksums = {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir()) if path.is_file()
    }
    write_json(output / "checksums.json", checksums)
    return metadata


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--packages", type=Path, default=DEFAULT_PACKAGES)
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_release(
        args.dist, args.output, args.version, clean=args.clean,
        profile_path=args.profile, packages_path=args.packages,
        source_epoch=args.source_date_epoch, allow_dirty=args.allow_dirty)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
