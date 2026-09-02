"""Stage and restore the Phase 5 PyDevices comparison filesystem overlay."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
from typing import Sequence

try:
    from phase1_device import RawRepl
except ImportError:  # Allow import as ``tools.phase5_pydevices_device``.
    from tools.phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
MARKER_PATH = "/state/phase5_pydevices_comparison.json"
SELECTOR = b"from t_display_s3_pro_pydevices_modern import *\n"
SELECTOR_PATHS = ("/device/hdwconfig.py", "/hdwconfig.py")
STAGED_FILES = {
    "/lib/pydevices_modern.py":
        ROOT / "firmware/lvgl-modern/pydevices/runtime/pydevices_modern.py",
    "/lib/lilygo_t_display_s3_pro_pydevices.py":
        ROOT / "firmware/lvgl-modern/pydevices/runtime/lilygo_t_display_s3_pro_pydevices.py",
    "/configs/t_display_s3_pro_pydevices_modern.py":
        ROOT / "firmware/lvgl-modern/pydevices/runtime/t_display_s3_pro_pydevices_modern.py",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _extract(output: bytes, marker: str) -> dict:
    prefix = marker + "="
    for line in output.decode("utf-8", "replace").splitlines():
        if line.startswith(prefix):
            result = json.loads(line[len(prefix):])
            if not isinstance(result, dict):
                raise ValueError(f"{marker} payload is not an object")
            return result
    raise ValueError(f"device output did not contain {marker}")


def _connect(args: argparse.Namespace) -> RawRepl:
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
    except Exception:
        repl.close()
        raise
    return repl


def stage(args: argparse.Namespace) -> None:
    repl = _connect(args)
    try:
        preflight = r'''
import os, ubinascii, uhashlib, ujson

def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

if exists(%r):
    raise ValueError("comparison marker already exists; clean up or inspect it")
collisions = [path for path in %r if exists(path)]
if collisions:
    raise ValueError("comparison overlay path already exists: " + repr(collisions))
originals = {}
for path in %r:
    with open(path, "rb") as stream:
        original = stream.read()
    digest = uhashlib.sha256(original).digest()
    originals[path] = {
        "b64": ubinascii.b2a_base64(original).decode().strip(),
        "sha256": "".join("%%02x" %% byte for byte in digest),
    }
print("PHASE5_PYDEVICES_PREFLIGHT=" + ujson.dumps({
    "originals": originals,
}))
''' % (MARKER_PATH, tuple(STAGED_FILES), SELECTOR_PATHS)
        original = _extract(
            repl.exec(preflight, max(args.timeout, 45)),
            "PHASE5_PYDEVICES_PREFLIGHT",
        )
        originals = original.get("originals", {})
        if set(originals) != set(SELECTOR_PATHS):
            raise ValueError("device selector preflight paths mismatch")
        for path, identity in originals.items():
            original_content = base64.b64decode(identity["b64"])
            if _sha256(original_content) != identity["sha256"]:
                raise ValueError(f"device selector preflight hash mismatch: {path}")

        staged = {
            remote: _sha256(local.read_bytes())
            for remote, local in STAGED_FILES.items()
        }
        for path in SELECTOR_PATHS:
            staged[path] = _sha256(SELECTOR)
        marker = {
            "schema": 1,
            "profile": "pydevices-modern-comparison",
            "original_selectors": originals,
            "staged_sha256": staged,
        }
        marker_content = (json.dumps(marker, separators=(",", ":")) + "\n").encode()
        repl.stream_file(
            MARKER_PATH, marker_content, _sha256(marker_content),
            max(args.timeout, 90),
        )
        for remote, local in STAGED_FILES.items():
            content = local.read_bytes()
            repl.stream_file(
                remote, content, staged[remote], max(args.timeout, 120))
        for path in SELECTOR_PATHS:
            repl.stream_file(
                path, SELECTOR, staged[path], max(args.timeout, 90))
        verify = r'''
import uhashlib, ujson
expected = %r
actual = {}
for path in expected:
    value = uhashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break
            value.update(chunk)
    actual[path] = "".join("%%02x" %% byte for byte in value.digest())
if actual != expected:
    raise ValueError("staged comparison file hash mismatch")
print("PHASE5_PYDEVICES_STAGED=" + ujson.dumps(actual))
''' % staged
        result = _extract(
            repl.exec(verify, max(args.timeout, 60)),
            "PHASE5_PYDEVICES_STAGED",
        )
    finally:
        repl.close()
    print(json.dumps(result, indent=2, sort_keys=True))


def cleanup(args: argparse.Namespace) -> None:
    repl = _connect(args)
    try:
        output = repl.exec(
            "import ujson\n"
            f"print('PHASE5_PYDEVICES_MARKER=' + "
            f"ujson.dumps(ujson.load(open({MARKER_PATH!r}))))\n",
            max(args.timeout, 45),
        )
        marker = _extract(output, "PHASE5_PYDEVICES_MARKER")
        if (marker.get("schema") != 1 or
                marker.get("profile") != "pydevices-modern-comparison" or
                set(marker.get("original_selectors", {})) !=
                set(SELECTOR_PATHS)):
            raise ValueError("unexpected comparison cleanup marker")
        for path, identity in marker["original_selectors"].items():
            original = base64.b64decode(identity["b64"])
            if _sha256(original) != identity["sha256"]:
                raise ValueError(f"saved selector hash mismatch: {path}")
            repl.stream_file(
                path, original, identity["sha256"], max(args.timeout, 90))
        remove_code = r'''
import os, ujson
removed = []
for path in %r:
    try:
        os.remove(path)
        removed.append(path)
    except OSError:
        pass
os.remove(%r)
print("PHASE5_PYDEVICES_CLEANED=" + ujson.dumps({"removed": removed}))
''' % (tuple(STAGED_FILES), MARKER_PATH)
        result = _extract(
            repl.exec(remove_code, max(args.timeout, 45)),
            "PHASE5_PYDEVICES_CLEANED",
        )
    finally:
        repl.close()
    print(json.dumps(result, indent=2, sort_keys=True))


def soft_reset(args: argparse.Namespace) -> None:
    """Request MicroPython's raw-REPL Ctrl-D soft reset."""
    repl = _connect(args)
    try:
        repl.serial.write(b"\x04")
        time.sleep(0.5)
    finally:
        repl.close()
    print(f"Soft reset requested on {args.port}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=int, default=15)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("stage").set_defaults(func=stage)
    commands.add_parser("cleanup").set_defaults(func=cleanup)
    commands.add_parser("soft-reset").set_defaults(func=soft_reset)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
