"""Deliberately interrupt one physical clean-provisioning transport command.

This qualification helper is intentionally separate from the production
provisioner.  It verifies the signed candidate normally, starts a clean
transaction, terminates exactly one named esptool/mpremote subprocess, and
records a sanitized interruption receipt in the private workspace.  Resume the
transaction with ``tools/provision_modern.py --resume``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Sequence

from provision_modern import (
    CommandTransport, _verify_attestations, provision,
)
from release_utils import sha256_file


UPLOAD_NAMES = (
    "configs", "defaults", "device", "files", "ide", "lib", "recovery",
    "state",
)
CHECKPOINTS = (
    "erase-flash", "write-flash", "verify-flash",
    "placeholder-boot", "placeholder-main",
    *("upload-" + name for name in UPLOAD_NAMES),
    "activate-boot", "activate-main",
)
ATTESTATION_RECEIPT = "qualification-attestation-verification.json"


class IntendedInterruption(RuntimeError):
    """Raised after the selected physical subprocess has been terminated."""


def command_checkpoint(command: Sequence[str], verify_count: int = 0
                       ) -> tuple[str | None, int]:
    """Classify a provisioner subprocess and track verify-flash occurrences."""

    if "erase-flash" in command:
        return "erase-flash", verify_count
    if "write-flash" in command:
        return "write-flash", verify_count
    if "verify-flash" in command:
        verify_count += 1
        # The first verify probes the existing image.  Qualification interrupts
        # the post-write verification, which is the second occurrence.
        checkpoint = "verify-flash" if verify_count >= 2 else None
        return checkpoint, verify_count
    if not command or Path(command[0]).name.lower() not in (
            "mpremote", "mpremote.exe") or "cp" not in command:
        return None, verify_count

    copy_index = command.index("cp")
    if len(command) <= copy_index + 2:
        return None, verify_count
    source = Path(command[copy_index + 1])
    destination = command[copy_index + 2]
    if source.name == "provisioning-placeholder.py":
        return (
            "placeholder-boot" if destination.endswith("boot.py")
            else "placeholder-main" if destination.endswith("main.py")
            else None,
            verify_count,
        )
    if source.name == "boot.py" and destination.endswith("boot.py"):
        return "activate-boot", verify_count
    if source.name == "main.py" and destination.endswith("main.py"):
        return "activate-main", verify_count
    if source.name in UPLOAD_NAMES:
        return "upload-" + source.name, verify_count
    return None, verify_count


def next_receipt_path(workspace: Path) -> Path:
    """Return a collision-free receipt path without replacing prior evidence."""

    first = workspace / "qualification-interruption.json"
    if not first.exists():
        return first
    index = 2
    while True:
        candidate = workspace / (
            "qualification-interruption-%03d.json" % index)
        if not candidate.exists():
            return candidate
        index += 1


def attestation_identity(release: Path, source_ref: str) -> dict[str, object]:
    return {
        "schema": 1,
        "source_ref": source_ref,
        "checksums_sha256": sha256_file(release / "checksums.json"),
        "bundle_sha256": sha256_file(
            release / "qualification-attestation.sigstore.json"),
    }


def verify_cached_attestation(release: Path, workspace: Path,
                              source_ref: str) -> dict[str, object]:
    path = workspace / ATTESTATION_RECEIPT
    if not path.is_file():
        raise ValueError("no cached qualification attestation receipt exists")
    cached = json.loads(path.read_text(encoding="utf-8"))
    expected = attestation_identity(release, source_ref)
    if cached != expected:
        raise ValueError("cached qualification attestation receipt changed")
    return expected


class InterruptingTransport(CommandTransport):
    """Physical transport that terminates one selected child process."""

    def __init__(self, port: str, checkpoint: str, delay: float):
        super().__init__(port)
        self.checkpoint = checkpoint
        self.delay = delay
        self.verify_count = 0
        self.receipt: dict[str, object] | None = None

    def _run(self, command: list[str], *, check: bool = True
             ) -> subprocess.CompletedProcess[str]:
        checkpoint, self.verify_count = command_checkpoint(
            command, self.verify_count)
        if checkpoint != self.checkpoint:
            return super()._run(command, check=check)

        started = time.monotonic()
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(
            command, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=environment)
        time.sleep(self.delay)
        completed_before_interrupt = process.poll() is not None
        if not completed_before_interrupt:
            process.terminate()
            try:
                output, unused = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, unused = process.communicate(timeout=5)
        else:
            output, unused = process.communicate(timeout=5)

        self.receipt = {
            "schema": 1,
            "checkpoint": checkpoint,
            "delay_seconds": self.delay,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "completed_before_interrupt": completed_before_interrupt,
            "returncode": process.returncode,
            "command": [Path(command[0]).name, *command[1:]],
            "output_tail": output[-1000:],
        }
        if completed_before_interrupt:
            raise RuntimeError(
                "%s completed before the qualification interruption; use a "
                "shorter --delay" % checkpoint)
        raise IntendedInterruption(
            "intentionally terminated physical checkpoint: " + checkpoint)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--checkpoint", choices=CHECKPOINTS, required=True)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reuse-attestation", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-interrupt", action="store_true")
    args = parser.parse_args()

    if not args.execute or not args.confirm_interrupt:
        raise ValueError(
            "physical interruption requires --execute and --confirm-interrupt")
    if args.delay <= 0 or args.delay > 10:
        raise ValueError("--delay must be greater than zero and at most 10")

    release = args.release.resolve()
    workspace = args.workspace.resolve()
    if args.reuse_attestation:
        attestation = verify_cached_attestation(
            release, workspace, args.source_ref)
    else:
        _verify_attestations(release, args.source_ref)
        attestation = attestation_identity(release, args.source_ref)
        if (workspace / "provisioning-journal.json").is_file():
            (workspace / ATTESTATION_RECEIPT).write_text(
                json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
    transport = InterruptingTransport(
        args.port, args.checkpoint, args.delay)
    try:
        provision(release, workspace, "clean", transport, resume=args.resume)
    except IntendedInterruption as error:
        if transport.receipt is None:
            raise RuntimeError("interruption produced no receipt") from error
        attestation_path = workspace / ATTESTATION_RECEIPT
        if not attestation_path.is_file():
            attestation_path.write_text(
                json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
        receipt_path = next_receipt_path(workspace)
        receipt_path.write_text(
            json.dumps(transport.receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "interrupted": True,
            "checkpoint": args.checkpoint,
            "workspace": str(workspace),
            "receipt": str(receipt_path),
        }, indent=2))
        return
    raise RuntimeError("selected checkpoint was not reached: " + args.checkpoint)


if __name__ == "__main__":
    main()
