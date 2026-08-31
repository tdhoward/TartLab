"""Bind a tested modern candidate and physical evidence to promotion."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from check_modern_release import check as check_modern_release
from check_modern_release_authenticity import MODERN_TAG, validate_ci_identity
from check_modern_qualification import check as check_modern_qualification
from release_utils import read_json, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TARGET_REPOSITORY = "tdhoward/TartLab-modern-releases"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--candidate-checksums-sha256", required=True)
    parser.add_argument("--hardware-evidence-sha256", required=True)
    parser.add_argument("--hardware-evidence-reference", required=True)
    parser.add_argument("--hardware-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate_hash = args.candidate_checksums_sha256.lower()
    evidence_hash = args.hardware_evidence_sha256.lower()
    if not MODERN_TAG.fullmatch(args.tag):
        raise ValueError("Modern tags must use modern-vMAJOR.MINOR[.PATCH]")
    if not SHA256.fullmatch(candidate_hash) or not SHA256.fullmatch(evidence_hash):
        raise ValueError("Candidate and evidence hashes must be lowercase SHA-256")
    evidence_reference = args.hardware_evidence_reference.strip()
    parsed_reference = urlsplit(evidence_reference)
    if parsed_reference.scheme != "https" or not parsed_reference.netloc or \
            parsed_reference.username is not None or \
            parsed_reference.password is not None or parsed_reference.query or \
            parsed_reference.fragment:
        raise ValueError(
            "Hardware evidence must use a durable public HTTPS URL without "
            "credentials, query, or fragment")
    if sha256_file(args.release / "checksums.json") != candidate_hash:
        raise ValueError("Rebuilt modern release differs from the tested candidate")
    qualification = check_modern_qualification(
        args.hardware_evidence, tag=args.tag,
        candidate_sha256=candidate_hash, expected_sha256=evidence_hash)
    metadata = read_json(args.release / "build_metadata.json")
    manifest = read_json(args.release / "modern-manifest.json")
    if metadata["tartlab_version"] != args.tag or manifest["version"] != args.tag:
        raise ValueError("Modern tag differs from release version")
    if metadata["git_dirty"]:
        raise ValueError("A dirty modern build cannot be promoted")
    compatibility = manifest["compatibility"]
    manifest_boards = compatibility.get("boards")
    if isinstance(manifest_boards, dict):
        release_boards = {
            board_id: record["firmware"]["sha256"]
            for board_id, record in manifest_boards.items()
        }
    else:
        release_boards = qualification["boards"]
    if qualification["boards"] != release_boards:
        raise ValueError(
            "Qualification evidence does not cover every release board")
    default_board_id = compatibility.get(
        "default_board_id", next(iter(release_boards)))
    firmware_hash = release_boards[default_board_id]
    check_modern_release(
        args.release, "lvgl-modern", firmware_hash, board_id=default_board_id)

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tag_commit = subprocess.check_output(
        ["git", "rev-parse", "refs/tags/%s^{commit}" % args.tag],
        cwd=ROOT, text=True).strip()
    if tag_commit != commit or metadata["git_commit"] != commit:
        raise ValueError("Modern release is not bound to the checked-out tag")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        validate_ci_identity(args.tag, commit)

    write_json(args.output, {
        "schema": 2,
        "profile": "lvgl-modern",
        "tartlab_version": args.tag,
        "git_commit": commit,
        "target_repository": TARGET_REPOSITORY,
        "runtime_profile": "lvgl-modern",
        "firmware_sha256": firmware_hash,
        "default_board_id": default_board_id,
        "boards": release_boards,
        "candidate_checksums_sha256": candidate_hash,
        "hardware_evidence_sha256": evidence_hash,
        "hardware_evidence_reference": evidence_reference,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    })
    print("Modern promotion attestation created for %s" % args.tag)


if __name__ == "__main__":
    main()
