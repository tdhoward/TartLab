"""Validate and build a pinned, board-specific modern firmware image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
from typing import Any, Sequence

from modern_firmware import (
    checkout_source,
    docker_command,
    sha256_file,
    verify_source,
)
from release_utils import sha256_source_file


ROOT = Path(__file__).resolve().parents[1]
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
BOARD_ID_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
EXPECTED_SUBMODULES = {
    "lib/SDL",
    "lib/esp-idf",
    "lib/lvgl",
    "lib/micropython",
    "lib/pycparser",
}
EXPECTED_TRANSITIVE_SUBMODULES = {
    "lib/micropython/lib/berkeley-db-1.xx",
    "lib/micropython/lib/mbedtls",
    "lib/micropython/lib/micropython-lib",
    "lib/micropython/lib/tinyusb",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    _require(isinstance(value, dict), f"{path}: expected a JSON object")
    return value


def _validate_sources(lock: dict[str, Any]) -> None:
    source = lock.get("source")
    _require(isinstance(source, dict), "source must be an object")
    _require(
        source.get("repository") ==
        "https://github.com/lvgl-micropython/lvgl_micropython.git",
        "unexpected modern firmware source repository",
    )
    _require(
        COMMIT_RE.fullmatch(source.get("commit", "")) is not None,
        "source commit must be a full lowercase Git commit",
    )
    submodules = source.get("submodules")
    _require(isinstance(submodules, list), "source submodules must be a list")
    paths = set()
    for item in submodules:
        _require(isinstance(item, dict), "submodule entries must be objects")
        path = item.get("path")
        _require(isinstance(path, str) and path not in paths,
                 "submodule paths must be unique strings")
        _require(COMMIT_RE.fullmatch(item.get("commit", "")) is not None,
                 f"{path}: submodule commit must be a full lowercase commit")
        _require(item.get("repository", "").startswith("https://github.com/"),
                 f"{path}: submodule repository must use HTTPS GitHub")
        _require(isinstance(item.get("required_for_esp32"), bool),
                 f"{path}: required_for_esp32 must be boolean")
        paths.add(path)
    _require(paths == EXPECTED_SUBMODULES,
             "modern firmware direct submodule set is incomplete")
    transitive = source.get("esp32_transitive_submodules")
    _require(isinstance(transitive, list),
             "ESP32 transitive submodules must be pinned")
    transitive_paths = set()
    for item in transitive:
        _require(isinstance(item, dict)
                 and isinstance(item.get("path"), str)
                 and COMMIT_RE.fullmatch(item.get("commit", "")) is not None,
                 "invalid ESP32 transitive submodule pin")
        _require(item["path"] not in transitive_paths,
                 "ESP32 transitive submodule paths must be unique")
        transitive_paths.add(item["path"])
    _require(transitive_paths == EXPECTED_TRANSITIVE_SUBMODULES,
             "modern firmware transitive submodule set is incomplete")


def _validate_build(lock: dict[str, Any]) -> None:
    target = lock.get("target")
    _require(isinstance(target, dict), "target must be an object")
    for field in (
            "board", "board_variant", "chip", "flash_bus", "psram_bus",
            "display_controller", "touch_controller", "repl"):
        _require(isinstance(target.get(field), str) and target[field],
                 f"target.{field} must be non-empty text")
    for field in (
            "flash_size_bytes", "application_partition_size",
            "display_width", "display_height"):
        _require(isinstance(target.get(field), int) and target[field] > 0,
                 f"target.{field} must be positive")
    _require(target["repl"] in ("USB_SERIAL_JTAG", "UART0"),
             "modern board firmware must declare a supported console")
    uart = target["repl"] == "UART0"
    expected_repl = [
        "--enable-uart-repl=" + ("y" if uart else "n"),
        "--enable-cdc-repl=n",
        "--enable-jtag-repl=" + ("n" if uart else "y"),
    ]

    toolchain = lock.get("toolchain")
    _require(isinstance(toolchain, dict), "toolchain must be an object")
    container = toolchain.get("container")
    _require(isinstance(container, dict), "toolchain.container must be an object")
    _require(container.get("platform") == "linux/amd64",
             "modern board firmware container must use linux/amd64")
    for key in ("index_digest", "manifest_digest"):
        _require(DIGEST_RE.fullmatch(container.get(key, "")) is not None,
                 f"container {key} must be pinned")
    esp_idf = next(
        item for item in lock["source"]["submodules"]
        if item["path"] == "lib/esp-idf")
    _require(toolchain.get("esp_idf_commit") == esp_idf["commit"],
             "toolchain ESP-IDF commit differs from the source pin")

    build = lock.get("build")
    _require(isinstance(build, dict), "build must be an object")
    environment = build.get("environment")
    _require(isinstance(environment, dict)
             and environment.get("LC_ALL") == "C.UTF-8"
             and environment.get("PYTHONHASHSEED") == "0"
             and environment.get("TZ") == "UTC"
             and environment.get("SOURCE_DATE_EPOCH", "").isdigit(),
             "build environment is not deterministic")
    command = build.get("command")
    _require(isinstance(command, list)
             and all(isinstance(item, str) and item for item in command),
             "build command must be a non-empty string array")
    _require(command[:3] == ["python3", "make.py", "esp32"],
             "build must invoke the pinned ESP32 make.py")
    required = {
        f'BOARD={target["board"]}',
        f'BOARD_VARIANT={target["board_variant"]}',
        f'--flash-size={target["flash_size_bytes"] // (1024 * 1024)}',
        f'--partition-size={target["application_partition_size"]}',
        *expected_repl,
        "clean",
    }
    _require(required.issubset(command),
             "build command differs from the declared target")
    repl_arguments = [
        item for item in command
        if item.startswith("--enable-") and "-repl=" in item]
    _require(repl_arguments == expected_repl,
             "build must enable only the declared REPL transport")
    _require("deploy" not in command
             and not any(item.startswith("PORT=") for item in command),
             "board firmware builds must never flash a device")
    display_args = [item for item in command if item.startswith("DISPLAY=")]
    indev_args = [item for item in command if item.startswith("INDEV=")]
    manifest_args = [
        item for item in command if item.startswith("FROZEN_MANIFEST=")]
    _require(len(display_args) == len(indev_args) == len(manifest_args) == 1,
             "build must select one display, input, and extra manifest")

    inputs = build.get("inputs")
    _require(isinstance(inputs, list) and inputs,
             "build inputs must be a non-empty list")
    by_container_path = {}
    for item in inputs:
        _require(isinstance(item, dict), "build input entries must be objects")
        source_path = ROOT / item.get("path", "")
        container_path = item.get("container_path")
        _require(source_path.is_file(), f"local build input missing: {source_path}")
        _require(isinstance(container_path, str)
                 and container_path.startswith("/tartlab/"),
                 "local build input container path must be under /tartlab")
        _require(container_path not in by_container_path,
                 "local build input container paths must be unique")
        _require(item.get("sha256") == sha256_source_file(source_path),
                 f"{item.get('path')}: source hash differs from lock")
        by_container_path[container_path] = item
    selected_paths = {
        display_args[0].split("=", 1)[1],
        indev_args[0].split("=", 1)[1],
        manifest_args[0].split("=", 1)[1],
        build.get("container_wrapper"),
    }
    # Upstream driver names are bound by the source commit. Local overrides
    # still require an explicit content hash; paths cannot bypass that check.
    upstream_drivers = {
        arg.split("=", 1)[1] for arg in display_args + indev_args
        if re.fullmatch(r"[a-z][a-z0-9_]*", arg.split("=", 1)[1])
    }
    _require((selected_paths - upstream_drivers).issubset(by_container_path),
             "selected build modules are not all hash-bound inputs")

    frozen = build.get("frozen_modules")
    _require(isinstance(frozen, dict), "build.frozen_modules must be an object")
    _require(frozen.get("display") == display_args[0].split("=", 1)[1],
             "frozen display module differs from DISPLAY")
    _require(frozen.get("input") == indev_args[0].split("=", 1)[1],
             "frozen input module differs from INDEV")
    additional = frozen.get("additional")
    _require(isinstance(additional, list) and additional,
             "additional frozen modules must be declared")
    _require(len(set(additional)) == len(additional)
             and all(path in by_container_path for path in additional),
             "additional frozen modules must be unique hash-bound inputs")
    manifest_source = (
        ROOT / by_container_path[manifest_args[0].split("=", 1)[1]]["path"]
    ).read_text(encoding="utf-8")
    for path in additional:
        _require(Path(path).name in manifest_source,
                 f"extra manifest does not freeze {Path(path).name}")


def validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    """Reject moving sources, unbound inputs, and unsupported build recipes."""
    _require(lock.get("schema") == 1,
             "unsupported modern board firmware lock schema")
    _require(lock.get("kind") == "tartlab-modern-board-firmware",
             "unexpected modern board firmware lock kind")
    board_id = lock.get("board_id")
    _require(isinstance(board_id, str)
             and BOARD_ID_RE.fullmatch(board_id) is not None,
             "board_id is invalid")
    status = lock.get("status")
    _require(status in ("build-candidate", "reproducible-candidate"),
             "modern board firmware status is invalid")
    _validate_sources(lock)
    _validate_build(lock)

    result = lock.get("result")
    if status == "build-candidate":
        _require(result is None,
                 "a build candidate cannot claim a reproducible result")
        return lock
    _require(isinstance(result, dict),
             "reproducible firmware requires a result")
    _require(result.get("qualification") == "reproducible-candidate",
             "firmware result cannot claim physical qualification")
    _require(result.get("independent_clean_builds") == 2
             and result.get("byte_identical") is True,
             "firmware result requires two byte-identical clean builds")
    artifact = ROOT / result.get("artifact", "")
    _require(artifact.is_file(), f"firmware artifact is missing: {artifact}")
    _require(artifact.stat().st_size == result.get("size"),
             "firmware artifact size differs from lock")
    _require(sha256_file(artifact) == result.get("sha256"),
             "firmware artifact hash differs from lock")
    provenance_path = ROOT / result.get("provenance", "")
    provenance = load_json(provenance_path)
    provenance_artifact = provenance.get("artifact", {})
    evidence = provenance.get("build_evidence", {})
    _require(provenance.get("kind") == "tartlab-modern-board-firmware"
             and provenance.get("board_id") == board_id
             and provenance.get("qualification") == "reproducible-candidate",
             "firmware provenance identity differs from lock")
    _require(provenance_artifact.get("size") == result["size"]
             and provenance_artifact.get("sha256") == result["sha256"]
             and provenance_artifact.get("image_format") ==
             "combined-esp-image"
             and provenance_artifact.get("flash_offset") == "0x0",
             "firmware provenance artifact differs from lock")
    _require(evidence.get("independent_clean_checkouts") == 2
             and evidence.get("byte_identical") is True
             and evidence.get("clean_source_verified_before_each_build") is True,
             "firmware provenance lacks reproducibility evidence")
    return lock


def check_lock(path: Path) -> dict[str, Any]:
    return validate_lock(load_json(path))


def inspect_image(lock: dict[str, Any], path: Path) -> dict[str, Any]:
    """Check an ESP32-S3 combined image against the declared flash budget."""
    from esptool.bin_image import LoadFirmwareImage

    data = path.read_bytes()
    flash_size = lock["target"]["flash_size_bytes"]
    _require(0x10000 < len(data) <= flash_size, "image exceeds flash or is incomplete")
    table = data[0x8000:0x9000]
    partitions = []
    verified_table = False
    for offset in range(0, len(table), 32):
        entry = table[offset:offset + 32]
        magic = struct.unpack_from("<H", entry)[0]
        if magic == 0xEBEB:
            _require(hashlib.md5(table[:offset]).digest() == entry[16:],
                     "partition table checksum differs")
            verified_table = True
            break
        _require(magic == 0x50AA, "invalid partition table entry")
        _, kind, subtype, start, size, label, flags = struct.unpack("<HBBII16sI", entry)
        _require(size > 0 and start >= 0x9000 and start + size <= flash_size,
                 "partition extends beyond physical flash or overlaps boot area")
        _require(not flags, "encrypted partitions are not supported by this inspector")
        partitions.append({"name": label.rstrip(b"\0").decode("ascii"),
                           "type": kind, "subtype": subtype, "offset": start, "size": size})
    _require(verified_table, "partition table lacks a verified checksum")
    ordered = sorted(partitions, key=lambda item: item["offset"])
    for left, right in zip(ordered, ordered[1:]):
        _require(left["offset"] + left["size"] <= right["offset"], "partitions overlap")
    apps = [item for item in partitions if item["type"] == 0]
    _require(len(apps) == 1 and apps[0]["offset"] == 0x10000,
             "expected one application at 0x10000")
    _require(apps[0]["size"] == lock["target"]["application_partition_size"],
             "application partition differs from lock")
    image_sizes = []
    for offset in (0, apps[0]["offset"]):
        image = LoadFirmwareImage("esp32s3", data[offset:])
        _require(image.chip_id == 9, "image is not for ESP32-S3")
        _require(image.checksum == image.calculate_checksum(), "ESP image checksum differs")
        _require(image.append_digest and image.stored_digest == image.calc_digest,
                 "ESP image SHA-256 differs")
        declared_flash = (1 << (image.flash_size_freq >> 4)) * 1024 * 1024
        _require(declared_flash == flash_size, "ESP image flash header differs from lock")
        image_sizes.append(image.data_length + 32)
    _require(image_sizes[0] <= 0x8000, "bootloader overlaps partition table")
    _require(image_sizes[1] <= apps[0]["size"], "application exceeds its partition")
    _require(len(data) <= apps[0]["offset"] + apps[0]["size"],
             "combined firmware unexpectedly contains filesystem data")
    return {
        "board_id": lock["board_id"], "inspection": "passed",
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "flash_size": flash_size, "application_size": image_sizes[1],
        "application_headroom": apps[0]["size"] - image_sizes[1],
        "partitions": partitions,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    check = actions.add_parser("check")
    check.add_argument("--source", type=Path)
    checkout = actions.add_parser("checkout")
    checkout.add_argument("--source", type=Path, required=True)
    command = actions.add_parser("command")
    command.add_argument("--source", type=Path, required=True)
    build = actions.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--copy-to", type=Path)
    inspect = actions.add_parser("inspect", help="validate combined image before flashing")
    inspect.add_argument("--image", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lock = check_lock(args.lock)
    if args.action == "inspect":
        print(json.dumps(inspect_image(lock, args.image), indent=2))
        return 0
    if args.action == "check":
        if args.source is not None:
            verify_source(lock, args.source)
        print(f"Modern board firmware lock is valid: {lock['board_id']}")
        return 0
    if args.action == "checkout":
        checkout_source(lock, args.source)
        print(f"Checked out {lock['source']['commit']} at {args.source}")
        return 0

    command = docker_command(lock, args.source)
    if args.action == "command":
        print(json.dumps(command))
        return 0
    verify_source(lock, args.source)
    subprocess.run(command, check=True)
    artifact = args.source / lock["build"]["artifact"]
    _require(artifact.is_file(), f"expected build artifact missing: {artifact}")
    if args.copy_to is not None:
        args.copy_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact, args.copy_to)
        artifact = args.copy_to
    print(f"Built unqualified board firmware: {artifact}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImportError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
