"""Verify tracked firmware binaries against manifests and modern build locks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from board_catalog import BoardCatalogError, load_catalog
from modern_firmware import check_lock as check_modern_firmware_lock


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
CHUNK_SIZE = 64 * 1024
LEGACY_RUNTIME_IDENTITY_REGIONS = [
    {
        "name": "bootloader-and-partition-table",
        "offset": 0,
        "size": 36864,
        "sha256": "6b22cf113eaffda9ac43e236f873c62dccceed233f1d0f5114b5e8b3de1ca414",
    },
    {
        "name": "factory-application",
        "offset": 65536,
        "size": 1565888,
        "sha256": "9d6998170b5bf7e8568be2aa2845e25fe98bd622f945e1fdd9740a35b12ffa8d",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_region(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            chunk = stream.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise ValueError("firmware identity region exceeds the artifact")
            digest.update(chunk)
            remaining -= len(chunk)
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

    identity_regions = artifact.get("runtime_identity_regions")
    if identity_regions is not None:
        if not isinstance(identity_regions, list) or not identity_regions:
            errors.append(
                f"{manifest_path.relative_to(ROOT)}: invalid identity regions")
        else:
            for region in identity_regions:
                try:
                    offset = region["offset"]
                    size = region["size"]
                    expected = region["sha256"]
                    if not isinstance(offset, int) or offset < 0 or \
                            not isinstance(size, int) or size <= 0:
                        raise ValueError("invalid offset or size")
                    actual = sha256_region(binary_path, offset, size)
                    if actual != expected:
                        raise ValueError("SHA-256 mismatch")
                except (KeyError, TypeError, ValueError) as exc:
                    errors.append(
                        f"{manifest_path.relative_to(ROOT)}: invalid firmware "
                        f"identity region: {exc}")

    profile_name = manifest.get("profile")
    if profile_name == "legacy-mp123" and \
            identity_regions != LEGACY_RUNTIME_IDENTITY_REGIONS:
        errors.append(
            f"{manifest_path.relative_to(ROOT)}: unexpected legacy runtime "
            "identity regions")
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
    if "manifest" in compatibility:
        expected_profile_values = {
            "image": filename,
            "sha256": actual_hash,
            "manifest": manifest_reference,
        }
        if identity_regions is not None:
            expected_profile_values["runtime_identity_regions"] = identity_regions
        for key, expected in expected_profile_values.items():
            actual = compatibility.get(key)
            if actual != expected:
                errors.append(
                    f"{profile_path.relative_to(ROOT)}: {key} is {actual!r}, "
                    f"expected {expected!r}"
                )
    elif "artifact" not in compatibility:
        errors.append(
            f"{profile_path.relative_to(ROOT)}: firmware compatibility must "
            "select a manifest or a locked artifact"
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
    modern_lock = FIRMWARE / "lvgl-modern/reference.lock.json"
    modern_count = 0
    if modern_lock.is_file():
        try:
            check_modern_firmware_lock(modern_lock)
            modern_count = 1
        except ValueError as exc:
            errors.append(f"{modern_lock.relative_to(ROOT)}: {exc}")
    board_count = 0
    try:
        board_count = len(load_catalog())
    except BoardCatalogError as exc:
        errors.append(f"board catalog: {exc}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        f"Verified {len(manifests) + modern_count} firmware artifacts and "
        f"{board_count} board descriptors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
