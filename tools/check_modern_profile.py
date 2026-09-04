"""Check the published modern TartLab filesystem profile.

The selected LVGL firmware and filesystem are production-qualified through a
separate release channel. This checker binds that published release path to the
exact Phase 5 firmware and keeps it isolated from the legacy device feed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from board_catalog import default_board
from modern_firmware import check_lock as check_modern_firmware_lock
from check_modern_support_window import validate_policy as validate_support_window
from release_utils import sha256_source_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"
PROFILE_BOARD = default_board("lvgl-modern")
PROFILE_SELECTOR_SOURCE = PROFILE_BOARD["selector"]["source"]
PROFILE_RUNTIME_FILE = (
    PROFILE_BOARD["runtime"]["target"].strip("/") + "/" +
    Path(PROFILE_SELECTOR_SOURCE).name)
REQUIRED_DIST_FILES = (
    "boot.py",
    "main.py",
    PROFILE_RUNTIME_FILE,
    "lib/tartlabutils/board.py",
    "lib/tartlabutils/modern_launcher.py",
    "lib/tartlabutils/modern_power.py",
    "lib/tartlabutils/modern.py",
    "lib/tartlabutils/modern_factory.py",
    "lib/tartlabutils/modern_st7796.py",
    "lib/tartlabutils/platform.py",
)
APPLICATION_ADAPTER_INPUTS = {
    "src/lib/tartlabutils/board.py",
    "src/lib/tartlabutils/modern.py",
    "src/lib/tartlabutils/modern_factory.py",
    "src/lib/tartlabutils/modern_st7796.py",
    PROFILE_SELECTOR_SOURCE,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_profile(profile: dict[str, Any]) -> None:
    """Ensure the profile is exact, isolated, and qualification-bound."""

    if profile.get("schema") != 2 or profile.get("profile") != "lvgl-modern":
        raise ValueError("unexpected modern profile identity")
    if profile.get("default_board_id") != PROFILE_BOARD["id"]:
        raise ValueError("modern profile has an unexpected default board")
    status = profile.get("status")
    qualification = profile.get("hardware_qualification")
    if status == "promotion-gated-unreleased":
        if qualification is not None:
            raise ValueError(
                "unreleased modern profile must not claim release qualification")
    elif status == "published":
        expected_qualification = {
            "status": "passed-and-promoted",
            "version": "modern-v0.14.8",
            "tag_commit": "49d5b82c795297fa0c6f12ed683af465502779a1",
            "candidate_checksums_sha256": (
                "dd17b1d64f527f6d50dcea414bf5068c4b56e64ac93b8c093cb211e357d7d96e"),
            "evidence_sha256": (
                "1d889e55d969a906c888af9a0ac6c3af355e5b9e6770175b2c5b0e02b7d4d8c8"),
            "evidence_reference": (
                "https://raw.githubusercontent.com/tdhoward/TartLab/"
                "4528f16dbc59750a5b474e81641a19300cfa3a70/tests/evidence/"
                "modern-v0.14.8-qualification.json"),
            "promotion_run_id": 33223821198,
            "published_at_utc": "2026-08-29T00:33:39Z",
            "release_url": (
                "https://github.com/tdhoward/TartLab-modern-releases/releases/"
                "tag/modern-v0.14.8"),
            "release_asset_count": 25,
            "promotion_attestation_sha256": (
                "fa14be9388f6b8178d74160ed934c9d1f782ac8d7f83531d78fddef4f26a42b0"),
            "release_attestation_sha256": (
                "fd01d90821eae91f04806a43f7d490a372430f3e429acc976c770c88efff188a"),
        }
        if qualification != expected_qualification:
            raise ValueError("published modern profile qualification does not match")
    else:
        raise ValueError("modern profile has an unknown release status")

    channel = profile.get("release_channel")
    if not isinstance(channel, dict):
        raise ValueError("modern profile has no isolated release channel")
    if channel.get("repository") != "tdhoward/TartLab-modern-releases":
        raise ValueError("modern release channel must use the isolated repository")
    if channel.get("manifest") != "modern-manifest.json":
        raise ValueError("modern release channel has an unexpected manifest")
    if channel.get("legacy_repository") != "tdhoward/TartLab" or \
            channel.get("legacy_feed_allowed") is not False:
        raise ValueError("modern release channel permits the legacy feed")

    builder = profile.get("release_builder")
    expected_builder = {
        "tool": "tools/build_modern_release.py",
        "package_map": "modern_packages.json",
        "manifest_schema": 1,
        "validator": "tools/check_modern_release.py",
        "provisioning_preflight": "tools/check_modern_release.py",
        "provisioning_tool": "tools/provision_modern.py",
        "qualification_attestation_workflow": (
            ".github/workflows/attest-modern-candidate.yml"),
        "qualification_validator": "tools/check_modern_qualification.py",
        "support_window": "profiles/modern-support-window.json",
        "migration_instructions": "profiles/lvgl-modern-migration.md",
        "filesystem_vendor_lock": "vendor/legacy-pydevices.lock.json",
    }
    if builder != expected_builder:
        raise ValueError("modern release builder contract is incomplete")
    for key in (
            "package_map", "provisioning_tool", "qualification_attestation_workflow",
            "qualification_validator", "support_window", "migration_instructions",
            "filesystem_vendor_lock"):
        if not (ROOT / builder[key]).is_file():
            raise ValueError(f"modern release builder input is missing: {key}")
    support_window = load_json(ROOT / builder["support_window"])
    validate_support_window(support_window)
    gates = profile.get("promotion_gates")
    if gates != [
            "adult-provisioning-and-migration",
            "profile-specific-hardware",
            "profile-specific-ota-and-recovery",
            "release-feed-isolation",
            "release-pipeline-qualification",
            "support-window"]:
        raise ValueError("modern release promotion gates are missing")

    firmware = profile.get("firmware_compatibility")
    if not isinstance(firmware, dict):
        raise ValueError("modern firmware compatibility is missing")
    firmware_expected = PROFILE_BOARD["firmware"]
    for key, value in firmware_expected.items():
        if firmware.get(key) != value:
            raise ValueError(f"modern compatible firmware has unexpected {key}")
    artifact = ROOT / firmware["artifact"]
    if not artifact.is_file() or sha256_file(artifact) != firmware["sha256"]:
        raise ValueError("modern compatible firmware artifact hash mismatch")

    candidate = profile.get("reference_candidate")
    if not isinstance(candidate, dict):
        raise ValueError("modern profile has no reference candidate")
    expected = {
        "status": "research-only-reproducible-hardware-qualified",
        "artifact": (
            "firmware/lvgl-modern/reference/"
            "lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16-phase5-reference.bin"),
        "lock": "firmware/lvgl-modern/reference.lock.json",
        "provenance": "firmware/lvgl-modern/reference/provenance.json",
    }
    for key, value in expected.items():
        if candidate.get(key) != value:
            raise ValueError(f"modern reference candidate has unexpected {key}")
    digest = candidate.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("modern reference candidate has an invalid SHA-256")

    adapter = profile.get("application_adapter")
    if not isinstance(adapter, dict) or \
            adapter.get("status") != "implemented-hardware-qualified":
        raise ValueError("modern application adapter is not hardware-qualified")
    inputs = adapter.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(
            APPLICATION_ADAPTER_INPUTS):
        raise ValueError("modern application adapter inputs are incomplete")
    actual_paths = {item.get("path") for item in inputs if isinstance(item, dict)}
    if actual_paths != APPLICATION_ADAPTER_INPUTS:
        raise ValueError("modern application adapter input paths do not match")
    for item in inputs:
        if not isinstance(item, dict):
            raise ValueError("modern application adapter input is invalid")
        path = ROOT / item["path"]
        if not path.is_file() or item.get("sha256") != sha256_source_file(path):
            raise ValueError(f"modern application adapter hash mismatch: {item['path']}")


def distribution_inventory(dist: Path) -> list[dict[str, object]]:
    if not dist.is_dir():
        raise ValueError(f"modern distribution not found: {dist}")
    for relative in REQUIRED_DIST_FILES:
        if not (dist / relative).is_file():
            raise ValueError(f"modern distribution is missing {relative}")

    inventory = []
    for path in sorted(item for item in dist.rglob("*") if item.is_file()):
        relative = path.relative_to(dist).as_posix()
        content = path.read_bytes()
        if path.suffix == ".py":
            try:
                compile(content, str(path), "exec")
            except SyntaxError as exc:
                raise ValueError(f"modern distribution does not compile: {relative}: {exc}") from exc
        inventory.append({
            "path": relative,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    if not inventory:
        raise ValueError("modern distribution is empty")
    return inventory


def check(profile_path: Path = DEFAULT_PROFILE, dist: Path | None = None,
          compare_dist: Path | None = None) -> dict[str, object]:
    """Validate the reference and, optionally, one or two filesystem builds."""

    check_modern_firmware_lock()
    validate_profile(load_json(profile_path))
    result: dict[str, object] = {
        "profile": "lvgl-modern",
        "artifact_status": "published",
        "release_version": "modern-v0.14.8",
        "release_repository": "tdhoward/TartLab-modern-releases",
    }
    if dist is not None:
        inventory = distribution_inventory(dist)
        result.update({
            "dist_files": len(inventory),
            "dist_sha256": hashlib.sha256(json.dumps(
                inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        })
        if compare_dist is not None:
            compared = distribution_inventory(compare_dist)
            if inventory != compared:
                raise ValueError("independent modern filesystem builds differ")
            result["independent_builds_match"] = True
    elif compare_dist is not None:
        raise ValueError("--compare-dist requires --dist")
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--compare-dist", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(check(args.profile, args.dist, args.compare_dist),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
