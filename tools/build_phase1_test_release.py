"""Build a noninteractive Phase 1 hardware-test release from the known v0.13 dist."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release as release_tools


OVERLAY_FILES = (
    "boot.py",
    "main.py",
    "ide/__init__.py",
    "ide/ide.py",
)
OVERLAY_DIRS = (
    "defaults",
    "recovery",
    "lib/tartlabutils",
)
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_value(*args):
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def build(output):
    output = output.resolve()
    if output == ROOT or ROOT not in output.parents:
        raise ValueError("Output must be a dedicated directory inside the repository")
    if output.exists():
        shutil.rmtree(output)
    dist = output / "dist"
    archives = output / "release"
    shutil.copytree(ROOT / "dist", dist, ignore=COPY_IGNORE)
    archives.mkdir(parents=True)

    for relative in OVERLAY_FILES:
        source = ROOT / "src" / relative
        target = dist / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in OVERLAY_DIRS:
        source = ROOT / "src" / relative
        target = dist / relative
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=COPY_IGNORE)

    packages = json.loads((ROOT / "tartlab_packages.json").read_text(encoding="utf-8"))
    manifest = []
    inventory = {}
    expanded_total = 0
    for package in packages:
        source_text = package["source"]
        top_only = source_text.endswith("*")
        relative_source = source_text.rstrip("*").replace("dist/", "", 1).strip("/")
        source = dist / relative_source
        archive = Path(release_tools.create_tarfile(
            package["name"], str(source), top_only, str(archives), package.get("exclude", [])))
        paths = release_tools.archive_paths(archive, package["target"])
        release_tools.validate_archive_ownership(paths)
        inventory[package["name"]] = paths
        expanded_size = sum(
            path.stat().st_size for path in source.rglob("*") if path.is_file()) if not top_only else sum(
                path.stat().st_size for path in source.iterdir()
                if path.is_file() and path.name not in package.get("exclude", []))
        expanded_total += expanded_size
        manifest.append({
            "file_name": archive.name,
            "sha256": sha256(archive),
            "target": package["target"],
            "clear_first": package["clear_first"],
            "ownership": package.get("ownership", "system"),
            "archive_size": archive.stat().st_size,
            "expanded_size": expanded_size,
        })

    (archives / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (archives / "archive_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "schema": 1,
        "version": "phase1-hwtest",
        "profile": "legacy-mp123",
        "git_commit": git_value("rev-parse", "HEAD"),
        "git_dirty": bool(git_value("status", "--porcelain")),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "package_count": len(manifest),
        "archive_bytes": sum((archives / item["file_name"]).stat().st_size for item in manifest),
        "expanded_bytes": expanded_total,
    }
    (archives / "test_release_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = build(args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
