"""Validate and execute the pinned Phase 5 modern-firmware reference build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence

from release_utils import sha256_source_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "firmware/lvgl-modern/reference.lock.json"
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
EXPECTED_SUBMODULES = {
    "lib/SDL",
    "lib/esp-idf",
    "lib/lvgl",
    "lib/micropython",
    "lib/pycparser",
}
EXPECTED_TRANSITIVE_SUBMODULES = {
    "lib/micropython/lib/berkeley-db-1.xx":
        "0f3bb6947c2f57233916dccd7bb425d7bf86e5a6",
    "lib/micropython/lib/mbedtls":
        "107ea89daaefb9867ea9121002fbbdf926780e98",
    "lib/micropython/lib/micropython-lib":
        "6ae440a8a144233e6e703f6759b7e7a0afaa37a4",
    "lib/micropython/lib/tinyusb":
        "aa0fc2e08f1c2dd6f026a431e8989357fbb4c5bf",
}
REQUIRED_BUILD_ARGUMENTS = {
    "esp32",
    "BOARD=ESP32_GENERIC_S3",
    "BOARD_VARIANT=SPIRAM_OCT",
    "--flash-size=16",
    "--partition-size=4194304",
    "--enable-uart-repl=n",
    "--enable-cdc-repl=n",
    "--enable-jtag-repl=y",
    "DISPLAY=st7796",
    "clean",
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


def load_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    _require(isinstance(value, dict), "modern firmware lock must be an object")
    return value


def validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    """Reject moving refs, incomplete pins, and unsafe reference recipes."""
    _require(lock.get("schema") == 1, "unsupported modern firmware lock schema")
    _require(
        lock.get("profile") == "lvgl-modern-reference",
        "unexpected modern firmware profile",
    )
    _require(
        lock.get("status") ==
        "research-only-reproducible-hardware-qualified",
        "the reference lock must remain reproducible, research-only, and "
        "hardware-qualified",
    )

    source = lock.get("source")
    _require(isinstance(source, dict), "source must be an object")
    repository = source.get("repository")
    _require(
        repository ==
        "https://github.com/lvgl-micropython/lvgl_micropython.git",
        "unexpected modern firmware source repository",
    )
    _require(
        isinstance(source.get("commit"), str)
        and COMMIT_RE.fullmatch(source["commit"]) is not None,
        "source commit must be a full lowercase Git commit",
    )

    submodules = source.get("submodules")
    _require(isinstance(submodules, list), "source submodules must be a list")
    paths: set[str] = set()
    commits: dict[str, str] = {}
    for item in submodules:
        _require(isinstance(item, dict), "submodule entries must be objects")
        path = item.get("path")
        commit = item.get("commit")
        _require(isinstance(path, str) and path.startswith("lib/"),
                 "submodule paths must be under lib/")
        _require(path not in paths, f"duplicate submodule path: {path}")
        _require(
            isinstance(commit, str) and COMMIT_RE.fullmatch(commit) is not None,
            f"{path}: commit must be a full lowercase Git commit",
        )
        _require(
            isinstance(item.get("repository"), str)
            and item["repository"].startswith("https://github.com/"),
            f"{path}: repository must be an HTTPS GitHub URL",
        )
        _require(isinstance(item.get("required_for_esp32"), bool),
                 f"{path}: required_for_esp32 must be boolean")
        paths.add(path)
        commits[path] = commit
    _require(
        paths == EXPECTED_SUBMODULES,
        "direct submodule lock mismatch: "
        f"missing={sorted(EXPECTED_SUBMODULES - paths)}, "
        f"unexpected={sorted(paths - EXPECTED_SUBMODULES)}",
    )
    transitive = source.get("esp32_transitive_submodules")
    _require(isinstance(transitive, list),
             "ESP32 transitive submodules must be a list")
    actual_transitive = {
        item.get("path"): item.get("commit") for item in transitive
        if isinstance(item, dict)
    }
    _require(actual_transitive == EXPECTED_TRANSITIVE_SUBMODULES,
             "ESP32 transitive submodule lock mismatch")

    toolchain = lock.get("toolchain")
    _require(isinstance(toolchain, dict), "toolchain must be an object")
    container = toolchain.get("container")
    _require(isinstance(container, dict), "toolchain container must be an object")
    _require(container.get("platform") == "linux/amd64",
             "reference container platform must be linux/amd64")
    for key in ("index_digest", "manifest_digest"):
        digest = container.get(key)
        _require(
            isinstance(digest, str) and DIGEST_RE.fullmatch(digest) is not None,
            f"container {key} must be a full SHA-256 digest",
        )
    _require(
        toolchain.get("esp_idf_commit") == commits["lib/esp-idf"],
        "container ESP-IDF commit must match the source gitlink",
    )

    target = lock.get("target")
    _require(isinstance(target, dict), "target must be an object")
    _require(target.get("touch_controller") == "CST226",
             "reference target must record the physical CST226 controller")
    _require(target.get("flash_bus") == "quad",
             "T-Display-S3 Pro reference uses quad flash")
    _require(target.get("psram_bus") == "octal",
             "T-Display-S3 Pro reference uses octal PSRAM")
    _require(target.get("repl") == "USB_SERIAL_JTAG",
             "T-Display-S3 Pro reference must expose its native USB REPL")

    build = lock.get("build")
    _require(isinstance(build, dict), "build must be an object")
    command = build.get("command")
    _require(
        isinstance(command, list)
        and all(isinstance(item, str) and item for item in command),
        "build command must be a non-empty string array",
    )
    _require(command[:2] == ["python3", "make.py"],
             "build must invoke the pinned repository's make.py")
    _require(REQUIRED_BUILD_ARGUMENTS.issubset(command),
             "build command is missing a required target argument")
    repl_arguments = [
        item for item in command
        if item.startswith("--enable-") and "-repl=" in item
    ]
    _require(repl_arguments == [
        "--enable-uart-repl=n",
        "--enable-cdc-repl=n",
        "--enable-jtag-repl=y",
    ], "reference build must enable only the native USB Serial/JTAG REPL")
    _require("deploy" not in command, "reference builds must never auto-flash")
    _require(not any(item.startswith("PORT=") for item in command),
             "reference builds must not name a serial port")
    _require(
        "INDEV=/tartlab/firmware/lvgl-modern/drivers/cst226.py" in command,
        "the reference build must freeze the reviewed CST226 driver",
    )
    _require("--octal-flash" not in command,
             "the reference board uses quad flash with octal PSRAM")
    _require(
        build.get("artifact") ==
        "build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin",
        "unexpected reference artifact path",
    )
    environment = build.get("environment")
    _require(environment == {
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": "1782211759",
        "TZ": "UTC",
    }, "reference build environment mismatch")
    inputs = build.get("inputs")
    _require(isinstance(inputs, list) and len(inputs) == 2,
             "reference build must contain two reviewed local inputs")
    inputs_by_path = {item.get("path"): item for item in inputs}
    _require(len(inputs_by_path) == len(inputs),
             "reference build input paths must be unique")
    driver = inputs_by_path.get("firmware/lvgl-modern/drivers/cst226.py")
    _require(isinstance(driver, dict), "CST226 driver input is missing")
    _require(
        driver.get("path") == "firmware/lvgl-modern/drivers/cst226.py"
        and driver.get("container_path") ==
        "/tartlab/firmware/lvgl-modern/drivers/cst226.py",
        "unexpected CST226 driver path",
    )
    wrapper = inputs_by_path.get("firmware/lvgl-modern/container_prepare.py")
    _require(isinstance(wrapper, dict), "container wrapper input is missing")
    _require(
        wrapper.get("container_path") ==
        "/tartlab/firmware/lvgl-modern/container_prepare.py"
        and build.get("container_wrapper") == wrapper["container_path"],
        "unexpected container wrapper path",
    )
    for item in inputs:
        input_path = ROOT / item["path"]
        _require(input_path.is_file(), f"local build input not found: {input_path}")
        actual_hash = sha256_source_file(input_path)
        _require(item.get("sha256") == actual_hash,
                 f"{item['path']}: hash does not match the reference lock")

    gate = lock.get("capability_gate")
    _require(isinstance(gate, dict), "capability_gate must be an object")
    missing = gate.get("required_before_hardware_qualification")
    _require(isinstance(missing, list),
             "required_before_hardware_qualification must be a list")
    present = gate.get("present_in_reference")
    _require(isinstance(present, list) and "cst226-input-driver" in present,
             "the reference must record its reviewed CST226 driver")
    _require("native-usb-repl" in present,
             "the reference must remain provisionable over native USB")
    payload = gate.get("present_in_application_payload")
    _require(isinstance(payload, list)
             and "public-direct-surface-api" in payload
             and "exclusive-ui-game-ownership-transitions" in payload,
             "the application payload must record its Phase 5 item 3 adapters")
    _require("public-direct-surface-api" not in missing
             and "exclusive-ui-game-ownership-transitions" not in missing,
             "implemented item 3 adapters cannot remain missing gates")
    _require(missing == [],
             "the lifecycle and comparative hardware gates must be complete")
    hardware_evidence = gate.get("hardware_evidence")
    _require(isinstance(hardware_evidence, list)
             and [item.get("gate") for item in hardware_evidence
                  if isinstance(item, dict)] ==
             ["lifecycle", "comparative-benchmarks"],
             "hardware evidence must record both reviewed gates")
    for item in hardware_evidence:
        evidence_path = ROOT / item.get("path", "")
        _require(evidence_path.is_file(),
                 f"hardware evidence is missing: {evidence_path}")
        _require(item.get("sha256") == sha256_source_file(evidence_path),
                 f"{item.get('path')}: hardware evidence hash mismatch")
    profile = load_lock(ROOT / "profiles/lvgl-modern.json")
    adapter = profile.get("application_adapter", {})
    adapter_inputs = adapter.get("inputs", [])
    _require(isinstance(adapter_inputs, list) and len(adapter_inputs) == 5,
             "Phase 5 item 3 adapter inputs are not locked")
    for item in adapter_inputs:
        path = ROOT / item.get("path", "")
        _require(path.is_file(), f"application adapter input is missing: {path}")
        _require(item.get("sha256") == sha256_source_file(path),
                 f"{item.get('path')}: application adapter hash mismatch")

    result = lock.get("result")
    _require(isinstance(result, dict), "reproducible build result is missing")
    _require(
        result.get("qualification") == "experimental-hardware-qualified",
        "reference result must remain experimental and hardware-qualified")
    _require(result.get("independent_clean_builds") == 2
             and result.get("byte_identical") is True,
             "reference result must record two byte-identical clean builds")
    artifact_path = ROOT / result.get("artifact", "")
    _require(artifact_path.is_file(), f"reference artifact not found: {artifact_path}")
    _require(artifact_path.stat().st_size == result.get("size"),
             "reference artifact size does not match the lock")
    _require(sha256_file(artifact_path) == result.get("sha256"),
             "reference artifact hash does not match the lock")

    provenance_path = ROOT / result.get("provenance", "")
    provenance = load_lock(provenance_path)
    provenance_artifact = provenance.get("artifact", {})
    evidence = provenance.get("build_evidence", {})
    _require(
        provenance.get("qualification") ==
        "experimental-hardware-qualified",
        "reference provenance must remain experimental and hardware-qualified")
    _require(provenance_artifact.get("size") == result["size"]
             and provenance_artifact.get("sha256") == result["sha256"],
             "reference provenance artifact identity mismatch")
    _require(evidence.get("independent_clean_checkouts") == 2
             and evidence.get("byte_identical") is True,
             "reference provenance lacks repeatability evidence")
    durations = evidence.get("successful_build_durations_seconds")
    _require(isinstance(durations, list) and len(durations) == 2
             and all(isinstance(item, (int, float)) and item > 0
                     for item in durations),
             "reference provenance must time both successful clean builds")
    _require(provenance.get("hardware_evidence") == hardware_evidence,
             "reference provenance hardware evidence must match the lock")
    _require(provenance.get("remaining_gates") == [],
             "reference hardware gates must be complete")
    selection = provenance.get("production_selection", {})
    _require(selection.get("status") == "not-selected"
             and "alternative-modern-stack-comparison" in
             selection.get("remaining", []),
             "hardware qualification must not select production firmware")

    profile = load_lock(ROOT / "profiles/lvgl-modern.json")
    candidate = profile.get("reference_candidate", {})
    _require(
        candidate.get("status") == lock["status"]
        and candidate.get("artifact") == result["artifact"]
        and candidate.get("sha256") == result["sha256"]
        and candidate.get("lock") ==
        "firmware/lvgl-modern/reference.lock.json"
        and candidate.get("provenance") == result["provenance"],
        "modern profile reference candidate does not match the lock",
    )
    return lock


def check_lock(path: Path = DEFAULT_LOCK) -> dict[str, Any]:
    return validate_lock(load_lock(path))


def _git(source: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.strip()


def verify_source(lock: dict[str, Any], source: Path) -> None:
    """Verify an already checked-out source tree before the build mutates it."""
    _require(source.is_dir(), f"source directory not found: {source}")
    actual_commit = _git(source, "rev-parse", "HEAD")
    expected_commit = lock["source"]["commit"]
    _require(actual_commit == expected_commit,
             f"source commit is {actual_commit}, expected {expected_commit}")
    status = _git(source, "status", "--porcelain", "--untracked-files=all")
    _require(not status, "source tree must be clean before the reference build")

    tree = _git(source, "ls-tree", "HEAD:lib")
    actual_gitlinks = {}
    for line in tree.splitlines():
        metadata, name = line.split("\t", 1)
        mode, kind, commit = metadata.split()
        if mode == "160000" and kind == "commit":
            actual_gitlinks[f"lib/{name}"] = commit
    expected_gitlinks = {
        item["path"]: item["commit"]
        for item in lock["source"]["submodules"]
    }
    _require(actual_gitlinks == expected_gitlinks,
             "checked-out source gitlinks do not match the reference lock")


def image_reference(lock: dict[str, Any]) -> str:
    container = lock["toolchain"]["container"]
    return f'{container["repository"]}@{container["manifest_digest"]}'


def docker_command(lock: dict[str, Any], source: Path) -> list[str]:
    source = source.resolve()
    command = [
        "docker", "run", "--rm",
        "--platform", lock["toolchain"]["container"]["platform"],
        "--env", "IDF_GIT_SAFE_DIR=/project",
        "--volume", f"{source}:/project",
        "--volume", f"{ROOT.resolve()}:/tartlab:ro",
        "--workdir", "/project",
    ]
    for name, value in lock["build"]["environment"].items():
        command.extend(["--env", f"{name}={value}"])
    command.extend([
        image_reference(lock),
        "python3", lock["build"]["container_wrapper"],
        "--python-env", "/opt/esp/python_env", "--",
        *lock["build"]["command"],
    ])
    return command


def checkout_source(lock: dict[str, Any], destination: Path) -> None:
    _require(not destination.exists(),
             f"checkout destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--no-checkout", lock["source"]["repository"],
         str(destination)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach",
         lock["source"]["commit"]],
        check=True,
    )
    verify_source(lock, destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    subparsers = parser.add_subparsers(dest="action", required=True)

    check = subparsers.add_parser("check", help="validate the reference lock")
    check.add_argument("--source", type=Path)

    checkout = subparsers.add_parser(
        "checkout", help="create an exact detached source checkout")
    checkout.add_argument("--source", type=Path, required=True)

    command = subparsers.add_parser(
        "command", help="print the digest-pinned Docker build command")
    command.add_argument("--source", type=Path, required=True)

    build = subparsers.add_parser(
        "build", help="run the digest-pinned Docker reference build")
    build.add_argument("--source", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    lock = check_lock(args.lock)
    if args.action == "check":
        if args.source is not None:
            verify_source(lock, args.source)
        print("Modern firmware reference lock is valid")
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
    _require(artifact.is_file(), f"expected build artifact not found: {artifact}")
    print(f"Built unqualified reference artifact: {artifact}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
