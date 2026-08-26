"""Check the non-promotable modern TartLab filesystem profile.

The LVGL reference firmware is a hardware-qualified research checkpoint, not a
release channel.  This checker gives it the same deterministic filesystem and
source-compatibility coverage as the legacy release path while making that
non-promotion boundary explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from modern_firmware import check_lock as check_modern_firmware_lock


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles/lvgl-modern.json"
REQUIRED_DIST_FILES = (
    "boot.py",
    "main.py",
    "configs/t_display_s3_pro_modern.py",
    "lib/tartlabutils/modern.py",
    "lib/tartlabutils/platform.py",
)


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
    """Ensure the profile stays limited to the qualified research reference."""

    if profile.get("schema") != 1 or profile.get("profile") != "lvgl-modern":
        raise ValueError("unexpected modern profile identity")
    if profile.get("status") != "experimental-unqualified":
        raise ValueError("modern profile must remain experimental and unqualified")
    if profile.get("release_channel") is not None:
        raise ValueError("modern profile must not define a release channel")
    if profile.get("release_builder") is not None:
        raise ValueError("modern profile must not define a release builder")
    if profile.get("hardware_qualification") is not None:
        raise ValueError("modern profile must not claim release qualification")

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
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise ValueError("modern application adapter inputs are incomplete")
    expected_paths = {
        "src/lib/tartlabutils/modern.py",
        "src/configs/t_display_s3_pro_modern.py",
    }
    actual_paths = {item.get("path") for item in inputs if isinstance(item, dict)}
    if actual_paths != expected_paths:
        raise ValueError("modern application adapter input paths do not match")
    for item in inputs:
        if not isinstance(item, dict):
            raise ValueError("modern application adapter input is invalid")
        path = ROOT / item["path"]
        if not path.is_file() or item.get("sha256") != sha256_file(path):
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
        "artifact_status": "research-only-not-for-promotion",
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
