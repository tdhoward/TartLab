"""USB-only physical qualification for modern OTA containment.

This helper is deliberately separate from the production updater. It verifies
the signed candidate on the host, stages only authenticated update assets in a
device temporary directory, and runs one named fault case. Real interruption
cases wait for a white display and a serial signal before the operator removes
USB power. No host Wi-Fi connection or local HTTP server is used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Sequence

import serial
from serial.tools import list_ports

from phase1_device import RawRepl
from provision_modern import (
    ROOT, _release_identity, _verify_attestations,
)
from release_utils import sha256_file


STAGE_ROOT = "/qualification/modern-update"
INTERRUPT_PACKAGE = "pydevices.tar"
CASES = ("corrupt-download", "interrupt-download", "interrupt-recovery")
ATTESTATION_RECEIPT = "modern-containment-attestation.json"


def _workspace(path: Path) -> Path:
    path = path.resolve()
    if path == ROOT or ROOT in path.parents or path == Path(path.anchor):
        raise ValueError("qualification workspace must be outside the repository")
    path.mkdir(parents=True, exist_ok=True)
    return path


def release_plan(release: Path) -> tuple[dict[str, Any], list[Path]]:
    """Validate the modern release and return its staged update assets."""

    release = release.resolve()
    manifest, checksums_sha256 = _release_identity(release)
    files = [release / "modern-manifest.json"]
    files.extend(release / item["file_name"] for item in manifest["packages"])
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)
    return {
        "schema": 1,
        "version": manifest["version"],
        "source_ref": "refs/tags/" + manifest["version"],
        "checksums_sha256": checksums_sha256,
        "bundle_sha256": sha256_file(
            release / "qualification-attestation.sigstore.json"),
        "assets": [{
            "name": path.name,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        } for path in files],
    }, files


def verify_cached_plan(workspace: Path, plan: dict[str, Any]) -> None:
    path = workspace / ATTESTATION_RECEIPT
    if not path.is_file():
        raise ValueError("no cached modern containment attestation exists")
    cached = json.loads(path.read_text(encoding="utf-8"))
    if cached != plan:
        raise ValueError("cached modern containment attestation changed")


def _remove_and_create_stage(repl: RawRepl) -> bytes:
    code = r'''
import os
ROOT = %r
def kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0
def remove(path):
    if kind(path) == 2:
        for name in os.listdir(path):
            remove(path.rstrip('/') + '/' + name)
        os.rmdir(path)
    elif kind(path) == 1:
        os.remove(path)
if kind('/qualification') == 0:
    os.mkdir('/qualification')
remove(ROOT)
os.mkdir(ROOT)
print('CONTAIN_STAGE_READY=True')
''' % STAGE_ROOT
    return repl.exec(code, 30)


def _connect_repl(port: str, timeout: int) -> RawRepl:
    """Wait for the native USB endpoint to become writable."""

    deadline = time.monotonic() + 12
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        repl = None
        try:
            repl = RawRepl(port, timeout=timeout)
            repl.enter()
            return repl
        except (OSError, serial.SerialException) as error:
            last_error = error
            if repl is not None:
                repl.close()
            time.sleep(0.5)
    if last_error is not None:
        raise last_error
    raise TimeoutError("native USB endpoint did not become writable")


def stage_release(port: str, files: Sequence[Path], timeout: int) -> None:
    repl = _connect_repl(port, timeout)
    try:
        print(_remove_and_create_stage(repl).decode("utf-8", "replace"), end="")
        for index, path in enumerate(files, 1):
            content = path.read_bytes()
            expected = sha256_file(path)
            print("Staging %d/%d %s (%d bytes)" % (
                index, len(files), path.name, len(content)), flush=True)
            output = repl.stream_file(
                STAGE_ROOT + "/" + path.name, content, expected,
                max(timeout, 300))
            print(output.decode("utf-8", "replace"), end="")
        repl.serial.write(b"import machine\nmachine.reset()\n\x04")
        time.sleep(0.5)
    finally:
        repl.close()
    time.sleep(3)


def _asset_records(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "name": item["name"],
        "size": item["size"],
        "browser_download_url": "serial://" + item["name"],
    } for item in plan["assets"]]


def corrupt_download_code(plan: dict[str, Any], package: str) -> str:
    return r'''
import os, uasyncio as asyncio, ujson
from tartlabutils import updater
ROOT = %r
ASSETS = %r
VERSION = %r
CORRUPT = %r

async def local_release(unused_repo):
    return ASSETS, VERSION

async def local_download(url, target):
    name = url.rsplit('/', 1)[-1]
    source = ROOT + '/' + name
    first = True
    with open(source, 'rb') as incoming, open(target, 'wb') as outgoing:
        while True:
            chunk = incoming.read(1024)
            if not chunk:
                break
            if name == CORRUPT and first:
                chunk = bytes([chunk[0] ^ 1]) + chunk[1:]
                first = False
            outgoing.write(chunk)
    return True

original_release = updater.check_for_update
original_download = updater.download_asset
updater.check_for_update = local_release
updater.download_asset = local_download
with open(updater.REPOS_FILE, 'r') as stream:
    repos = ujson.load(stream)
target = next(item for item in repos['list'] if item.get('name') == 'TartLab')
before = target.get('installed_version')
try:
    result = asyncio.run(updater.update_packages(
        target, lambda message, step, total: None))
finally:
    updater.check_for_update = original_release
    updater.download_asset = original_download
try:
    marker = ujson.load(open('/state/update.json'))
except Exception:
    marker = None
print('CONTAIN_RESULT=' + str(result))
print('CONTAIN_FAILED=' + str(result == updater.UPDATE_FAILED))
print('CONTAIN_VERSION_BEFORE=' + str(before))
print('CONTAIN_VERSION_AFTER=' + str(target.get('installed_version')))
print('CONTAIN_MARKER=' + str(marker.get('status') if marker else 'none'))
''' % (STAGE_ROOT, _asset_records(plan), plan["version"], package)


def interrupt_download_code(plan: dict[str, Any], package: str) -> str:
    return r'''
import uasyncio as asyncio, ujson, utime
from tartlabutils import updater
ROOT = %r
ASSETS = %r
VERSION = %r
INTERRUPT = %r

async def local_release(unused_repo):
    return ASSETS, VERSION

async def local_download(url, target):
    name = url.rsplit('/', 1)[-1]
    with open(ROOT + '/' + name, 'rb') as incoming, open(target, 'wb') as outgoing:
        signaled = False
        while True:
            chunk = incoming.read(1024)
            if not chunk:
                break
            outgoing.write(chunk)
            if name == INTERRUPT and not signaled:
                from tartlabutils.platform import get_platform
                platform = get_platform()
                surface = platform.enter_game_mode()
                stripe_height = 24
                for y in range(0, surface.height, stripe_height):
                    height = min(stripe_height, surface.height - y)
                    buffer = surface.allocate_buffer(surface.width, height)
                    for offset in range(0, len(buffer), 2):
                        buffer[offset] = 0xff
                        buffer[offset + 1] = 0xff
                    surface.write(buffer, 0, y, surface.width, height)
                    surface.free_buffer(buffer)
                print('CONTAIN_POWER_SIGNAL=interrupt-download')
                signaled = True
            if name == INTERRUPT:
                utime.sleep_ms(25)
    return True

updater.check_for_update = local_release
updater.download_asset = local_download
with open(updater.REPOS_FILE, 'r') as stream:
    repos = ujson.load(stream)
target = next(item for item in repos['list'] if item.get('name') == 'TartLab')
asyncio.run(updater.update_packages(target, lambda message, step, total: None))
''' % (STAGE_ROOT, _asset_records(plan), plan["version"], package)


def interrupt_recovery_code(plan: dict[str, Any], package: str) -> str:
    return r'''
import os, sys, ujson
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery_update
ROOT = %r
VERSION = %r
INTERRUPT = %r
ASSET_NAMES = %r
TEMP = recovery_update.TEMP_DIR
if recovery_update._kind(TEMP) != 0:
    recovery_update._remove_tree(TEMP)
recovery_update._mkdirs(TEMP)
for name in ASSET_NAMES:
    with open(ROOT + '/' + name, 'rb') as incoming, open(TEMP + '/' + name, 'wb') as outgoing:
        while True:
            chunk = incoming.read(4096)
            if not chunk:
                break
            outgoing.write(chunk)
document = recovery_update._read_json(TEMP + '/modern-manifest.json', None)
repos = recovery_update._read_json(recovery_update.STATE_REPOS, {})
tartlab = recovery_update._tartlab_repo(repos)
manifest = recovery_update._manifest_packages(document, tartlab, VERSION)
for item in manifest:
    path = TEMP + '/' + item['file_name']
    if recovery_update._sha256(path) != item['sha256']:
        raise ValueError('Staged package hash mismatch: ' + item['file_name'])
    recovery_update._tar_members(path, item['target'], False)
original_members = recovery_update._tar_members
def signaled_members(path, target, extract):
    if extract and path.endswith('/' + INTERRUPT):
        from tartlabutils.platform import get_platform
        platform = get_platform()
        surface = platform.enter_game_mode()
        stripe_height = 24
        for y in range(0, surface.height, stripe_height):
            height = min(stripe_height, surface.height - y)
            buffer = surface.allocate_buffer(surface.width, height)
            for offset in range(0, len(buffer), 2):
                buffer[offset] = 0xff
                buffer[offset + 1] = 0xff
            surface.write(buffer, 0, y, surface.width, height)
            surface.free_buffer(buffer)
        print('CONTAIN_POWER_SIGNAL=interrupt-recovery')
    return original_members(path, target, extract)
recovery_update._tar_members = signaled_members
recovery_update._install_verified_packages(
    tartlab, VERSION, manifest, lambda message: print('CONTAIN_RECOVERY=' + message))
''' % (
        STAGE_ROOT, plan["version"], package,
        [item["name"] for item in plan["assets"]])


def _run_code(port: str, code: str, timeout: int) -> str:
    repl = _connect_repl(port, timeout)
    try:
        return repl.exec(code, timeout).decode("utf-8", "replace")
    finally:
        repl.close()


def _run_until_power_loss(port: str, code: str, signal: bytes,
                          timeout: int) -> str:
    repl = _connect_repl(port, timeout)
    captured = b""
    try:
        payload = code.encode("utf-8")
        for offset in range(0, len(payload), 128):
            repl.serial.write(payload[offset:offset + 128])
            time.sleep(0.01)
        repl.serial.write(b"\x04")
        captured = repl._read_until(signal, timeout)
        print(captured.decode("utf-8", "replace"), end="", flush=True)
        print("Remove USB power now; keep it disconnected for five seconds.",
              flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            available = {item.device for item in list_ports.comports()}
            if port not in available:
                return captured.decode("utf-8", "replace")
            try:
                repl.serial.read(repl.serial.in_waiting or 1)
            except (OSError, serial.SerialException):
                return captured.decode("utf-8", "replace")
            time.sleep(0.1)
    finally:
        repl.close()
    raise TimeoutError("USB power was not removed after the device signal")


def _receipt_path(workspace: Path, case: str) -> Path:
    first = workspace / ("modern-containment-" + case + ".json")
    if not first.exists():
        return first
    index = 2
    while True:
        candidate = workspace / (
            "modern-containment-%s-%03d.json" % (case, index))
        if not candidate.exists():
            return candidate
        index += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--case", choices=("stage", *CASES), required=True)
    parser.add_argument("--package", default=INTERRUPT_PACKAGE)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--reuse-stage", action="store_true")
    parser.add_argument("--reuse-attestation", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-fault", action="store_true")
    args = parser.parse_args()

    if not args.execute or not args.confirm_fault:
        raise ValueError("qualification requires --execute and --confirm-fault")
    workspace = _workspace(args.workspace)
    plan, files = release_plan(args.release)
    if args.source_ref != plan["source_ref"]:
        raise ValueError("source ref must be " + plan["source_ref"])
    if args.reuse_attestation:
        verify_cached_plan(workspace, plan)
    else:
        _verify_attestations(args.release.resolve(), args.source_ref)
        (workspace / ATTESTATION_RECEIPT).write_text(
            json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    package_names = {item["name"] for item in plan["assets"]}
    if args.package not in package_names or not args.package.endswith(".tar"):
        raise ValueError("fault package is not in the authenticated manifest")

    if not args.reuse_stage:
        stage_release(args.port, files, args.timeout)
    result = "staged"
    if args.case == "corrupt-download":
        output = _run_code(
            args.port, corrupt_download_code(plan, args.package),
            max(args.timeout, 300))
        print(output, end="")
        if "CONTAIN_FAILED=True" not in output or \
                "CONTAIN_MARKER=none" not in output:
            raise RuntimeError("corrupt download did not fail closed")
        result = "failed-closed"
    elif args.case == "interrupt-download":
        _run_until_power_loss(
            args.port, interrupt_download_code(plan, args.package),
            b"CONTAIN_POWER_SIGNAL=interrupt-download", args.timeout)
        result = "power-removed"
    elif args.case == "interrupt-recovery":
        _run_until_power_loss(
            args.port, interrupt_recovery_code(plan, args.package),
            b"CONTAIN_POWER_SIGNAL=interrupt-recovery", args.timeout)
        result = "power-removed"

    receipt = {
        **plan,
        "case": args.case,
        "package": args.package,
        "result": result,
    }
    path = _receipt_path(workspace, args.case)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(path), "result": result}, indent=2))


if __name__ == "__main__":
    main()
