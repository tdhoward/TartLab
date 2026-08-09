"""Create or verify the historical legacy PyDevices content lock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from release_utils import file_inventory, inventory_identifier, read_json, write_json


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/lib/pydevices"
FIXTURE_INVENTORY = ROOT / "tests/fixtures/legacy_mp123/inventory.json"
LOCK = ROOT / "vendor/legacy-pydevices.lock.json"


def git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True,
        stderr=subprocess.DEVNULL).strip()


def deployed_inventory() -> list[dict[str, object]]:
    prefix = "lib/pydevices/"
    result = []
    for item in read_json(FIXTURE_INVENTORY):
        path = str(item.get("path", ""))
        if path.startswith(prefix) and "sha256" in item:
            result.append({
                "path": path[len(prefix):],
                "size": item["size"],
                "sha256": item["sha256"],
            })
    return sorted(result, key=lambda item: str(item["path"]))


def make_lock() -> dict[str, object]:
    source_files = file_inventory(SOURCE, normalize_source_text=True)
    deployed_files = deployed_inventory()
    last_change = git_value("rev-list", "-1", "HEAD", "--", "src/lib/pydevices")
    return {
        "schema": 1,
        "name": "legacy-pydevices",
        "source_path": "src/lib/pydevices",
        "identifier": inventory_identifier(source_files),
        "files": source_files,
        "provenance": {
            "upstream_repository": "https://github.com/PyDevices/pydisplay",
            "upstream_commit": None,
            "status": "incomplete-historical-snapshot",
            "note": (
                "The historical distillation did not record an upstream commit. "
                "This lock preserves the exact TartLab source and deployed payload "
                "identities before Phase 4 replacement work begins."
            ),
            "distillation_script": "distill_pydevices.py",
            "last_tartlab_commit_affecting_source": last_change,
        },
        "deployed_legacy_mp123": {
            "source": "tests/fixtures/legacy_mp123/inventory.json",
            "identifier": inventory_identifier(deployed_files),
            "file_count": len(deployed_files),
            "expanded_bytes": sum(int(item["size"]) for item in deployed_files),
            "phase1_tested_archive_sha256": (
                "ba29c18c126de7b08964d6ad8150dd1e7f7e2dbab24e0b03c4bbfda0070567a1"
            ),
        },
    }


def check_lock(expected: dict[str, object] | None = None) -> dict[str, object]:
    expected = expected or read_json(LOCK)
    actual_source = file_inventory(SOURCE, normalize_source_text=True)
    actual_identifier = inventory_identifier(actual_source)
    if actual_identifier != expected.get("identifier"):
        raise ValueError(
            "Vendored source differs from vendor/legacy-pydevices.lock.json; "
            "review provenance and regenerate the lock explicitly")
    if actual_source != expected.get("files"):
        raise ValueError("Vendored file inventory differs from its content lock")
    actual_deployed = deployed_inventory()
    deployed = expected.get("deployed_legacy_mp123", {})
    if inventory_identifier(actual_deployed) != deployed.get("identifier"):
        raise ValueError("Sanitized deployed fixture differs from the vendor lock")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true",
        help="replace the lock after explicitly reviewing a vendor payload change")
    args = parser.parse_args()
    if args.write:
        value = make_lock()
        write_json(LOCK, value)
        print("Wrote %s (%s)" % (LOCK.relative_to(ROOT), value["identifier"]))
    else:
        value = check_lock()
        print("Verified %s" % value["identifier"])


if __name__ == "__main__":
    main()
