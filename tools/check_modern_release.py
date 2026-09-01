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
from board_catalog import load_catalog  # noqa: E402
from check_modern_profile import load_json, validate_profile  # noqa: E402
from check_modern_support_window import validate_policy as validate_support_window  # noqa: E402
from release_utils import file_inventory, sha256_file, sha256_source_file  # noqa: E402


DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"


def _validate_published_file(
        release: Path, record: object, checksums: dict[str, Any],
        expected_kind: str) -> Path:
    if not isinstance(record, dict) or record.get("kind") != expected_kind:
        raise ValueError("modern published asset has an unexpected kind")
    filename = record.get("file_name")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("modern published asset filename is unsafe")
    path = release / filename
    if not path.is_file() or filename not in checksums:
        raise ValueError("modern published asset is missing or unauthenticated: %s" % filename)
    actual_hash = sha256_file(path)
    if actual_hash != record.get("sha256") or actual_hash != checksums[filename]:
        raise ValueError("modern published asset hash mismatch: %s" % filename)
    if path.stat().st_size != record.get("size"):
        raise ValueError("modern published asset size mismatch: %s" % filename)
    return path


def validate_compatibility(manifest: dict[str, Any], runtime_profile: str,
                           firmware_sha256: str,
                           board_id: str | None = None) -> dict[str, str]:
    """Fail closed unless the device identity exactly matches the manifest."""

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("modern manifest compatibility declaration is missing")
    required_profile = compatibility.get("runtime_profile")
    if runtime_profile != required_profile:
        raise ValueError(
            "Runtime profile mismatch: device is %s, release requires %s" %
            (runtime_profile, required_profile))
    boards = compatibility.get("boards")
    if isinstance(boards, dict):
        if board_id is None:
            matches = [
                candidate_id for candidate_id, record in boards.items()
                if isinstance(record, dict) and
                isinstance(record.get("firmware"), dict) and
                record["firmware"].get("sha256") == firmware_sha256.lower()
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Board identity is required for this modern release")
            board_id = matches[0]
        board = boards.get(board_id)
        if not isinstance(board, dict):
            raise ValueError("Board is not supported by the modern release")
        firmware = board.get("firmware")
    else:
        firmware = compatibility.get("firmware")
        if board_id is None:
            board_id = "legacy-single-board"
    if not isinstance(firmware, dict):
        raise ValueError("modern manifest firmware identity is missing")
    required_hash = firmware.get("sha256")
    if firmware_sha256.lower() != required_hash:
        raise ValueError(
            "Firmware identity mismatch: device hash does not match the release")
    return {
        "runtime_profile": required_profile,
        "firmware_sha256": required_hash,
        "board_id": board_id,
    }


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("%s: expected a JSON object" % path)
    return value


def check(release: Path, runtime_profile: str, firmware_sha256: str,
          *, profile_path: Path = DEFAULT_PROFILE,
          dist: Path | None = None,
          board_id: str | None = None) -> dict[str, object]:
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
        manifest, runtime_profile, firmware_sha256, board_id)

    checksums = _read_object(release / "checksums.json")
    for filename, expected in checksums.items():
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("unsafe modern checksum filename")
        path = release / filename
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError("Modern release checksum mismatch: %s" % filename)
    required_metadata = {
        "modern-manifest.json", "build_metadata.json",
        "payload_inventory.json", "dist_inventory.json", "compatibility.json",
        "firmware-build-lock.json", "firmware-provenance.json",
        "filesystem-vendor-lock.json", "MIGRATION.md",
        "support-window.json",
    }
    missing = sorted(required_metadata.difference(checksums))
    if missing:
        raise ValueError("modern checksums omit required metadata: %s" % missing[0])

    payloads = _read_object(release / "payload_inventory.json")
    metadata = _read_object(release / "build_metadata.json")
    published = manifest.get("published_assets")
    if not isinstance(published, dict):
        raise ValueError("modern manifest has no published artifact inventory")
    default_board_id = profile["default_board_id"]
    published_firmware = published.get("firmware")
    published_firmwares = published.get("firmwares")
    if published_firmwares is None:
        published_firmwares = {default_board_id: published_firmware}
    if not isinstance(published_firmwares, dict) or \
            published_firmwares.get(default_board_id) != published_firmware:
        raise ValueError("published board firmware inventory is incomplete")
    firmware_paths: dict[str, Path] = {}
    for published_board_id, record in published_firmwares.items():
        path = _validate_published_file(
            release, record, checksums, "firmware-image")
        if record.get("board_id", published_board_id) != published_board_id or \
                record.get("installation") != "adult-provisioning-only":
            raise ValueError("published board firmware identity is invalid")
        firmware_paths[published_board_id] = path
    selected_board_id = preflight["board_id"]
    if selected_board_id == "legacy-single-board":
        selected_board_id = default_board_id
    selected_firmware = published_firmwares.get(selected_board_id)
    if not isinstance(selected_firmware, dict) or \
            selected_firmware.get("sha256") != firmware_sha256.lower():
        raise ValueError("published firmware identity differs from compatibility policy")
    firmware_path = firmware_paths[selected_board_id]

    compatibility_path = _validate_published_file(
        release, published.get("compatibility"), checksums,
        "compatibility-declaration")
    compatibility = _read_object(compatibility_path)
    support_window_record = published.get("support_window")
    support_window_path = _validate_published_file(
        release, support_window_record, checksums, "support-window-policy")
    support_window = _read_object(support_window_path)
    validate_support_window(support_window)
    support_window_source = ROOT / profile["release_builder"]["support_window"]
    if support_window_record.get("sha256") != \
            sha256_source_file(support_window_source) or \
            support_window != _read_object(support_window_source):
        raise ValueError("published modern support-window policy differs from source")
    expected_support_window = {
        "policy": support_window_record,
        "source_profile": "legacy-mp123",
        "minimum_tartlab_version": "v0.13",
        "version_rule": "stable-at-or-newer",
        "below_floor_action": (
            "adult-clean-provision-with-reviewed-manual-restore"),
    }
    if compatibility.get("schema") not in (1, 2) or \
            compatibility.get("kind") != "tartlab-modern-compatibility" or \
            compatibility.get("profile") != "lvgl-modern" or \
            compatibility.get("version") != manifest.get("version") or \
            compatibility.get("release_repository") != \
            "tdhoward/TartLab-modern-releases" or \
            compatibility.get("firmware") != published_firmware or \
            compatibility.get("runtime_identity") != profile["runtime_identity"] or \
            compatibility.get("provisioning_tool") != \
            "tools/provision_modern.py" or \
            compatibility.get("supported_source_profiles") != [] or \
            compatibility.get("host_tested_source_profiles") != \
            ["clean", "legacy-mp123"] or \
            compatibility.get("planned_migration_source") != "legacy-mp123" or \
            compatibility.get("migration_status") != \
            "host-tested-pending-physical-qualification" or \
            compatibility.get("support_window") != expected_support_window:
        raise ValueError("published modern compatibility declaration is invalid")
    manifest_compatibility = manifest["compatibility"]
    if compatibility.get("schema") == 2:
        if manifest_compatibility.get("schema") != 2 or \
                compatibility.get("default_board_id") != default_board_id or \
                manifest_compatibility.get("default_board_id") != default_board_id:
            raise ValueError("modern default-board compatibility is invalid")
        published_boards = compatibility.get("boards")
        manifest_boards = manifest_compatibility.get("boards")
        if not isinstance(published_boards, dict) or \
                not isinstance(manifest_boards, dict) or \
                set(published_boards) != set(published_firmwares) or \
                set(manifest_boards) != set(published_firmwares):
            raise ValueError("modern board compatibility matrix is incomplete")
        catalog = load_catalog()
        for compatible_board_id in sorted(published_boards):
            descriptor = catalog.get(compatible_board_id)
            published_board = published_boards[compatible_board_id]
            manifest_board = manifest_boards[compatible_board_id]
            if not isinstance(descriptor, dict) or \
                    not isinstance(published_board, dict) or \
                    not isinstance(manifest_board, dict):
                raise ValueError("modern compatibility names an unknown board")
            hardware = descriptor["hardware"]
            expected_board = {
                "name": descriptor["name"],
                "revisions": hardware["revisions"],
                "flash_size_bytes": hardware["flash_size_bytes"],
                "psram_size_bytes": hardware["psram_size_bytes"],
                "selector_module": descriptor["selector"]["module"],
            }
            for key, value in expected_board.items():
                if published_board.get(key) != value or \
                        manifest_board.get(key) != value:
                    raise ValueError(
                        "modern board compatibility differs from catalog: %s" %
                        compatible_board_id)
            if published_board.get("firmware") != \
                    published_firmwares[compatible_board_id] or \
                    manifest_board.get("firmware", {}).get("sha256") != \
                    published_firmwares[compatible_board_id].get("sha256"):
                raise ValueError("modern board firmware matrix is inconsistent")

    migration_path = _validate_published_file(
        release, published.get("migration_instructions"), checksums,
        "migration-instructions")
    migration_text = migration_path.read_text(encoding="utf-8")
    default_firmware_path = firmware_paths[default_board_id]
    migration_markers = (
        manifest["version"], default_firmware_path.name,
        published_firmware["sha256"],
        "adult administrators", "cannot replace firmware", "v0.13",
        "older than v0.13",
    )
    authorization_markers = (
        "promotion-gated-unreleased", "promotion_attestation.json")
    if any(marker not in migration_text for marker in migration_markers) or \
            not any(marker in migration_text for marker in authorization_markers):
        raise ValueError("published modern migration instructions are incomplete")

    provenance = published.get("provenance")
    if not isinstance(provenance, list) or \
            len(provenance) != len(published_firmwares) * 2 + 1:
        raise ValueError("modern source/vendor provenance inventory is incomplete")
    catalog = load_catalog()
    for compatible_board_id in published_firmwares:
        descriptor = catalog[compatible_board_id]
        for kind, source_key in (
                ("firmware-build-lock", "lock"),
                ("firmware-provenance", "provenance")):
            matches = [
                item for item in provenance if isinstance(item, dict) and
                item.get("kind") == kind and
                (item.get("board_id") == compatible_board_id or
                 (compatibility.get("schema") == 1 and
                  compatible_board_id == default_board_id and
                  item.get("board_id") is None))
            ]
            if len(matches) != 1:
                raise ValueError(
                    "modern board provenance is incomplete: %s" %
                    compatible_board_id)
            path = _validate_published_file(
                release, matches[0], checksums, kind)
            if matches[0].get("sha256") != sha256_source_file(
                    ROOT / descriptor["firmware"][source_key]):
                raise ValueError(
                    "published modern provenance differs from source: %s" % kind)
    vendor_matches = [
        item for item in provenance if isinstance(item, dict) and
        item.get("kind") == "filesystem-vendor-lock"
    ]
    if len(vendor_matches) != 1:
        raise ValueError("modern filesystem provenance is incomplete")
    vendor_path = _validate_published_file(
        release, vendor_matches[0], checksums, "filesystem-vendor-lock")
    if vendor_path.name != "filesystem-vendor-lock.json" or \
            vendor_matches[0].get("sha256") != sha256_source_file(
                ROOT / profile["release_builder"]["filesystem_vendor_lock"]):
        raise ValueError("published modern filesystem provenance differs")

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
        selection = package.get("selection")
        if not isinstance(filename, str) or Path(filename).name != filename or \
                not filename.endswith(".tar"):
            raise ValueError("modern package filename is unsafe")
        if not isinstance(target, str) or "\\" in target or \
                not target.startswith("/") or ".." in Path(target).parts or \
                (target != "/" and target != "/" + target.strip("/")):
            raise ValueError("modern package target is unsafe")
        if selection is not None and (
                selection != "board-id-subtree" or name != "board-support" or
                target != "/board" or package.get("clear_first") is not True):
            raise ValueError("modern package selection policy is invalid")
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
        if selection == "board-id-subtree":
            payload_boards = {
                Path(item["path"]).parts[0] for item in actual_payload
                if Path(item["path"]).parts
            }
            if payload_boards != set(published_firmwares):
                raise ValueError(
                    "board-support payload differs from compatible boards")
            selected_sizes: dict[str, int] = {}
            for item in actual_payload:
                board_id = Path(item["path"]).parts[0]
                selected_sizes[board_id] = (
                    selected_sizes.get(board_id, 0) + int(item["size"]))
            if package.get("selected_expanded_sizes") != selected_sizes:
                raise ValueError(
                    "board-support selected expanded sizes differ")
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

    if "/defaults/user/hello.py" not in owned_paths:
        raise ValueError(
            "modern release has no authenticated clean user defaults")
    selected_packages = [
        item for item in packages
        if item.get("selection") == "board-id-subtree"]
    if len(selected_packages) != 1:
        raise ValueError("modern release has no unique board-support package")

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
    if metadata.get("totals", {}).get("firmware_bytes") != sum(
            path.stat().st_size for path in firmware_paths.values()):
        raise ValueError("Modern firmware total differs from build metadata")
    return {
        "profile": "lvgl-modern",
        "version": manifest["version"],
        "packages": len(packages),
        "archive_bytes": archive_total,
        "expanded_bytes": expanded_total,
        "firmware_asset": firmware_path.name,
        "board_id": selected_board_id,
        "compatible_boards": sorted(published_firmwares),
        "published_provenance_assets": len(provenance),
        "support_window_floor": "v0.13",
        "preflight": preflight,
        "mutation_performed": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--runtime-profile", required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--board")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--dist", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = check(
        args.release, args.runtime_profile, args.firmware_sha256,
        profile_path=args.profile, dist=args.dist, board_id=args.board)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
