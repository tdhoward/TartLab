"""Validate the modern migration support-window decision and source backup."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Sequence

from board_catalog import default_board

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "profiles/modern-support-window.json"
STABLE_VERSION = re.compile(r"^v([0-9]+)\.([0-9]+)(?:\.([0-9]+))?$")
PROFILE_BOARD = default_board("lvgl-modern")
EXPECTED_FIRMWARE_SHA256 = (
    "41a750a8f047224e3e0a7544a626338c252407df420e2b94dcb0d2dad9793212")


def _require_exact_keys(value: dict[str, Any], expected: set[str],
                        label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(
            "%s keys differ: missing=%s unexpected=%s" % (
                label, sorted(expected - actual), sorted(actual - expected)))


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("%s: expected a JSON object" % path)
    return value


def _version(value: Any, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError("%s must be a stable TartLab version" % label)
    match = STABLE_VERSION.fullmatch(value)
    if match is None:
        raise ValueError("%s must be a stable TartLab version" % label)
    return tuple(int(part or 0) for part in match.groups())


def validate_policy(policy: dict[str, Any], *, root: Path = ROOT) -> None:
    """Require the exact approved support floor and below-floor disposition."""

    _require_exact_keys(policy, {
        "schema", "profile", "decision", "direct_migration",
        "floor_evidence", "below_floor",
    }, "support-window policy")
    if policy.get("schema") != 1 or policy.get("profile") != "lvgl-modern" or \
            policy.get("decision") != "approved":
        raise ValueError("unexpected modern support-window policy")
    direct = policy.get("direct_migration")
    if not isinstance(direct, dict):
        raise ValueError("modern direct-migration window is missing")
    _require_exact_keys(direct, {
        "source_profile", "source_repository", "minimum_tartlab_version",
        "version_rule", "firmware_sha256", "board", "pcb_revision",
        "selector_marker", "supported_layouts",
    }, "direct-migration policy")
    expected = {
        "source_profile": "legacy-mp123",
        "source_repository": "tdhoward/TartLab",
        "minimum_tartlab_version": "v0.13",
        "version_rule": "stable-at-or-newer",
        "firmware_sha256": EXPECTED_FIRMWARE_SHA256,
        "board": PROFILE_BOARD["name"],
        "pcb_revision": PROFILE_BOARD["hardware"]["revisions"][0],
        "selector_marker": "from t_display_s3_pro import *",
    }
    for name, value in expected.items():
        if direct.get(name) != value:
            raise ValueError("modern support-window has unexpected %s" % name)
    _version(direct["minimum_tartlab_version"], "minimum_tartlab_version")
    if direct.get("supported_layouts") != [
            {
                "id": "legacy-root-v1",
                "repositories": "/repos.json",
                "hardware_selector": "/hdwconfig.py",
            },
            {
                "id": "canonical-v1",
                "repositories": "/state/repos.json",
                "hardware_selector": "/device/hdwconfig.py",
            }]:
        raise ValueError("modern support-window layouts are incomplete")

    evidence = policy.get("floor_evidence")
    expected_evidence = {
        "fixture": "tests/fixtures/legacy_mp123",
        "installed_version": "v0.13",
        "legacy_physical_gate": "tests/PHASE2_HARDWARE.md",
        "modern_physical_gate": "tests/PHASE6_PROVISIONING.md",
    }
    if evidence != expected_evidence:
        raise ValueError("modern support-window floor evidence is incomplete")
    for name in ("fixture", "legacy_physical_gate", "modern_physical_gate"):
        if not (root / evidence[name]).exists():
            raise ValueError("modern support-window evidence is missing: %s" % name)

    below = policy.get("below_floor")
    if isinstance(below, dict):
        _require_exact_keys(below, {
            "automatic_migration_allowed", "action", "required_steps",
        }, "below-floor policy")
    if not isinstance(below, dict) or \
            below.get("automatic_migration_allowed") is not False or \
            below.get("action") != \
            "adult-clean-provision-with-reviewed-manual-restore" or \
            below.get("required_steps") != [
                "capture-private-backup-before-erase",
                "clean-provision-authenticated-modern-release",
                "manually-restore-reviewed-settings-and-user-files",
                "retain-backup-until-healthy-boot",
            ]:
        raise ValueError("modern below-floor administrator path is incomplete")


def _source_layout(backup: Path, layouts: list[dict[str, str]]) -> tuple[str, Path, Path]:
    for layout in reversed(layouts):
        repos = backup / layout["repositories"].lstrip("/")
        selector = backup / layout["hardware_selector"].lstrip("/")
        if repos.is_file() and selector.is_file():
            return layout["id"], repos, selector
    raise ValueError(
        "legacy source layout is outside the supported migration window")


def validate_backup(backup: Path, *, policy_path: Path = DEFAULT_POLICY) -> dict[str, str]:
    """Inspect a captured source without modifying it or the connected device."""

    policy = _read_object(policy_path)
    validate_policy(policy)
    direct = policy["direct_migration"]
    layout, repos_path, selector_path = _source_layout(
        backup, direct["supported_layouts"])
    if direct["selector_marker"] not in selector_path.read_text(encoding="utf-8"):
        raise ValueError(
            "legacy hardware selector is not the supported T-Display-S3 Pro")
    if (backup / "state/update.json").is_file():
        raise ValueError(
            "legacy source has an active update; recover it before migration")

    repositories = _read_object(repos_path)
    entries = repositories.get("list")
    if not isinstance(entries, list):
        raise ValueError("legacy source repository state is invalid")
    matches = [item for item in entries
               if isinstance(item, dict) and item.get("name") == "TartLab"]
    if len(matches) != 1:
        raise ValueError("legacy source must contain one TartLab repository record")
    tartlab = matches[0]
    source_profile = tartlab.get("runtime_profile", "legacy-mp123")
    if source_profile != direct["source_profile"]:
        raise ValueError("legacy source has an unsupported runtime profile")
    repository = tartlab.get("repo")
    if not isinstance(repository, str) or \
            repository.lower() != direct["source_repository"].lower():
        raise ValueError("legacy source has an unsupported release repository")
    installed_version = tartlab.get("installed_version")
    if _version(installed_version, "installed_version") < _version(
            direct["minimum_tartlab_version"], "minimum_tartlab_version"):
        raise ValueError(
            "legacy source is older than the v0.13 direct-migration floor; "
            "use the documented adult clean-provision/manual-restore path")
    return {
        "source_profile": source_profile,
        "installed_version": installed_version,
        "layout": layout,
        "minimum_tartlab_version": direct["minimum_tartlab_version"],
        "decision": policy["decision"],
    }


def check(policy_path: Path = DEFAULT_POLICY,
          backup: Path | None = None) -> dict[str, Any]:
    policy = _read_object(policy_path)
    validate_policy(policy)
    result: dict[str, Any] = {
        "profile": policy["profile"],
        "decision": policy["decision"],
        "source_profile": policy["direct_migration"]["source_profile"],
        "minimum_tartlab_version": policy["direct_migration"][
            "minimum_tartlab_version"],
        "below_floor_action": policy["below_floor"]["action"],
    }
    if backup is not None:
        result["source"] = validate_backup(
            backup.resolve(), policy_path=policy_path)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--backup", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(check(args.policy, args.backup), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
