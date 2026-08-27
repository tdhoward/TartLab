"""Validate the isolated modern release authenticity and feed policy."""

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
DEFAULT_POLICY = ROOT / "profiles/modern-release-authenticity.json"
PROMOTION_WORKFLOW = ROOT / ".github/workflows/promote-modern-release.yml"
QUALIFICATION_WORKFLOW = ROOT / ".github/workflows/attest-modern-candidate.yml"
MODERN_TAG = re.compile(r"^modern-v[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("%s: expected a JSON object" % path)
    return value


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("schema") != 1 or \
            policy.get("mechanism") != "github-artifact-attestation":
        raise ValueError("unexpected modern authenticity policy")
    if policy.get("source_repository") != "tdhoward/TartLab":
        raise ValueError("modern provenance must be bound to the source repository")
    if policy.get("target_repository") != "tdhoward/TartLab-modern-releases":
        raise ValueError("modern releases must target the isolated repository")
    if policy.get("signer_workflow") != \
            "tdhoward/TartLab/.github/workflows/promote-modern-release.yml":
        raise ValueError("unexpected modern signer workflow")
    if policy.get("qualification_signer_workflow") != \
            "tdhoward/TartLab/.github/workflows/attest-modern-candidate.yml":
        raise ValueError("unexpected modern qualification signer workflow")
    if policy.get("predicate_type") != "https://slsa.dev/provenance/v1":
        raise ValueError("modern attestations must use SLSA provenance")
    action = policy.get("action")
    if not isinstance(action, dict) or action.get("repository") != "actions/attest":
        raise ValueError("modern attestation action is invalid")
    commit = action.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("modern attestation action must use a full commit pin")
    if action.get("version") != "v4.2.1":
        raise ValueError("unexpected modern attestation action version")
    if policy.get("release_subjects") != ["*.tar", "*.json", "*.bin", "*.md"]:
        raise ValueError("modern attestation subjects are incomplete")
    if policy.get("bundle_asset") != "release-attestation.sigstore.json":
        raise ValueError("unexpected modern attestation bundle")
    if policy.get("qualification_bundle_asset") != \
            "qualification-attestation.sigstore.json":
        raise ValueError("unexpected modern qualification attestation bundle")
    scope = policy.get("scope")
    expected_scope = {
        "release_profile": "lvgl-modern",
        "manifest": "modern-manifest.json",
        "legacy_repository_allowed": False,
        "on_device_enforcement": False,
        "adult_provisioning_preflight": "tools/check_modern_release.py",
        "adult_provisioning_tool": "tools/provision_modern.py",
        "qualification_validator": "tools/check_modern_qualification.py",
        "support_window_policy": "profiles/modern-support-window.json",
    }
    if scope != expected_scope:
        raise ValueError("modern authenticity scope is incomplete")


def validate_workflow(policy: dict[str, Any], workflow_path: Path,
                      qualification_workflow_path: Path) -> None:
    source = workflow_path.read_text(encoding="utf-8")
    required = (
        "environment: modern-release",
        "id-token: write",
        "attestations: write",
        "MODERN_RELEASE_TOKEN",
        'TARGET_REPOSITORY: "tdhoward/TartLab-modern-releases"',
        "tools/build_modern_release.py",
        "tools/check_modern_release.py",
        "tools/check_modern_qualification.py",
        "--expected-sha256 \"$EVIDENCE_HASH\"",
        f"uses: actions/attest@{policy['action']['commit']}",
        "build/promote-modern/release/*.tar",
        "build/promote-modern/release/*.json",
        "build/promote-modern/release/*.bin",
        "build/promote-modern/release/*.md",
        "steps.attest_release.outputs.bundle-path",
        "--repo \"$TARGET_REPOSITORY\"",
        "--promotion-tag \"$RELEASE_TAG\"",
    )
    for marker in required:
        if marker not in source:
            raise ValueError("modern promotion workflow is missing marker: %s" % marker)
    if "continue-on-error" in source:
        raise ValueError("modern promotion workflow must fail closed")
    attest_at = source.index(f"uses: actions/attest@{policy['action']['commit']}")
    publish_at = source.index('gh release create "$RELEASE_TAG"')
    if attest_at > publish_at:
        raise ValueError("modern assets must be attested before publication")

    qualification_source = qualification_workflow_path.read_text(
        encoding="utf-8")
    qualification_required = (
        "environment: modern-qualification",
        "id-token: write",
        "attestations: write",
        "--qualification-tag \"$RELEASE_TAG\"",
        "tools/build_modern_release.py",
        "tools/compare_releases.py",
        "tools/check_modern_release.py",
        f"uses: actions/attest@{policy['action']['commit']}",
        "build/qualification/release/*.tar",
        "build/qualification/release/*.json",
        "build/qualification/release/*.bin",
        "build/qualification/release/*.md",
        "qualification-attestation.sigstore.json",
        "actions/upload-artifact@v7",
    )
    for marker in qualification_required:
        if marker not in qualification_source:
            raise ValueError(
                "modern qualification workflow is missing marker: %s" % marker)
    if "gh release create" in qualification_source or \
            "MODERN_RELEASE_TOKEN" in qualification_source:
        raise ValueError("modern qualification workflow must not publish")
    if "continue-on-error" in qualification_source:
        raise ValueError("modern qualification workflow must fail closed")


def validate_ci_identity(tag: str, commit: str,
                         environment: dict[str, str] | None = None) -> None:
    environment = environment if environment is not None else os.environ
    if not MODERN_TAG.fullmatch(tag):
        raise ValueError("modern promotion requires modern-vMAJOR.MINOR[.PATCH]")
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "tdhoward/TartLab",
        "GITHUB_REF": "refs/tags/%s" % tag,
        "GITHUB_SHA": commit,
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise ValueError("modern promotion identity mismatch: %s" % name)


def release_assets(release: Path, policy: dict[str, Any], *,
                   purpose: str = "release") -> list[Path]:
    if not release.is_dir():
        raise ValueError("modern release directory not found: %s" % release)
    if purpose not in ("release", "qualification"):
        raise ValueError("unknown modern attestation purpose")
    all_bundles = {
        policy["bundle_asset"], policy["qualification_bundle_asset"]}
    assets = sorted({
        path for pattern in policy["release_subjects"]
        for path in release.glob(pattern)
        if path.is_file() and path.name not in all_bundles
    })
    required = {
        "modern-manifest.json", "build_metadata.json", "checksums.json",
        "compatibility.json",
        "firmware-build-lock.json", "firmware-provenance.json",
        "filesystem-vendor-lock.json", "support-window.json", "MIGRATION.md",
    }
    if purpose == "release":
        required.add("promotion_attestation.json")
    missing = sorted(required.difference(path.name for path in assets))
    if missing:
        raise ValueError("modern release is missing metadata: %s" % missing[0])
    if (release / "manifest.json").exists():
        raise ValueError("modern release contains the legacy manifest")
    if not any(path.suffix == ".tar" for path in assets):
        raise ValueError("modern release contains no filesystem packages")
    if not any(path.suffix == ".bin" for path in assets):
        raise ValueError("modern release contains no firmware image")
    return assets


def verification_command(asset: Path, policy: dict[str, Any], *,
                         bundle: Path | None = None,
                         source_ref: str | None = None,
                         purpose: str = "release") -> list[str]:
    if purpose not in ("release", "qualification"):
        raise ValueError("unknown modern attestation purpose")
    signer = policy[
        "signer_workflow" if purpose == "release" else
        "qualification_signer_workflow"]
    command = [
        "gh", "attestation", "verify", str(asset),
        "--repo", policy["source_repository"],
        "--signer-workflow", signer,
        "--predicate-type", policy["predicate_type"],
        "--deny-self-hosted-runners",
    ]
    if bundle is not None:
        command.extend(("--bundle", str(bundle)))
    if source_ref is not None:
        command.extend(("--source-ref", source_ref))
    return command


def check(policy_path: Path = DEFAULT_POLICY,
          workflow_path: Path = PROMOTION_WORKFLOW,
          qualification_workflow_path: Path =
          QUALIFICATION_WORKFLOW) -> dict[str, object]:
    policy = load_json(policy_path)
    validate_policy(policy)
    validate_workflow(policy, workflow_path, qualification_workflow_path)
    return {
        "mechanism": policy["mechanism"],
        "source_repository": policy["source_repository"],
        "target_repository": policy["target_repository"],
        "profile": "lvgl-modern",
        "qualification_signer_workflow": policy[
            "qualification_signer_workflow"],
        "on_device_enforcement": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--workflow", type=Path, default=PROMOTION_WORKFLOW)
    parser.add_argument(
        "--qualification-workflow", type=Path,
        default=QUALIFICATION_WORKFLOW)
    parser.add_argument("--release", type=Path)
    parser.add_argument("--promotion-tag")
    parser.add_argument("--qualification-tag")
    parser.add_argument("--source-ref")
    parser.add_argument(
        "--purpose", choices=("release", "qualification"), default="release")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = check(
        args.policy, args.workflow, args.qualification_workflow)
    if args.promotion_tag is not None and args.qualification_tag is not None:
        raise ValueError(
            "choose only one of --promotion-tag and --qualification-tag")
    identity_tag = args.promotion_tag or args.qualification_tag
    if identity_tag is not None:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        validate_ci_identity(identity_tag, commit)
        result[
            "promotion_identity" if args.promotion_tag else
            "qualification_identity"] = {
            "tag": identity_tag,
            "commit": commit,
        }
    if args.release is not None:
        policy = load_json(args.policy)
        assets = release_assets(
            args.release, policy, purpose=args.purpose)
        bundle_name = policy[
            "bundle_asset" if args.purpose == "release" else
            "qualification_bundle_asset"]
        bundle = args.release / bundle_name
        if args.execute and not bundle.is_file():
            raise ValueError("modern release attestation bundle not found")
        commands = [
            verification_command(
                asset, policy, bundle=bundle if bundle.is_file() else None,
                source_ref=args.source_ref, purpose=args.purpose)
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
    elif args.execute:
        raise ValueError("--execute requires --release")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
