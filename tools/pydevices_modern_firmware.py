"""Validate and build the pinned Phase 5 PyDevices modern comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "firmware/lvgl-modern/pydevices.lock.json"
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXPECTED_LAYOUT = {
    "cmods",
    "displayif",
    "lvgl-micropython",
    "lvgl-bindings",
    "micropython",
    "pydevices",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_source_file(path: Path) -> str:
    """Hash reviewed text inputs independently of checkout line endings."""
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    _require(isinstance(value, dict), "PyDevices lock must be an object")
    return value


def validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    _require(lock.get("schema") == 1,
             "unsupported PyDevices modern lock schema")
    _require(lock.get("profile") == "pydevices-modern-comparison",
             "unexpected PyDevices modern profile")
    _require(lock.get("status") in {
        "research-only-build-candidate",
        "research-only-reproducible-candidate",
        "research-only-hardware-qualified",
    }, "PyDevices modern status must remain research-only")

    sources = lock.get("sources")
    _require(isinstance(sources, list), "sources must be a list")
    layouts = set()
    for source in sources:
        _require(isinstance(source, dict), "source entries must be objects")
        layout = source.get("layout")
        _require(isinstance(layout, str) and layout not in layouts,
                 "source layouts must be unique strings")
        layouts.add(layout)
        _require(source.get("repository", "").startswith("https://github.com/"),
                 f"{layout}: source must use an HTTPS GitHub URL")
        _require(COMMIT_RE.fullmatch(source.get("commit", "")) is not None,
                 f"{layout}: source commit must be a full lowercase Git commit")
        _require(source.get("license") == "MIT",
                 f"{layout}: reviewed license must be MIT")
    _require(layouts == EXPECTED_LAYOUT,
             "PyDevices source layout is incomplete or unexpected")

    by_layout = {item["layout"]: item for item in sources}
    bindings_submodules = by_layout["lvgl-bindings"].get("submodules")
    _require(isinstance(bindings_submodules, list)
             and len(bindings_submodules) == 1,
             "lvgl-bindings must pin its LVGL submodule")
    lvgl = bindings_submodules[0]
    _require(lvgl.get("path") == "lvgl"
             and COMMIT_RE.fullmatch(lvgl.get("commit", "")) is not None
             and lvgl.get("version") == "9.5.0",
             "unexpected pinned LVGL identity")
    mp_submodules = by_layout["micropython"].get("required_submodules")
    expected_mp = {
        "lib/berkeley-db-1.xx":
            "0f3bb6947c2f57233916dccd7bb425d7bf86e5a6",
        "lib/mbedtls":
            "107ea89daaefb9867ea9121002fbbdf926780e98",
        "lib/micropython-lib":
            "6ae440a8a144233e6e703f6759b7e7a0afaa37a4",
        "lib/tinyusb":
            "aa0fc2e08f1c2dd6f026a431e8989357fbb4c5bf",
    }
    _require(
        {item.get("path"): item.get("commit") for item in mp_submodules
         if isinstance(item, dict)} == expected_mp,
        "MicroPython transitive submodule lock mismatch",
    )

    container = lock.get("toolchain", {}).get("container", {})
    _require(container.get("platform") == "linux/amd64",
             "container platform must be linux/amd64")
    _require(DIGEST_RE.fullmatch(container.get("manifest_digest", ""))
             is not None, "container manifest digest must be pinned")

    target = lock.get("target", {})
    _require(target.get("board") == "TARTLAB_T_DISPLAY_S3_PRO",
             "unexpected comparison board")
    _require(target.get("repl") == "USB_SERIAL_JTAG",
             "comparison firmware must use native USB Serial/JTAG")
    _require(target.get("application_partition_size") == 4_194_304,
             "comparison app partition must remain 4 MiB")
    _require(target.get("cpu_hz") == 240_000_000
             and target.get("display_spi_hz") == 60_000_000,
             "comparison clocks must match the reference matrix")

    build = lock.get("build", {})
    _require(build.get("command") == [
        "python3",
        "/tartlab/firmware/lvgl-modern/pydevices/container_build.py",
    ], "unexpected container build command")
    command_text = " ".join(build["command"]).lower()
    _require("deploy" not in command_text and "flash" not in command_text
             and "com" not in command_text,
             "comparison build command must never flash a device")
    _require(build.get("environment") == {
        "LC_ALL": "C.UTF-8",
        "MP_AUTOSIZE": "0",
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": "1787647762",
        "TZ": "UTC",
    }, "comparison build environment mismatch")
    _require(build.get("whole_pydevices_repository_frozen") is False,
             "the complete PyDevices repository must not be frozen")
    expected_runtime = {
        "appdev", "displaydev", "multimer", "events.py", "keys.py",
        "st7796.py", "cst226.py", "display_driver.py", "fs_driver.py",
    }
    _require(set(build.get("frozen_runtime", [])) == expected_runtime,
             "minimal frozen runtime inventory mismatch")
    for item in build.get("local_inputs", []):
        path = ROOT / item.get("path", "")
        _require(path.is_file(), f"local build input is missing: {path}")
        _require(item.get("sha256") == sha256_source_file(path),
                 f"{item.get('path')}: local build input hash mismatch")

    transport = lock.get("transport", {})
    _require(transport.get("provider") == "displayif"
             and transport.get("module") == "spibus"
             and transport.get("blocking") is True
             and transport.get("dma_completion_callback") is False,
             "displayif transport capabilities are misstated")
    adapter = lock.get("application_adapter", {})
    _require(adapter.get("uses_upstream_private_display_fields") is False,
             "the public adapter cannot depend on private display fields")
    for item in adapter.get("inputs", []):
        path = ROOT / item.get("path", "")
        _require(path.is_file(), f"adapter input is missing: {path}")
        _require(item.get("sha256") == sha256_source_file(path),
                 f"{item.get('path')}: adapter input hash mismatch")

    gate = lock.get("capability_gate", {})
    _require("asynchronous-display-transfer" in gate.get("known_absent", []),
             "known synchronous transport limitation must remain explicit")
    selection = lock.get("production_selection", {})
    _require(selection.get("status") == "not-selected"
             and selection.get("legacy_release_channel") == "unchanged",
             "the comparison cannot select production or alter legacy")

    result = lock.get("result")
    if result is not None:
        _require(isinstance(result, dict), "result must be an object")
        _require(
            result.get("qualification") ==
            "research-only-reproducible-candidate",
            "comparison result cannot claim hardware qualification",
        )
        artifact = ROOT / result.get("artifact", "")
        _require(artifact.is_file(), f"comparison artifact missing: {artifact}")
        _require(artifact.stat().st_size == result.get("size"),
                 "comparison artifact size mismatch")
        _require(sha256_file(artifact) == result.get("sha256"),
                 "comparison artifact hash mismatch")
        _require(result.get("independent_clean_builds") == 2
                 and result.get("byte_identical") is True,
                 "comparison result requires two byte-identical clean builds")
        provenance_path = ROOT / result.get("provenance", "")
        _require(provenance_path.is_file(),
                 f"comparison provenance missing: {provenance_path}")
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{provenance_path}: {exc}") from exc
        _require(
            provenance.get("profile") == lock["profile"]
            and provenance.get("qualification") == result["qualification"],
            "comparison provenance identity mismatch",
        )
        provenance_artifact = provenance.get("artifact", {})
        _require(
            provenance_artifact.get("file") == artifact.name
            and provenance_artifact.get("size") == result["size"]
            and provenance_artifact.get("sha256") == result["sha256"],
            "comparison provenance artifact identity mismatch",
        )
        evidence = provenance.get("build_evidence", {})
        _require(
            evidence.get("independent_clean_checkouts") == 2
            and evidence.get("byte_identical") is True
            and evidence.get("clean_source_verified_before_each_build") is True
            and evidence.get("clean_source_verified_after_each_build") is True,
            "comparison provenance lacks clean repeatability evidence",
        )
        _require(
            provenance.get("remaining_gates") ==
            gate.get("required_before_selection"),
            "comparison provenance remaining gates mismatch",
        )
        evidence_identity = result.get("hardware_benchmark_evidence", {})
        evidence_path = ROOT / evidence_identity.get("path", "")
        _require(evidence_path.is_file(),
                 f"comparison evidence missing: {evidence_path}")
        _require(
            sha256_source_file(evidence_path) == evidence_identity.get("sha256"),
                 "comparison evidence hash mismatch")
        _require(
            provenance.get("benchmark_evidence", {}).get(
                "evidence_document") == evidence_identity,
            "comparison provenance evidence identity mismatch",
        )
        _require(
            provenance.get("benchmark_evidence", {}).get(
                "matrix_validated") is True
            and provenance.get("benchmark_evidence", {}).get(
                "candidate_slower_in_every_measured_median") is True,
            "comparison provenance lacks benchmark outcome",
        )
    return lock


def check_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    return validate_lock(load_lock(path))


def _git(source: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def verify_sources(lock: dict[str, Any], source_root: Path) -> None:
    for source in lock["sources"]:
        path = source_root / source["layout"]
        _require(path.is_dir(), f"source directory not found: {path}")
        actual = _git(path, "rev-parse", "HEAD")
        _require(actual == source["commit"],
                 f"{source['layout']}: {actual}, expected {source['commit']}")
        status = _git(path, "status", "--porcelain", "--untracked-files=all")
        _require(not status, f"source tree must be clean: {path}")
        for submodule in source.get("submodules", []):
            subpath = path / submodule["path"]
            _require(_git(subpath, "rev-parse", "HEAD") == submodule["commit"],
                     f"{source['layout']}/{submodule['path']}: wrong commit")
        for submodule in source.get("required_submodules", []):
            subpath = path / submodule["path"]
            _require(_git(subpath, "rev-parse", "HEAD") == submodule["commit"],
                     f"{source['layout']}/{submodule['path']}: wrong commit")


def image_reference(lock: dict[str, Any]) -> str:
    container = lock["toolchain"]["container"]
    return f'{container["repository"]}@{container["manifest_digest"]}'


def docker_command(lock: dict[str, Any], source_root: Path) -> list[str]:
    source_root = source_root.resolve()
    mounts = [
        (source_root / "cmods", "/workspace", False),
        (source_root / "micropython", "/workspace/micropython", False),
        # The wrapper applies and reverses the hash-bound compatibility patch.
        (source_root / "displayif", "/workspace/displayif", False),
        (source_root / "lvgl-micropython", "/workspace/lvgl-micropython", True),
        (source_root / "lvgl-bindings", "/workspace/lvgl-bindings", True),
        (source_root / "pydevices", "/sources/pydevices", True),
        (ROOT.resolve(), "/tartlab", True),
    ]
    command = [
        "docker", "run", "--rm", "--platform",
        lock["toolchain"]["container"]["platform"],
        "--workdir", "/workspace",
        "--env", "IDF_DIR=/opt/esp/idf",
    ]
    for host, container, read_only in mounts:
        suffix = ":ro" if read_only else ""
        command.extend(["--volume", f"{host}:{container}{suffix}"])
    for name, value in lock["build"]["environment"].items():
        command.extend(["--env", f"{name}={value}"])
    command.extend([image_reference(lock), *lock["build"]["command"]])
    return command


def checkout_sources(lock: dict[str, Any], destination: Path) -> None:
    _require(not destination.exists(),
             f"checkout destination already exists: {destination}")
    destination.mkdir(parents=True)
    for source in lock["sources"]:
        path = destination / source["layout"]
        subprocess.run([
            "git", "clone", "--no-checkout", source["repository"], str(path)
        ], check=True)
        subprocess.run([
            "git", "-C", str(path), "checkout", "--detach", source["commit"]
        ], check=True)
        submodule_paths = [
            item["path"] for item in
            source.get("submodules", []) + source.get("required_submodules", [])
        ]
        if submodule_paths:
            subprocess.run([
                "git", "-C", str(path), "submodule", "update", "--init",
                "--depth", "1", *submodule_paths,
            ], check=True)
    verify_sources(lock, destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    commands = parser.add_subparsers(dest="action", required=True)
    check = commands.add_parser("check")
    check.add_argument("--source-root", type=Path)
    checkout = commands.add_parser("checkout")
    checkout.add_argument("--source-root", type=Path, required=True)
    command = commands.add_parser("command")
    command.add_argument("--source-root", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("--source-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lock = check_lock(args.lock)
    if args.action == "check":
        if args.source_root is not None:
            verify_sources(lock, args.source_root)
        print("PyDevices modern comparison lock is valid")
        return 0
    if args.action == "checkout":
        checkout_sources(lock, args.source_root)
        print(f"Checked out comparison sources at {args.source_root}")
        return 0
    command = docker_command(lock, args.source_root)
    if args.action == "command":
        print(json.dumps(command))
        return 0
    verify_sources(lock, args.source_root)
    subprocess.run(command, check=True)
    artifact = args.source_root / lock["build"]["artifact"]
    _require(artifact.is_file(), f"expected build artifact not found: {artifact}")
    print(f"Built unqualified PyDevices comparison artifact: {artifact}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
