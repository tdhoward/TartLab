"""Create deterministic, legacy-compatible TartLab OTA release assets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from release_utils import (
    ensure_safe_output, file_inventory, inventory_identifier, read_json,
    sha256_file, sha256_source_file, write_json,
)
from pydevices_inventory import check_inventory as check_pydevices_inventory
from pydevices_upstream import check_upstream_mapping
from vendor_pydevices import check_vendor_lock as check_pydevices_candidate_lock
from vendor_lock import check_lock


PROTECTED_PATHS = (
    "/app.py", "/hdwconfig.py", "/settings.json", "/repos.json", "/logs",
    "/device", "/state", "/files/user",
)


def is_protected_path(path):
    normalized = "/" + str(path).strip("/")
    return any(
        normalized == protected or normalized.startswith(protected + "/")
        for protected in PROTECTED_PATHS)


def calculate_sha256(file_path):
    return sha256_file(Path(file_path))


def _tar_info(tar: tarfile.TarFile, path: Path, arcname: str, mtime: int):
    info = tar.gettarinfo(str(path), arcname=arcname)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o644
    info.mtime = int(mtime)
    return info


def create_tarfile(
        name, source, exclude_subdirs, output_dir, excludes=None, mtime=0):
    """Create a stable USTAR containing files only, in lexical path order."""

    excludes = set(excludes or [])
    source = Path(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tar_path = output_dir / (name + ".tar")
    if exclude_subdirs:
        paths = [
            path for path in source.iterdir()
            if path.is_file() and path.name not in excludes
        ]
    else:
        paths = [
            path for path in source.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and
            path.suffix.lower() not in (".pyc", ".pyo")
        ]
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        for path in sorted(paths, key=lambda item: item.relative_to(source).as_posix()):
            arcname = path.relative_to(source).as_posix()
            info = _tar_info(tar, path, arcname, mtime)
            with path.open("rb") as stream:
                tar.addfile(info, stream)
    return str(tar_path)


def archive_paths(tar_path, target):
    target = "/" + target.strip("/")
    if target == "/":
        target = ""
    with tarfile.open(tar_path, "r") as tar:
        return sorted(
            target + "/" + member.name.replace("\\", "/")
            for member in tar.getmembers() if member.isfile())


def validate_archive_ownership(paths):
    for path in paths:
        normalized = "/" + path.strip("/")
        if is_protected_path(normalized):
            raise ValueError("Release archive targets protected path: %s" % normalized)


def _git_value(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True,
        stderr=subprocess.DEVNULL).strip()


def _epoch(configured=None):
    if configured is not None:
        return int(configured)
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        return int(_git_value("log", "-1", "--format=%ct"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def _actual_toolchain():
    try:
        minifier = importlib.metadata.version("python-minifier")
    except importlib.metadata.PackageNotFoundError:
        minifier = None
    try:
        node = subprocess.check_output(
            ["node", "--version"], text=True,
            stderr=subprocess.DEVNULL).strip().lstrip("v")
    except (OSError, subprocess.CalledProcessError):
        node = None
    return {
        "python": "%s.%s.%s" % sys.version_info[:3],
        "python_minifier": minifier,
        "node": node,
    }


def _numeric_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+)*", value):
        raise ValueError("Tool versions must contain dot-separated integers: %r" % value)
    return tuple(int(part) for part in value.split("."))


def _requirement_label(requirement):
    if isinstance(requirement, str):
        return requirement
    if not isinstance(requirement, dict):
        raise ValueError("Toolchain requirements must be a version or range object")
    unknown = set(requirement).difference(("min_inclusive", "max_exclusive"))
    if unknown:
        raise ValueError("Unknown toolchain requirement field: %s" % sorted(unknown)[0])
    parts = []
    if "min_inclusive" in requirement:
        _numeric_version(requirement["min_inclusive"])
        parts.append(">=" + requirement["min_inclusive"])
    if "max_exclusive" in requirement:
        _numeric_version(requirement["max_exclusive"])
        parts.append("<" + requirement["max_exclusive"])
    if not parts:
        raise ValueError("Toolchain version range must define at least one bound")
    return ",".join(parts)


def _matches_requirement(actual, requirement):
    if isinstance(requirement, str):
        return actual == requirement
    _requirement_label(requirement)
    if actual is None:
        return False
    try:
        version = _numeric_version(actual)
    except ValueError:
        return False
    minimum = requirement.get("min_inclusive")
    maximum = requirement.get("max_exclusive")
    return (minimum is None or version >= _numeric_version(minimum)) and \
        (maximum is None or version < _numeric_version(maximum))


def _check_toolchain(required, actual):
    mismatches = []
    for name, requirement in required.items():
        if not _matches_requirement(actual.get(name), requirement):
            mismatches.append(
                "%s=%s (required %s)" % (
                    name, actual.get(name), _requirement_label(requirement)))
    if mismatches:
        raise ValueError(
            "Build toolchain does not match the legacy profile: " + "; ".join(mismatches))


def _expanded_size(tar_path):
    with tarfile.open(tar_path, "r") as archive:
        return sum(member.size for member in archive.getmembers() if member.isfile())


def _package_source(dist: Path, source_text: str):
    top_only = source_text.endswith("*")
    relative = source_text.rstrip("*").replace("\\", "/")
    if relative == "dist/":
        relative = ""
    elif relative.startswith("dist/"):
        relative = relative[len("dist/"):]
    else:
        raise ValueError("Package source must be beneath dist/: %s" % source_text)
    return dist / relative.strip("/"), top_only


def _check_size_budgets(metadata, profile):
    budgets = profile["size_budgets"]
    if metadata["totals"]["archive_bytes"] > budgets["archive_bytes"]:
        raise ValueError("Release archive total exceeds legacy profile budget")
    if metadata["totals"]["expanded_bytes"] > budgets["expanded_bytes"]:
        raise ValueError("Release expanded total exceeds legacy profile budget")
    pydevices = next(
        item for item in metadata["packages"] if item["name"] == "pydevices")
    if pydevices["archive_size"] > budgets["pydevices_archive_bytes"]:
        raise ValueError("PyDevices archive exceeds legacy profile budget")
    if pydevices["expanded_size"] > budgets["pydevices_expanded_bytes"]:
        raise ValueError("PyDevices payload exceeds legacy profile budget")


def _baseline_comparison(dist_inventory, profile):
    fixture_path = ROOT / profile["baseline"]["fixture"] / "inventory.json"
    baseline_items = [
        item for item in read_json(fixture_path)
        if item.get("ownership") == "update-managed" and "sha256" in item
    ]
    baseline = {item["path"]: item for item in baseline_items}
    current = {item["path"]: item for item in dist_inventory}
    unchanged = []
    changed = []
    removed = []
    for path, old in sorted(baseline.items()):
        new = current.get(path)
        if new is None:
            removed.append(path)
        elif new["sha256"] == old["sha256"]:
            unchanged.append(path)
        else:
            changed.append(path)
    added = sorted(set(current).difference(baseline))
    return {
        "baseline": str(fixture_path.relative_to(ROOT)).replace("\\", "/"),
        "baseline_files": len(baseline),
        "current_dist_files": len(current),
        "unchanged": unchanged,
        "changed": changed,
        "added": added,
        "removed": removed,
        "counts": {
            "unchanged": len(unchanged),
            "changed": len(changed),
            "added": len(added),
            "removed": len(removed),
        },
    }


def validate_research_vendor(provenance_path: Path, runtime: Path):
    """Validate an exact generated vendor tree for a research-only release."""

    provenance_path = provenance_path.resolve()
    runtime = runtime.resolve()
    provenance = read_json(provenance_path)
    if provenance.get("promotion_status") != "research-only":
        raise ValueError("Research vendor provenance must remain research-only")
    if provenance.get("profile") != "legacy-mp123-candidate":
        raise ValueError("Unexpected research vendor profile")
    lock_file = provenance.get("lock_file")
    if lock_file != "vendor/pydevices-candidate.lock.json":
        raise ValueError("Unexpected research vendor lock file")
    lock_path = ROOT / lock_file
    if provenance.get("lock_sha256") != sha256_source_file(lock_path):
        raise ValueError("Research vendor lock hash mismatch")

    records = (
        list(provenance.get("selected_files", [])) +
        list(provenance.get("compatibility_files", []))
    )
    expected = {}
    for record in records:
        destination = record.get("destination")
        if (not isinstance(destination, str) or not destination or
                Path(destination).is_absolute() or ".." in Path(destination).parts):
            raise ValueError("Unsafe research vendor destination: %r" % destination)
        if destination in expected:
            raise ValueError("Duplicate research vendor destination: " + destination)
        expected[destination] = {
            "path": destination,
            "size": record.get("output_size"),
            "sha256": record.get("output_sha256"),
        }

    actual_inventory = file_inventory(runtime, normalize_source_text=True)
    actual = {item["path"]: item for item in actual_inventory}
    if actual != expected:
        missing = sorted(set(expected).difference(actual))
        unexpected = sorted(set(actual).difference(expected))
        changed = sorted(
            path for path in set(actual).intersection(expected)
            if actual[path] != expected[path])
        raise ValueError(
            "Research vendor runtime mismatch: missing=%r unexpected=%r changed=%r" %
            (missing, unexpected, changed))
    identifier = inventory_identifier(actual_inventory)
    if identifier != provenance.get("runtime_identifier"):
        raise ValueError("Research vendor runtime identifier mismatch")
    return provenance


def validate_promoted_vendor(profile, provenance, compilation,
                             packaged_identifier, packaged_files):
    """Bind a generated runtime to the exact Phase 4 qualified payload."""

    promoted = profile.get("promoted_vendor")
    if not isinstance(promoted, dict):
        raise ValueError("Release profile does not approve a promoted vendor")
    expected = {
        "profile": provenance.get("profile"),
        "lock_file": provenance.get("lock_file"),
        "source_runtime_identifier": provenance.get("runtime_identifier"),
        "source_runtime_files": (
            len(provenance.get("selected_files", [])) +
            len(provenance.get("compatibility_files", []))),
        "packaged_runtime_identifier": packaged_identifier,
        "packaged_runtime_files": packaged_files,
        "target_arch": compilation.get("target_arch"),
    }
    mismatches = [
        name for name, actual in expected.items()
        if promoted.get(name) != actual
    ]
    compiler_version = compilation.get("compiler_version", "")
    for name in ("mpy_version", "mpy_format"):
        if promoted.get(name) not in compiler_version:
            mismatches.append(name)
    if compilation.get("modules") != promoted.get("packaged_runtime_files"):
        mismatches.append("compiled_modules")
    if compilation.get("packaged_identifier") != packaged_identifier:
        mismatches.append("compiled_identifier")
    gate = promoted.get("physical_gate")
    if not isinstance(gate, str) or not (ROOT / gate).is_file():
        mismatches.append("physical_gate")
    if mismatches:
        raise ValueError(
            "Generated vendor differs from the Phase 4 promoted payload: %s" %
            ", ".join(sorted(set(mismatches))))
    return promoted


def build_release(
        dist: Path, output: Path, version: str, *, clean=False,
        profile_path: Path | None = None, packages_path: Path | None = None,
        source_epoch: int | None = None, allow_dirty=True,
        allow_toolchain_mismatch=True,
        research_vendor_provenance: Path | None = None,
        research_vendor_source: Path | None = None,
        promoted_vendor_compilation: dict | None = None,
        require_promoted_vendor=False):
    dist = dist.resolve()
    output = ensure_safe_output(output, (ROOT, dist))
    if output.exists():
        if not clean:
            raise FileExistsError(
                "Output already exists; rerun with --clean to remove it first: %s" % output)
        shutil.rmtree(output)
    output.mkdir(parents=True)
    if not version or any(character.isspace() for character in version):
        raise ValueError("Version must be a non-empty value without whitespace")

    profile_path = profile_path or ROOT / "profiles/legacy-mp123.json"
    packages_path = packages_path or ROOT / "tartlab_packages.json"
    profile = read_json(profile_path)
    packages = read_json(packages_path)
    vendor = check_lock()
    check_upstream_mapping()
    check_pydevices_candidate_lock()
    research_vendor = None
    if (research_vendor_provenance is None and
            research_vendor_source is not None):
        raise ValueError(
            "Research vendor source requires provenance")
    if research_vendor_provenance is None:
        if require_promoted_vendor and profile.get("promoted_vendor"):
            raise ValueError(
                "The legacy profile requires the promoted PyDevices release builder")
        check_pydevices_inventory(dist=dist)
    else:
        research_vendor = validate_research_vendor(
            research_vendor_provenance,
            research_vendor_source or dist / "lib/pydevices")
    if promoted_vendor_compilation is not None and research_vendor is None:
        raise ValueError("Promoted vendor compilation requires provenance")
    try:
        commit = _git_value("rev-parse", "HEAD")
        dirty = bool(_git_value("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
        dirty = True
    if dirty and not allow_dirty:
        raise ValueError("Release builds require a clean Git working tree")
    epoch = _epoch(source_epoch)

    manifest = []
    archive_inventory = {}
    payload_inventory = {}
    package_metadata = []
    owned_paths = set()
    for package in packages:
        source, top_only = _package_source(dist, package["source"])
        if not source.is_dir():
            raise FileNotFoundError("Package source does not exist: %s" % source)
        tar_path = Path(create_tarfile(
            package["name"], source, top_only, output,
            package.get("exclude", []), mtime=epoch))
        paths = archive_paths(tar_path, package["target"])
        if not paths:
            raise ValueError("Package is empty: %s" % package["name"])
        validate_archive_ownership(paths)
        duplicates = owned_paths.intersection(paths)
        if duplicates:
            raise ValueError("Archive ownership overlaps: %s" % sorted(duplicates)[0])
        owned_paths.update(paths)
        expanded_size = _expanded_size(tar_path)
        archive_hash = sha256_file(tar_path)
        archive_inventory[package["name"]] = paths
        with tarfile.open(tar_path, "r") as archive:
            members = []
            for member in sorted(
                    (item for item in archive.getmembers() if item.isfile()),
                    key=lambda item: item.name):
                stream = archive.extractfile(member)
                content = stream.read()
                members.append({
                    "path": member.name,
                    "size": member.size,
                    "sha256": hashlib.sha256(content).hexdigest(),
                })
            payload_inventory[package["name"]] = members
        entry = {
            "file_name": tar_path.name,
            "sha256": archive_hash,
            "target": package["target"],
            "clear_first": package["clear_first"],
            "ownership": package.get("ownership", "system"),
            "archive_size": tar_path.stat().st_size,
            "expanded_size": expanded_size,
        }
        manifest.append(entry)
        package_metadata.append({"name": package["name"], **entry})

    write_json(output / "manifest.json", manifest)
    write_json(output / "archive_inventory.json", archive_inventory)
    write_json(output / "payload_inventory.json", payload_inventory)
    dist_inventory = file_inventory(dist)
    required_ota_paths = {
        "/" + item["path"].strip("/") for item in dist_inventory
        if not is_protected_path(item["path"])
    }
    missing_ota_paths = sorted(required_ota_paths.difference(owned_paths))
    if missing_ota_paths:
        raise ValueError(
            "Distribution file has no OTA package owner: %s" % missing_ota_paths[0])
    write_json(output / "dist_inventory.json", dist_inventory)
    baseline_comparison = _baseline_comparison(dist_inventory, profile)
    if baseline_comparison["removed"]:
        if research_vendor is None:
            raise ValueError(
                "Clean build dropped files from the deployed legacy inventory: %s" %
                baseline_comparison["removed"][0])
        unexpected_removed = [
            path for path in baseline_comparison["removed"]
            if not path.startswith("lib/pydevices/")
        ]
        if unexpected_removed:
            raise ValueError(
                "Research build dropped a non-vendor legacy file: %s" %
                unexpected_removed[0])
    write_json(output / "baseline_comparison.json", baseline_comparison)
    actual_toolchain = _actual_toolchain()
    if not allow_toolchain_mismatch:
        _check_toolchain(profile["build_toolchain"], actual_toolchain)
    vendor_payload = {
        "identifier": inventory_identifier(file_inventory(dist / "lib/pydevices")),
        "deployed_baseline_identifier": vendor["deployed_legacy_mp123"]["identifier"],
    }
    promoted_vendor = None
    if research_vendor is None:
        vendor_payload.update({
            "source_lock_identifier": vendor["identifier"],
            "lock_file": profile["vendor_lock"],
        })
    else:
        packaged_inventory = file_inventory(dist / "lib/pydevices")
        packaged_identifier = inventory_identifier(packaged_inventory)
        if promoted_vendor_compilation is not None:
            promoted_vendor = validate_promoted_vendor(
                profile, research_vendor, promoted_vendor_compilation,
                packaged_identifier, len(packaged_inventory))
        vendor_payload.update({
            "lock_file": research_vendor["lock_file"],
            "lock_sha256": research_vendor["lock_sha256"],
            "profile": research_vendor["profile"],
            "promotion_status": (
                "promoted" if promoted_vendor is not None else "research-only"),
            "provenance_sha256": sha256_source_file(
                Path(research_vendor_provenance)),
            "source_runtime_identifier": research_vendor["runtime_identifier"],
        })
        if promoted_vendor is not None:
            vendor_payload.update({
                "compiler_sha256": promoted_vendor_compilation["compiler_sha256"],
                "compiler_version": promoted_vendor_compilation["compiler_version"],
                "packaged_runtime_identifier": packaged_identifier,
                "physical_gate": promoted_vendor["physical_gate"],
                "qualified_candidate": promoted_vendor["qualified_candidate"],
                "target_arch": promoted_vendor_compilation["target_arch"],
            })

    metadata = {
        "schema": 1,
        "tartlab_version": version,
        "profile": profile["profile"],
        "git_commit": commit,
        "git_dirty": dirty,
        "build_timestamp_utc": datetime.fromtimestamp(
            epoch, timezone.utc).isoformat().replace("+00:00", "Z"),
        "build_timestamp_basis": "SOURCE_DATE_EPOCH",
        "source_date_epoch": epoch,
        "firmware_compatibility": profile["firmware_compatibility"],
        "vendor_payload": vendor_payload,
        "inputs": {
            "package_map_sha256": sha256_source_file(packages_path),
            "profile_sha256": sha256_source_file(profile_path),
            "web_package_lock_sha256": sha256_source_file(
                ROOT / "src/ide/www/package-lock.json"),
        },
        "toolchain": {
            "required": profile["build_toolchain"],
            "actual": actual_toolchain,
        },
        "packages": package_metadata,
        "totals": {
            "package_count": len(manifest),
            "archive_bytes": sum(item["archive_size"] for item in manifest),
            "expanded_bytes": sum(item["expanded_size"] for item in manifest),
            "dist_files": len(dist_inventory),
            "dist_bytes": sum(int(item["size"]) for item in dist_inventory),
        },
        "baseline": profile["baseline"],
        "baseline_comparison": baseline_comparison["counts"],
        "size_budgets": profile["size_budgets"],
    }
    if research_vendor is not None and promoted_vendor is None:
        metadata["artifact_status"] = "research-only-not-for-promotion"
    elif research_vendor is None and profile.get("promoted_vendor"):
        metadata["artifact_status"] = "historical-vendor-diagnostic"
    _check_size_budgets(metadata, profile)
    write_json(output / "build_metadata.json", metadata)
    checksums = {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir()) if path.is_file()
    }
    write_json(output / "checksums.json", checksums)
    return metadata


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "profiles/legacy-mp123.json")
    parser.add_argument(
        "--packages", type=Path, default=ROOT / "tartlab_packages.json")
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument(
        "--allow-toolchain-mismatch", action="store_true",
        help="diagnostic-only override; artifacts are not promotion eligible")
    return parser.parse_args()


def main():
    args = parse_args()
    metadata = build_release(
        args.dist, args.output, args.version, clean=args.clean,
        profile_path=args.profile, packages_path=args.packages,
        source_epoch=args.source_date_epoch, allow_dirty=args.allow_dirty,
        allow_toolchain_mismatch=args.allow_toolchain_mismatch,
        require_promoted_vendor=True)
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
