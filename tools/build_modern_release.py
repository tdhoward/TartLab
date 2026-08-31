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
from board_catalog import select_board  # noqa: E402
from check_modern_profile import load_json, validate_profile  # noqa: E402
from check_modern_support_window import validate_policy as validate_support_window  # noqa: E402
from release_utils import (  # noqa: E402
    canonical_source_bytes, ensure_safe_output, file_inventory,
    inventory_identifier, sha256_file, sha256_source_file, write_json,
)


DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"
DEFAULT_PACKAGES = ROOT / "tartlab_packages.json"
MODERN_VERSION = re.compile(r"^modern-v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def _write_canonical_copy(source: Path, destination: Path) -> None:
    destination.write_bytes(canonical_source_bytes(source))


def _release_file(path: Path, *, kind: str) -> dict[str, object]:
    return {
        "kind": kind,
        "file_name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


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
        allow_dirty: bool = False,
        board_ids: Sequence[str] | None = None) -> dict[str, object]:
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

    default_board_id = profile["default_board_id"]
    if board_ids is None:
        boards = [select_board(default_board_id, required_status="qualified")]
    else:
        if len(set(board_ids)) != len(board_ids):
            raise ValueError("modern release board IDs must be unique")
        boards = [select_board(board_id) for board_id in board_ids]
        for descriptor in boards:
            if descriptor["runtime_profile"] != profile["profile"] or \
                    descriptor["support_status"] not in ("candidate", "qualified"):
                raise ValueError(
                    "modern release boards must be candidate or qualified")
    boards.sort(key=lambda descriptor: descriptor["id"])
    if not boards or default_board_id not in {
            descriptor["id"] for descriptor in boards}:
        raise ValueError("modern release must include its qualified default board")

    firmware_policies: dict[str, dict[str, Any]] = {}
    published_firmwares: dict[str, dict[str, object]] = {}
    board_compatibility: dict[str, dict[str, Any]] = {}
    provenance_assets: list[dict[str, object]] = []
    firmware_assets: dict[str, Path] = {}
    for descriptor in boards:
        board_id = descriptor["id"]
        firmware = dict(
            profile["firmware_compatibility"]
            if board_id == default_board_id else descriptor["firmware"])
        for key, value in descriptor["firmware"].items():
            if firmware.get(key) != value:
                raise ValueError(
                    "board firmware differs from profile for %s" % board_id)
        firmware["artifact_sha256_verified"] = True
        firmware["lock_sha256"] = sha256_source_file(ROOT / firmware["lock"])
        firmware["provenance_sha256"] = sha256_source_file(
            ROOT / firmware["provenance"])
        source_firmware = ROOT / firmware["artifact"]
        if board_id == default_board_id:
            firmware_name = "tartlab-%s.bin" % version
            lock_name = "firmware-build-lock.json"
            provenance_name = "firmware-provenance.json"
        else:
            firmware_name = "tartlab-%s-%s.bin" % (version, board_id)
            lock_name = "firmware-build-lock-%s.json" % board_id
            provenance_name = "firmware-provenance-%s.json" % board_id
        firmware_asset = output / firmware_name
        shutil.copyfile(source_firmware, firmware_asset)
        if sha256_file(firmware_asset) != firmware["sha256"]:
            raise ValueError(
                "Published modern firmware differs for board %s" % board_id)
        lock_asset = output / lock_name
        provenance_asset = output / provenance_name
        _write_canonical_copy(ROOT / firmware["lock"], lock_asset)
        _write_canonical_copy(ROOT / firmware["provenance"], provenance_asset)
        published_firmware = _release_file(
            firmware_asset, kind="firmware-image")
        published_firmware.update({
            "board_id": board_id,
            "image_format": firmware["image_format"],
            "flash_offset": firmware["flash_offset"],
            "installation": "adult-provisioning-only",
        })
        lock_record = _release_file(lock_asset, kind="firmware-build-lock")
        lock_record["board_id"] = board_id
        provenance_record = _release_file(
            provenance_asset, kind="firmware-provenance")
        provenance_record["board_id"] = board_id
        provenance_assets.extend((lock_record, provenance_record))
        firmware_policies[board_id] = firmware
        published_firmwares[board_id] = published_firmware
        firmware_assets[board_id] = firmware_asset
        hardware = descriptor["hardware"]
        board_compatibility[board_id] = {
            "name": descriptor["name"],
            "revisions": hardware["revisions"],
            "flash_size_bytes": hardware["flash_size_bytes"],
            "psram_size_bytes": hardware["psram_size_bytes"],
            "selector_module": descriptor["selector"]["module"],
            "firmware": firmware,
        }

    firmware = firmware_policies[default_board_id]
    firmware_asset = firmware_assets[default_board_id]
    published_firmware = published_firmwares[default_board_id]
    vendor_lock_asset = output / "filesystem-vendor-lock.json"
    support_window_asset = output / "support-window.json"
    _write_canonical_copy(
        ROOT / profile["release_builder"]["filesystem_vendor_lock"],
        vendor_lock_asset)
    support_window_source = ROOT / profile["release_builder"]["support_window"]
    support_window = load_json(support_window_source)
    validate_support_window(support_window)
    _write_canonical_copy(support_window_source, support_window_asset)

    provenance_assets.append(
        _release_file(vendor_lock_asset, kind="filesystem-vendor-lock"))
    published_support_window = _release_file(
        support_window_asset, kind="support-window-policy")
    compatibility = {
        "schema": 2,
        "kind": "tartlab-modern-compatibility",
        "profile": profile["profile"],
        "version": version,
        "release_repository": profile["release_channel"]["repository"],
        "firmware": published_firmware,
        "default_board_id": default_board_id,
        "boards": {
            board_id: dict(
                board_compatibility[board_id],
                firmware=published_firmwares[board_id])
            for board_id in sorted(board_compatibility)
        },
        "runtime_identity": profile["runtime_identity"],
        "provisioning_tool": profile["release_builder"]["provisioning_tool"],
        "filesystem": {
            "manifest": "modern-manifest.json",
            "packages": [item["file_name"] for item in package_entries],
            "legacy_updater_compatible": False,
        },
        "supported_source_profiles": [],
        "host_tested_source_profiles": ["clean", "legacy-mp123"],
        "planned_migration_source": "legacy-mp123",
        "migration_status": "host-tested-pending-physical-qualification",
        "support_window": {
            "policy": published_support_window,
            "source_profile": support_window["direct_migration"][
                "source_profile"],
            "minimum_tartlab_version": support_window["direct_migration"][
                "minimum_tartlab_version"],
            "version_rule": support_window["direct_migration"]["version_rule"],
            "below_floor_action": support_window["below_floor"]["action"],
        },
    }
    write_json(output / "compatibility.json", compatibility)

    migration_source = ROOT / profile["release_builder"]["migration_instructions"]
    migration_text = canonical_source_bytes(migration_source).decode("utf-8")
    replacements = {
        "@VERSION@": version,
        "@FIRMWARE_ASSET@": firmware_asset.name,
        "@FIRMWARE_SHA256@": firmware["sha256"],
        "@FLASH_OFFSET@": firmware["flash_offset"],
    }
    for marker, value in replacements.items():
        migration_text = migration_text.replace(marker, value)
    if re.search(r"@[A-Z0-9_]+@", migration_text):
        raise ValueError("Modern migration instructions contain an unknown marker")
    migration_asset = output / "MIGRATION.md"
    migration_asset.write_text(migration_text, encoding="utf-8", newline="\n")

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
            "schema": 2,
            "runtime_profile": profile["profile"],
            "firmware": firmware,
            "default_board_id": default_board_id,
            "boards": board_compatibility,
            "runtime_identity": profile["runtime_identity"],
        },
        "packages": package_entries,
        "published_assets": {
            "firmware": published_firmware,
            "firmwares": published_firmwares,
            "compatibility": _release_file(
                output / "compatibility.json", kind="compatibility-declaration"),
            "migration_instructions": _release_file(
                migration_asset, kind="migration-instructions"),
            "support_window": published_support_window,
            "provenance": provenance_assets,
        },
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
        "default_board_id": default_board_id,
        "board_ids": sorted(board_compatibility),
        "dist_identifier": inventory_identifier(dist_inventory),
        "inputs": {
            "profile_sha256": sha256_source_file(profile_path),
            "package_map_sha256": sha256_source_file(packages_path),
            "firmware_lock_sha256": firmware["lock_sha256"],
            "firmware_provenance_sha256": firmware["provenance_sha256"],
            "board_firmware_locks": {
                board_id: firmware_policies[board_id]["lock_sha256"]
                for board_id in sorted(firmware_policies)
            },
            "board_firmware_provenance": {
                board_id: firmware_policies[board_id]["provenance_sha256"]
                for board_id in sorted(firmware_policies)
            },
            "filesystem_vendor_lock_sha256": sha256_file(vendor_lock_asset),
            "support_window_sha256": sha256_file(support_window_asset),
            "migration_instructions_sha256": sha256_file(migration_asset),
        },
        "totals": {
            "package_count": len(package_entries),
            "archive_bytes": sum(item["archive_size"] for item in package_entries),
            "expanded_bytes": sum(item["expanded_size"] for item in package_entries),
            "dist_files": len(dist_inventory),
            "firmware_bytes": sum(
                path.stat().st_size for path in firmware_assets.values()),
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
    parser.add_argument(
        "--board", dest="board_ids", action="append",
        help="candidate/qualified board ID to include; repeat for multiple boards")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = build_release(
        args.dist, args.output, args.version, clean=args.clean,
        profile_path=args.profile, packages_path=args.packages,
        source_epoch=args.source_date_epoch, allow_dirty=args.allow_dirty,
        board_ids=args.board_ids)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
