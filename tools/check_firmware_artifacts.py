"""Verify tracked firmware binaries against their neighboring manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
CHUNK_SIZE = 64 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_manifest(manifest_path: Path) -> list[str]:
    errors = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{manifest_path.relative_to(ROOT)}: {exc}"]

    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        return [f"{manifest_path.relative_to(ROOT)}: missing artifact object"]

    filename = artifact.get("file")
    if not isinstance(filename, str) or Path(filename).name != filename:
        return [
            f"{manifest_path.relative_to(ROOT)}: artifact file must be a filename"
        ]

    binary_path = manifest_path.parent / filename
    if binary_path.suffix.lower() != ".bin":
        errors.append(f"{binary_path.relative_to(ROOT)}: expected a .bin file")
    if not binary_path.is_file():
        errors.append(f"{binary_path.relative_to(ROOT)}: file not found")
        return errors

    expected_size = artifact.get("size")
    actual_size = binary_path.stat().st_size
    if expected_size != actual_size:
        errors.append(
            f"{binary_path.relative_to(ROOT)}: size {actual_size}, "
            f"expected {expected_size}"
        )

    expected_hash = artifact.get("sha256")
    actual_hash = sha256_file(binary_path)
    if not isinstance(expected_hash, str) or expected_hash.lower() != actual_hash:
        errors.append(
            f"{binary_path.relative_to(ROOT)}: SHA-256 {actual_hash}, "
            f"expected {expected_hash}"
        )

    profile_name = manifest.get("profile")
    profile_path = ROOT / "profiles" / f"{profile_name}.json"
    if not isinstance(profile_name, str) or not profile_path.is_file():
        errors.append(
            f"{manifest_path.relative_to(ROOT)}: matching profile not found"
        )
        return errors

    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        compatibility = profile["firmware_compatibility"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        errors.append(f"{profile_path.relative_to(ROOT)}: {exc}")
        return errors

    manifest_reference = manifest_path.relative_to(ROOT).as_posix()
    expected_profile_values = {
        "image": filename,
        "sha256": actual_hash,
        "manifest": manifest_reference,
    }
    for key, expected in expected_profile_values.items():
        actual = compatibility.get(key)
        if actual != expected:
            errors.append(
                f"{profile_path.relative_to(ROOT)}: {key} is {actual!r}, "
                f"expected {expected!r}"
            )
    return errors


def main() -> int:
    manifests = sorted(FIRMWARE.rglob("manifest.json"))
    if not manifests:
        print("No firmware manifests found", file=sys.stderr)
        return 1

    errors = []
    for manifest in manifests:
        errors.extend(check_manifest(manifest))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"Verified {len(manifests)} firmware artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
