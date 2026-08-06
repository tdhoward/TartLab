"""Create a sanitized TartLab legacy-layout fixture without copying device secrets."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


PROTECTED_PREFIXES = (
    "app.py", "hdwconfig.py", "settings.json", "repos.json", "logs/", "files/user/", "boot.py",
)
CAPTURE_METADATA_FILES = {"snapshot_manifest.json"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ownership(relative):
    value = relative.as_posix()
    if value == "boot.py":
        return "firmware"
    if value in ("app.py", "hdwconfig.py", "settings.json", "repos.json"):
        return "protected-state"
    if value.startswith("logs/") or value.startswith("files/user/"):
        return "protected-state"
    return "update-managed"


def selected_app(source):
    try:
        lines = (source / "app.py").read_text(encoding="utf-8").splitlines()
        if len(lines) >= 2 and lines[1].startswith("# ") and lines[1][2:].endswith(".py"):
            return lines[1][2:]
    except OSError:
        pass
    return "hello.py"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_fixture(source, output, args):
    files = sorted(
        path for path in source.rglob("*")
        if path.is_file() and path.relative_to(source).as_posix() not in CAPTURE_METADATA_FILES
    )
    inventory = []
    for path in files:
        relative = path.relative_to(source)
        item_ownership = ownership(relative)
        if item_ownership != "update-managed":
            continue
        item = {
            "path": relative.as_posix(),
            "size": path.stat().st_size,
            "ownership": item_ownership,
            "sha256": sha256(path),
        }
        inventory.append(item)

    app_name = "hello.py" if selected_app(source) == "hello.py" else "selected_app.py"
    layout = output / "layout"
    if layout.exists():
        shutil.rmtree(layout)
    write_json(layout / "settings.json", {
        "dbver": 1,
        "STARTUP_MODE": "BUTTON",
        "pre-release-updates": False,
        "ap_name": "PySyntheticDevice42",
        "hostname": "tartlab-fixture",
        "wifi_ssids": ["SYNTHETIC_CLASSROOM"],
        "wifi_passwords": ["not-a-real-password"],
    })
    write_json(layout / "repos.json", {
        "dbver": 1,
        "list": [{
            "name": "TartLab",
            "repo": "tdhoward/tartlab",
            "installed_version": "v0.13",
        }],
    })
    (layout / "app.py").write_text(
        "# Sanitized legacy generated launcher\n# %s\n# Import removed from fixture.\n" % app_name,
        encoding="utf-8",
    )
    (layout / "hdwconfig.py").write_text(
        "# Sanitized board selector\nfrom t_display_s3_pro import *\n", encoding="utf-8")
    (layout / "files" / "user").mkdir(parents=True, exist_ok=True)
    (layout / "files" / "user" / "hello.py").write_text(
        "print('Synthetic fixture app')\n", encoding="utf-8")
    if app_name != "hello.py":
        selected = layout / "files" / "user" / app_name
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_text("# Synthetic selected-app placeholder\n", encoding="utf-8")
    (layout / "logs").mkdir(parents=True, exist_ok=True)
    for name in ("000000.log", "000001.log", "000002.log", "000003.log", "000004.log"):
        (layout / "logs" / name).write_text("Sanitized legacy boot log\n", encoding="utf-8")

    inventory.append({
        "path": "boot.py",
        "ownership": "firmware",
        "content": "excluded",
    })
    for path in sorted(item for item in layout.rglob("*") if item.is_file()):
        inventory.append({
            "path": path.relative_to(layout).as_posix(),
            "size": path.stat().st_size,
            "ownership": "protected-state",
            "content": "sanitized",
        })
    inventory.sort(key=lambda item: item["path"])

    metadata = {
        "schema": 1,
        "sanitized": True,
        "release_gate_ready": args.release_gate_ready,
        "source_capture": source.name,
        "board": {
            "model": "LilyGO T-Display-S3 Pro",
            "revision": args.board_revision,
        },
        "firmware": {
            "image": "ESP32_GENERIC_S3-SPIRAM_OCT-20240602-v1.23.0.bin",
            "sha256": args.firmware_sha256,
        },
        "capture_method": args.capture_method,
        "filesystem": {
            "capacity_bytes": args.filesystem_capacity,
            "free_bytes": args.filesystem_free,
        },
        "source_file_count": len(files),
        "source_content_bytes": sum(path.stat().st_size for path in files),
        "inventory": "inventory.json",
    }
    if args.release_gate_ready:
        missing = [key for key, value in (
            ("board revision", args.board_revision),
            ("firmware SHA-256", args.firmware_sha256),
            ("capture method", args.capture_method),
            ("filesystem capacity", args.filesystem_capacity),
            ("filesystem free space", args.filesystem_free),
        ) if value in (None, "", "UNRECORDED")]
        if missing:
            raise ValueError("Release-ready fixture is missing: " + ", ".join(missing))
    write_json(output / "metadata.json", metadata)
    write_json(output / "inventory.json", inventory)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--board-revision", default="UNRECORDED")
    parser.add_argument("--firmware-sha256", default="UNRECORDED")
    parser.add_argument("--capture-method", default="Existing directory capture; original procedure unrecorded")
    parser.add_argument("--filesystem-capacity", type=int)
    parser.add_argument("--filesystem-free", type=int)
    parser.add_argument("--release-gate-ready", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    options = parse_args()
    build_fixture(options.source.resolve(), options.output.resolve(), options)
