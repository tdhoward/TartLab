"""Validate the sanitized evidence required to promote a modern release."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Sequence

from release_utils import read_json, sha256_file


SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODERN_TAG = re.compile(r"^modern-v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
PROFILE = "lvgl-modern"
TARGET_REPOSITORY = "tdhoward/TartLab-modern-releases"
FIRMWARE_SHA256 = (
    "187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab")
REQUIRED_GATES = (
    "adult_provisioning",
    "hardware",
    "ota",
    "recovery",
    "release_feed_isolation",
    "support_window",
)
TOP_LEVEL_KEYS = {
    "schema", "profile", "version", "target_repository",
    "candidate_checksums_sha256", "firmware_sha256", "board",
    "operator", "tested_at_utc", "artifacts", "gates",
}
ARTIFACT_KEYS = {
    "clean_provisioning_journal_sha256",
    "migration_provisioning_journal_sha256",
    "serial_log_sha256",
}


def _require_exact_keys(value: dict[str, Any], expected: set[str],
                        label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            "%s keys differ: missing=%s unexpected=%s" % (
                label, sorted(expected - actual), sorted(actual - expected)))


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError("%s must be a lowercase SHA-256" % label)
    return value


def validate(evidence: dict[str, Any], *, tag: str, candidate_sha256: str,
             firmware_sha256: str = FIRMWARE_SHA256) -> dict[str, Any]:
    """Validate one candidate-bound, sanitized qualification summary."""
    if not isinstance(evidence, dict):
        raise ValueError("Qualification evidence must be a JSON object")
    _require_exact_keys(evidence, TOP_LEVEL_KEYS, "qualification evidence")
    if evidence["schema"] != 1:
        raise ValueError("Unsupported qualification evidence schema")
    if not MODERN_TAG.fullmatch(tag) or evidence["version"] != tag:
        raise ValueError("Qualification evidence version does not match modern tag")
    if evidence["profile"] != PROFILE:
        raise ValueError("Qualification evidence targets the wrong profile")
    if evidence["target_repository"] != TARGET_REPOSITORY:
        raise ValueError("Qualification evidence targets the wrong repository")
    if _require_sha256(
            evidence["candidate_checksums_sha256"],
            "candidate_checksums_sha256") != candidate_sha256:
        raise ValueError("Qualification evidence targets a different candidate")
    if _require_sha256(
            evidence["firmware_sha256"],
            "firmware_sha256") != firmware_sha256:
        raise ValueError("Qualification evidence targets different firmware")

    board = evidence["board"]
    if not isinstance(board, dict):
        raise ValueError("Qualification board must be an object")
    _require_exact_keys(board, {
        "model", "pcb_revision", "chip_revision", "flash_size_bytes",
        "psram_size_bytes",
    }, "board")
    if board.get("model") != "LilyGO T-Display-S3 Pro" or \
            board.get("pcb_revision") != "1.1" or \
            board.get("flash_size_bytes") != 16777216 or \
            board.get("psram_size_bytes") != 8388608:
        raise ValueError("Qualification evidence targets an unapproved board")
    if not isinstance(board.get("chip_revision"), str) or not \
            board["chip_revision"].strip():
        raise ValueError("Qualification evidence requires the chip revision")

    operator = evidence["operator"]
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("Qualification evidence requires an operator")
    tested_at = evidence["tested_at_utc"]
    if not isinstance(tested_at, str) or not tested_at.endswith("Z"):
        raise ValueError("tested_at_utc must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(tested_at[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("tested_at_utc must be an RFC 3339 UTC timestamp") from exc

    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, dict):
        raise ValueError("Qualification artifacts must be an object")
    _require_exact_keys(artifacts, ARTIFACT_KEYS, "qualification artifacts")
    for name, value in artifacts.items():
        _require_sha256(value, name)

    gates = evidence["gates"]
    if not isinstance(gates, dict):
        raise ValueError("Qualification gates must be an object")
    _require_exact_keys(gates, set(REQUIRED_GATES), "qualification gates")
    for name in REQUIRED_GATES:
        gate = gates[name]
        if not isinstance(gate, dict):
            raise ValueError("Qualification gate %s must be an object" % name)
        _require_exact_keys(gate, {"status", "evidence"}, "gate %s" % name)
        if gate["status"] != "passed":
            raise ValueError("Qualification gate %s has not passed" % name)
        references = gate["evidence"]
        if not isinstance(references, list) or not references or not all(
                isinstance(item, str) and item.strip() for item in references):
            raise ValueError(
                "Qualification gate %s requires evidence references" % name)

    return {
        "profile": PROFILE,
        "version": tag,
        "candidate_checksums_sha256": candidate_sha256,
        "firmware_sha256": firmware_sha256,
        "passed_gates": list(REQUIRED_GATES),
    }


def check(path: Path, *, tag: str, candidate_sha256: str,
          expected_sha256: str | None = None) -> dict[str, Any]:
    if expected_sha256 is not None:
        _require_sha256(expected_sha256, "expected evidence SHA-256")
        if sha256_file(path) != expected_sha256:
            raise ValueError("Qualification evidence SHA-256 does not match input")
    return validate(
        read_json(path), tag=tag, candidate_sha256=candidate_sha256)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--candidate-checksums-sha256", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    result = check(
        args.evidence, tag=args.tag,
        candidate_sha256=args.candidate_checksums_sha256.lower(),
        expected_sha256=args.expected_sha256.lower())
    print(
        "Modern qualification passed %d gates for %s" % (
            len(result["passed_gates"]), result["version"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
