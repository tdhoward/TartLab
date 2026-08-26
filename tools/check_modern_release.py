"""Validate a modern release and perform the mandatory provisioning preflight.

This tool is deliberately read-only.  An adult provisioning or migration tool
must call the compatibility preflight successfully before erasing, flashing,
extracting, or otherwise changing device files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import release as release_tools  # noqa: E402
from check_modern_profile import load_json, validate_profile  # noqa: E402
from release_utils import file_inventory, sha256_file  # noqa: E402


DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"


def validate_compatibility(manifest: dict[str, Any], runtime_profile: str,
                           firmware_sha256: str) -> dict[str, str]:
    """Fail closed unless the device identity exactly matches the manifest."""

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("modern manifest compatibility declaration is missing")
    required_profile = compatibility.get("runtime_profile")
    firmware = compatibility.get("firmware")
    if not isinstance(firmware, dict):
        raise ValueError("modern manifest firmware identity is missing")
    required_hash = firmware.get("sha256")
    if runtime_profile != required_profile:
        raise ValueError(
            "Runtime profile mismatch: device is %s, release requires %s" %
            (runtime_profile, required_profile))
    if firmware_sha256.lower() != required_hash:
        raise ValueError(
            "Firmware identity mismatch: device hash does not match the release")
    return {
        "runtime_profile": required_profile,
        "firmware_sha256": required_hash,
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("%s: expected a JSON object" % path)
    return value


def check(release: Path, runtime_profile: str, firmware_sha256: str,
          *, profile_path: Path = DEFAULT_PROFILE,
          dist: Path | None = None) -> dict[str, object]:
    release = release.resolve()
    if not release.is_dir():
        raise ValueError("modern release directory not found: %s" % release)
    if (release / "manifest.json").exists():
        raise ValueError("modern release must not contain legacy manifest.json")
    profile = load_json(profile_path)
    validate_profile(profile)
    manifest = _read_object(release / "modern-manifest.json")
    if manifest.get("schema") != profile["release_builder"]["manifest_schema"] or \
            manifest.get("kind") != "tartlab-modern-release" or \
            manifest.get("profile") != "lvgl-modern":
        raise ValueError("unexpected modern manifest identity")
    if manifest.get("channel") != {
            "repository": "tdhoward/TartLab-modern-releases",
            "manifest": "modern-manifest.json"}:
        raise ValueError("modern manifest targets an unexpected release channel")

    expected_compatibility = profile["firmware_compatibility"]
    actual_firmware = manifest.get("compatibility", {}).get("firmware", {})
    for key, expected in expected_compatibility.items():
        if actual_firmware.get(key) != expected:
            raise ValueError("modern manifest firmware declaration mismatch: %s" % key)
    preflight = validate_compatibility(
        manifest, runtime_profile, firmware_sha256)

    checksums = _read_object(release / "checksums.json")
    for filename, expected in checksums.items():
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("unsafe modern checksum filename")
        path = release / filename
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError("Modern release checksum mismatch: %s" % filename)
    required_metadata = {
        "modern-manifest.json", "build_metadata.json",
        "payload_inventory.json", "dist_inventory.json",
    }
    missing = sorted(required_metadata.difference(checksums))
    if missing:
        raise ValueError("modern checksums omit required metadata: %s" % missing[0])

    payloads = _read_object(release / "payload_inventory.json")
    metadata = _read_object(release / "build_metadata.json")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("modern manifest contains no packages")
    owned_paths: set[str] = set()
    package_names: set[str] = set()
    archive_total = 0
    expanded_total = 0
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("modern package entry must be an object")
        name = package.get("name")
        if not isinstance(name, str) or name in package_names:
            raise ValueError("modern package name is missing or duplicated")
        package_names.add(name)
        filename = package.get("file_name")
        target = package.get("target")
        if not isinstance(filename, str) or Path(filename).name != filename or \
                not filename.endswith(".tar"):
            raise ValueError("modern package filename is unsafe")
        if not isinstance(target, str) or "\\" in target or \
                not target.startswith("/") or ".." in Path(target).parts or \
                (target != "/" and target != "/" + target.strip("/")):
            raise ValueError("modern package target is unsafe")
        archive_path = release / filename
        if archive_path.name not in checksums:
            raise ValueError("modern package is not checksum authenticated")
        if sha256_file(archive_path) != package.get("sha256"):
            raise ValueError("Modern manifest hash mismatch: %s" % archive_path.name)
        if archive_path.stat().st_size != package.get("archive_size"):
            raise ValueError("Modern manifest size mismatch: %s" % archive_path.name)
        actual_payload = []
        with tarfile.open(archive_path, "r") as archive:
            members = [member for member in archive.getmembers() if member.isfile()]
            if [member.name for member in members] != sorted(
                    member.name for member in members):
                raise ValueError("Modern archive members are not sorted")
            for member in members:
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or \
                        "\\" in member.name:
                    raise ValueError("Modern archive contains an unsafe member path")
                if member.uid != 0 or member.gid != 0 or \
                        member.mtime != metadata["source_date_epoch"]:
                    raise ValueError("Modern archive metadata is not normalized")
                stream = archive.extractfile(member)
                content = stream.read()
                actual_payload.append({
                    "path": member.name,
                    "size": member.size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                })
        if actual_payload != payloads.get(name):
            raise ValueError("Modern payload inventory mismatch: %s" % name)
        expanded = sum(item["size"] for item in actual_payload)
        if expanded != package.get("expanded_size"):
            raise ValueError("Modern expanded size mismatch: %s" % name)
        paths = release_tools.archive_paths(archive_path, target)
        release_tools.validate_archive_ownership(paths)
        overlap = owned_paths.intersection(paths)
        if overlap:
            raise ValueError("Modern package ownership overlap: %s" % sorted(overlap)[0])
        owned_paths.update(paths)
        archive_total += archive_path.stat().st_size
        expanded_total += expanded

    recorded_dist = json.loads(
        (release / "dist_inventory.json").read_text(encoding="utf-8"))
    required_paths = {
        "/" + str(item["path"]).strip("/") for item in recorded_dist
        if not release_tools.is_protected_path(item["path"])
    }
    if owned_paths != required_paths:
        raise ValueError("Modern package ownership differs from recorded distribution")
    if dist is not None and file_inventory(dist) != recorded_dist:
        raise ValueError("Modern distribution differs from its recorded inventory")
    totals = metadata.get("totals", {})
    if totals.get("package_count") != len(packages) or \
            totals.get("archive_bytes") != archive_total or \
            totals.get("expanded_bytes") != expanded_total:
        raise ValueError("Modern release totals differ from build metadata")
    if metadata.get("profile") != "lvgl-modern" or \
            metadata.get("release_repository") != \
            "tdhoward/TartLab-modern-releases":
        raise ValueError("Modern build metadata targets an unexpected profile or feed")
    return {
        "profile": "lvgl-modern",
        "version": manifest["version"],
        "packages": len(packages),
        "archive_bytes": archive_total,
        "expanded_bytes": expanded_total,
        "preflight": preflight,
        "mutation_performed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--runtime-profile", required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--dist", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = check(
        args.release, args.runtime_profile, args.firmware_sha256,
        profile_path=args.profile, dist=args.dist)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
