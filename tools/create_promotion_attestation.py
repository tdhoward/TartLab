"""Create the auditable bridge from physical evidence to stable promotion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys

from release_utils import read_json, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STABLE_TAG = re.compile(r"^v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--candidate-checksums-sha256", required=True)
    parser.add_argument("--hardware-evidence-sha256", required=True)
    parser.add_argument("--hardware-evidence-reference", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate_hash = args.candidate_checksums_sha256.lower()
    evidence_hash = args.hardware_evidence_sha256.lower()
    if not STABLE_TAG.fullmatch(args.tag):
        raise ValueError("Stable legacy tags must use vMAJOR.MINOR or vMAJOR.MINOR.PATCH")
    if not args.hardware_evidence_reference.strip():
        raise ValueError("A durable physical-evidence reference is required")
    if not SHA256.fullmatch(candidate_hash) or not SHA256.fullmatch(evidence_hash):
        raise ValueError("Evidence and candidate hashes must be lowercase SHA-256 values")
    actual_candidate_hash = sha256_file(args.release / "checksums.json")
    if actual_candidate_hash != candidate_hash:
        raise ValueError(
            "Rebuilt release differs from the candidate that passed physical testing")
    metadata = read_json(args.release / "build_metadata.json")
    if metadata["tartlab_version"] != args.tag:
        raise ValueError("Release tag differs from build metadata version")
    vendor_status = metadata.get("vendor_payload", {}).get("promotion_status")
    if metadata.get("artifact_status") is not None or vendor_status != "promoted":
        raise ValueError("Stable promotion requires the promoted PyDevices payload")
    if metadata["git_dirty"]:
        raise ValueError("A dirty build cannot be promoted")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tag_commit = subprocess.check_output(
        ["git", "rev-parse", "refs/tags/%s^{commit}" % args.tag],
        cwd=ROOT, text=True).strip()
    if tag_commit != commit:
        raise ValueError("Checked-out commit does not match the requested stable tag")
    if metadata["git_commit"] != commit:
        raise ValueError("Release metadata commit differs from checked-out tag")

    attestation = {
        "schema": 1,
        "profile": metadata["profile"],
        "tartlab_version": args.tag,
        "git_commit": commit,
        "candidate_checksums_sha256": candidate_hash,
        "hardware_evidence_sha256": evidence_hash,
        "hardware_evidence_reference": args.hardware_evidence_reference,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "github_run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
    }
    write_json(args.output, attestation)
    print("Promotion attestation created for %s" % args.tag)


if __name__ == "__main__":
    main()
