"""Validate a Phase 2 legacy distribution and its release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import release as release_tools
from pydevices_inventory import check_inventory as check_pydevices_inventory
from pydevices_upstream import check_upstream_mapping
from release_utils import file_inventory, read_json, sha256_file
from vendor_pydevices import check_vendor_lock as check_pydevices_candidate_lock
from vendor_lock import check_lock


def _compile_tree(root: Path) -> int:
    count = 0
    for path in sorted(root.rglob("*.py")):
        source = path.read_bytes()
        compile(source, str(path), "exec")
        count += 1
    return count


def _snapshot(root: Path, relatives: tuple[str, ...]) -> dict[str, bytes]:
    result = {}
    for relative in relatives:
        path = root / relative
        if path.is_file():
            result[relative] = path.read_bytes()
        elif path.is_dir():
            for child in sorted(item for item in path.rglob("*") if item.is_file()):
                result[child.relative_to(root).as_posix()] = child.read_bytes()
    return result


def _extract_generated_archive(archive_path: Path, target: Path) -> None:
    target = target.resolve()
    with tarfile.open(archive_path, "r") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            destination = (target / member.name).resolve()
            if target != destination and target not in destination.parents:
                raise ValueError("Archive escapes simulated device root")
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            with destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def _simulate_installs(dist: Path, release_dir: Path, manifest) -> dict[str, bool]:
    protected = (
        "app.py", "hdwconfig.py", "settings.json", "repos.json", "logs",
        "device", "state", "files/user",
    )
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        first = root / "first"
        shutil.copytree(dist, first)
        essentials = (
            "boot.py", "main.py", "app.py", "hdwconfig.py",
            "files/user/hello.py", "recovery/recovery.py",
        )
        if not all((first / relative).is_file() for relative in essentials):
            raise ValueError("Clean installation is missing a required file")

        device = root / "ota"
        shutil.copytree(ROOT / "tests/fixtures/legacy_mp123/layout", device)
        before = _snapshot(device, protected)
        installed_paths = []
        for package in manifest:
            relative_target = package["target"].strip("/")
            target = device / relative_target if relative_target else device
            if package["clear_first"] and target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            _extract_generated_archive(
                release_dir / package["file_name"], target)
            installed_paths.extend(
                release_tools.archive_paths(
                    release_dir / package["file_name"], package["target"]))
        if _snapshot(device, protected) != before:
            raise ValueError("OTA simulation changed protected device state")
        for path in installed_paths:
            if not (device / path.strip("/")).is_file():
                raise ValueError("OTA simulation did not install %s" % path)
        return {"clean_install": True, "captured_layout_ota": True}


def check(dist: Path, release_dir: Path) -> dict[str, object]:
    dist = dist.resolve()
    release_dir = release_dir.resolve()
    check_lock()
    check_pydevices_inventory(dist=dist)
    check_upstream_mapping()
    check_pydevices_candidate_lock()
    manifest = read_json(release_dir / "manifest.json")
    metadata = read_json(release_dir / "build_metadata.json")
    checksums = read_json(release_dir / "checksums.json")
    archive_inventory = read_json(release_dir / "archive_inventory.json")
    payload_inventory = read_json(release_dir / "payload_inventory.json")
    recorded_dist = read_json(release_dir / "dist_inventory.json")
    comparison = read_json(release_dir / "baseline_comparison.json")

    for filename, expected in checksums.items():
        path = release_dir / filename
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError("Release checksum mismatch: %s" % filename)
    if file_inventory(dist) != recorded_dist:
        raise ValueError("Distribution does not match dist_inventory.json")
    if comparison["removed"]:
        raise ValueError("Release removed a deployed legacy file")

    epoch = metadata["source_date_epoch"]
    paths = set()
    total_archive = 0
    total_expanded = 0
    for package in manifest:
        archive_path = release_dir / package["file_name"]
        if sha256_file(archive_path) != package["sha256"]:
            raise ValueError("Manifest hash mismatch: %s" % archive_path.name)
        if archive_path.stat().st_size != package["archive_size"]:
            raise ValueError("Manifest archive size mismatch: %s" % archive_path.name)
        package_name = archive_path.stem
        with tarfile.open(archive_path, "r") as archive:
            members = [item for item in archive.getmembers() if item.isfile()]
            if [item.name for item in members] != sorted(item.name for item in members):
                raise ValueError("Archive members are not sorted: %s" % archive_path.name)
            for member in members:
                if member.uid != 0 or member.gid != 0 or member.mtime != epoch:
                    raise ValueError("Archive metadata is not normalized")
            expanded = sum(item.size for item in members)
            actual_payload = []
            for member in members:
                stream = archive.extractfile(member)
                content = stream.read()
                actual_payload.append({
                    "path": member.name,
                    "size": member.size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                })
        if expanded != package["expanded_size"]:
            raise ValueError("Manifest expanded size mismatch: %s" % archive_path.name)
        archive_paths = release_tools.archive_paths(archive_path, package["target"])
        if archive_paths != archive_inventory[package_name]:
            raise ValueError("Archive path inventory mismatch: %s" % package_name)
        release_tools.validate_archive_ownership(archive_paths)
        overlap = paths.intersection(archive_paths)
        if overlap:
            raise ValueError("Package ownership overlap: %s" % sorted(overlap)[0])
        paths.update(archive_paths)
        recorded_payload = payload_inventory[package_name]
        if recorded_payload != actual_payload:
            raise ValueError("Payload content inventory mismatch: %s" % package_name)
        total_archive += package["archive_size"]
        total_expanded += expanded

    required_ota_paths = {
        "/" + item["path"].strip("/") for item in recorded_dist
        if not release_tools.is_protected_path(item["path"])
    }
    if paths != required_ota_paths:
        missing = sorted(required_ota_paths.difference(paths))
        extra = sorted(paths.difference(required_ota_paths))
        detail = missing[0] if missing else extra[0]
        raise ValueError("OTA package ownership differs from distribution: %s" % detail)

    if total_archive != metadata["totals"]["archive_bytes"] or \
            total_expanded != metadata["totals"]["expanded_bytes"]:
        raise ValueError("Release totals differ from build metadata")
    if metadata["profile"] != "legacy-mp123":
        raise ValueError("Unexpected build profile")
    compiled = _compile_tree(dist)
    simulations = _simulate_installs(dist, release_dir, manifest)
    return {
        "profile": metadata["profile"],
        "version": metadata["tartlab_version"],
        "packages": len(manifest),
        "compiled_python_files": compiled,
        "archive_bytes": total_archive,
        "expanded_bytes": total_expanded,
        "baseline_comparison": comparison["counts"],
        "simulations": simulations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.dist, args.release), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
