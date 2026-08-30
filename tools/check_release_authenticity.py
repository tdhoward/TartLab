"""Validate and optionally verify TartLab's release-authenticity policy.

Stable assets are attested by the protected promotion workflow using GitHub's
keyless Sigstore-backed artifact attestations.  Static checks keep that workflow
bound to the reviewed repository, signer workflow, predicate, and action pin.
Post-release verification delegates cryptographic verification to GitHub CLI.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "profiles/release-authenticity.json"
PROMOTION_WORKFLOW = ROOT / ".github/workflows/promote-legacy-release.yml"
SHA256_LENGTH = 40
STABLE_TAG = re.compile(r"^v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema") != 1:
        raise ValueError("unexpected release-authenticity policy schema")
    if policy.get("mechanism") != "github-artifact-attestation":
        raise ValueError("unsupported release-authenticity mechanism")
    if policy.get("repository") != "tdhoward/TartLab":
        raise ValueError("release attestations must be bound to tdhoward/TartLab")
    expected_workflow = (
        "tdhoward/TartLab/.github/workflows/promote-legacy-release.yml")
    if policy.get("signer_workflow") != expected_workflow:
        raise ValueError("release attestations must require the promotion workflow")
    if policy.get("predicate_type") != "https://slsa.dev/provenance/v1":
        raise ValueError("release attestations must require SLSA provenance")

    action = policy.get("action")
    if not isinstance(action, dict) or action.get("repository") != "actions/attest":
        raise ValueError("release attestation action is invalid")
    commit = action.get("commit")
    if (not isinstance(commit, str) or len(commit) != SHA256_LENGTH or
            any(character not in "0123456789abcdef" for character in commit)):
        raise ValueError("release attestation action must use a full commit pin")
    if action.get("version") != "v4.2.1":
        raise ValueError("unexpected release attestation action version")

    if policy.get("release_subjects") != ["*.tar", "*.json"]:
        raise ValueError("release attestation subjects are incomplete")
    if policy.get("bundle_asset") != "release-attestation.sigstore.json":
        raise ValueError("unexpected release attestation bundle name")
    scope = policy.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("release authenticity scope is missing")
    if scope.get("release_profiles") != ["legacy-mp123"]:
        raise ValueError("release authenticity scope must cover legacy promotion")
    if scope.get("modern_profile") != "research-only-not-for-promotion":
        raise ValueError("modern profile must remain outside release promotion")
    if scope.get("on_device_enforcement") is not False:
        raise ValueError("policy must not claim on-device authenticity enforcement")


def validate_workflow(policy: dict[str, Any], workflow_path: Path) -> None:
    try:
        source = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{workflow_path}: {exc}") from exc

    required = (
        "id-token: write",
        "attestations: write",
        "contents: write",
        f"uses: actions/attest@{policy['action']['commit']}",
        "id: attest_release",
        "build/promote/release/*.tar",
        "build/promote/release/*.json",
        "steps.attest_release.outputs.bundle-path",
        f"build/promote/release/{policy['bundle_asset']}",
        "--promotion-tag \"$RELEASE_TAG\"",
    )
    for marker in required:
        if marker not in source:
            raise ValueError(f"promotion workflow is missing authenticity marker: {marker}")
    if "continue-on-error" in source:
        raise ValueError("promotion workflow must fail closed on attestation errors")

    attest_at = source.index(f"uses: actions/attest@{policy['action']['commit']}")
    publish_at = source.index('gh release create "$RELEASE_TAG"')
    if attest_at > publish_at:
        raise ValueError("release assets must be attested before publication")

    source_epoch_at = source.index(
        'echo "SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)" >> "$GITHUB_ENV"')
    mpy_cross_at = source.index(
        "make -C build/micropython-v1.23.0/mpy-cross -j2")
    if source_epoch_at > mpy_cross_at:
        raise ValueError(
            "promotion must set SOURCE_DATE_EPOCH before building mpy-cross")


def validate_ci_identity(tag: str, commit: str,
                         environment: dict[str, str] | None = None) -> None:
    """Bind the keyless certificate identity to the exact promoted tag."""

    environment = environment if environment is not None else os.environ
    if not STABLE_TAG.fullmatch(tag):
        raise ValueError("promotion identity requires a stable vMAJOR.MINOR tag")
    expected_ref = f"refs/tags/{tag}"
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "tdhoward/TartLab",
        "GITHUB_REF": expected_ref,
        "GITHUB_SHA": commit,
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise ValueError(
                f"promotion identity mismatch: {name} must be {value}")


def release_assets(release: Path, policy: dict[str, Any]) -> list[Path]:
    if not release.is_dir():
        raise ValueError(f"release directory not found: {release}")
    bundle = policy["bundle_asset"]
    assets = sorted(
        path for pattern in policy["release_subjects"]
        for path in release.glob(pattern)
        if path.is_file() and path.name != bundle)
    unique = list(dict.fromkeys(assets))
    required = {"manifest.json", "build_metadata.json", "checksums.json",
                "promotion_attestation.json"}
    missing = sorted(required.difference(path.name for path in unique))
    if missing:
        raise ValueError(f"release is missing authenticated metadata: {missing[0]}")
    if not any(path.suffix == ".tar" for path in unique):
        raise ValueError("release contains no package archives to authenticate")
    return unique


def verification_command(asset: Path, policy: dict[str, Any], *,
                         bundle: Path | None = None,
                         source_ref: str | None = None) -> list[str]:
    command = [
        "gh", "attestation", "verify", str(asset),
        "--repo", policy["repository"],
        "--signer-workflow", policy["signer_workflow"],
        "--predicate-type", policy["predicate_type"],
        "--deny-self-hosted-runners",
    ]
    if bundle is not None:
        command.extend(("--bundle", str(bundle)))
    if source_ref is not None:
        command.extend(("--source-ref", source_ref))
    return command


def check(policy_path: Path = DEFAULT_POLICY,
          workflow_path: Path = PROMOTION_WORKFLOW) -> dict[str, object]:
    policy = load_json(policy_path)
    validate_policy(policy)
    validate_workflow(policy, workflow_path)
    return {
        "mechanism": policy["mechanism"],
        "repository": policy["repository"],
        "signer_workflow": policy["signer_workflow"],
        "on_device_enforcement": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--workflow", type=Path, default=PROMOTION_WORKFLOW)
    parser.add_argument("--release", type=Path)
    parser.add_argument("--source-ref", help="expected source ref, e.g. refs/tags/v1.0")
    parser.add_argument("--promotion-tag",
                        help="validate this Actions run's repository/tag/commit identity")
    parser.add_argument("--execute", action="store_true",
                        help="run gh attestation verify for every release asset")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = check(args.policy, args.workflow)
    if args.promotion_tag is not None:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        validate_ci_identity(args.promotion_tag, commit)
        result["promotion_identity"] = {
            "tag": args.promotion_tag,
            "commit": commit,
        }
    if args.execute and args.release is None:
        raise ValueError("--execute requires --release")
    if args.release is not None:
        policy = load_json(args.policy)
        assets = release_assets(args.release, policy)
        bundle = args.release / policy["bundle_asset"]
        if args.execute and not bundle.is_file():
            raise ValueError(f"release attestation bundle not found: {bundle}")
        commands = [
            verification_command(
                asset, policy, bundle=bundle if bundle.is_file() else None,
                source_ref=args.source_ref)
            for asset in assets
        ]
        result["release_assets"] = len(assets)
        result["verification_commands"] = commands
        if args.execute:
            if shutil.which("gh") is None:
                raise ValueError("GitHub CLI is required for attestation verification")
            for command in commands:
                subprocess.run(command, check=True)
            result["verified"] = True
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
