"""Host checks for Phase 6 release authenticity and promotion policy."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_release_authenticity import (  # noqa: E402
    check, load_json, release_assets, validate_ci_identity, validate_policy,
    verification_command,
)
from build_modern_release import build_release as build_modern_release  # noqa: E402
from check_modern_release import (  # noqa: E402
    check as check_modern_release, validate_compatibility,
)
from check_modern_release_authenticity import (  # noqa: E402
    check as check_modern_authenticity,
    load_json as load_modern_policy,
    release_assets as modern_release_assets,
    validate_ci_identity as validate_modern_ci_identity,
    validate_policy as validate_modern_policy,
    verification_command as modern_verification_command,
)


class ReleaseAuthenticityTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_json(ROOT / "profiles/release-authenticity.json")

    def test_checked_in_policy_and_promotion_workflow_fail_closed(self):
        self.assertEqual(check(), {
            "mechanism": "github-artifact-attestation",
            "repository": "tdhoward/TartLab",
            "signer_workflow": (
                "tdhoward/TartLab/.github/workflows/promote-legacy-release.yml"),
            "on_device_enforcement": False,
        })

    def test_policy_rejects_a_moving_action_reference(self):
        policy = copy.deepcopy(self.policy)
        policy["action"]["commit"] = "v4"
        with self.assertRaisesRegex(ValueError, "full commit pin"):
            validate_policy(policy)

    def test_policy_does_not_claim_unimplemented_device_enforcement(self):
        policy = copy.deepcopy(self.policy)
        policy["scope"]["on_device_enforcement"] = True
        with self.assertRaisesRegex(ValueError, "on-device"):
            validate_policy(policy)

    def test_release_requires_all_authenticated_metadata_and_an_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary)
            for name in (
                    "manifest.json", "build_metadata.json", "checksums.json",
                    "promotion_attestation.json", "rootfiles.tar"):
                (release / name).write_text("{}\n", encoding="utf-8")
            self.assertEqual(len(release_assets(release, self.policy)), 5)

            (release / "promotion_attestation.json").unlink()
            with self.assertRaisesRegex(ValueError, "promotion_attestation"):
                release_assets(release, self.policy)

    def test_verification_pins_repository_workflow_predicate_and_tag(self):
        command = verification_command(
            Path("manifest.json"), self.policy,
            bundle=Path("release-attestation.sigstore.json"),
            source_ref="refs/tags/v1.2.3")
        self.assertIn("tdhoward/TartLab", command)
        self.assertIn(
            "tdhoward/TartLab/.github/workflows/promote-legacy-release.yml",
            command)
        self.assertIn("https://slsa.dev/provenance/v1", command)
        self.assertIn("--deny-self-hosted-runners", command)
        self.assertIn("refs/tags/v1.2.3", command)

    def test_keyless_identity_requires_the_exact_repository_tag_and_commit(self):
        identity = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "tdhoward/TartLab",
            "GITHUB_REF": "refs/tags/v1.2.3",
            "GITHUB_SHA": "a" * 40,
        }
        validate_ci_identity("v1.2.3", "a" * 40, identity)

        for field, value in (
                ("GITHUB_REPOSITORY", "attacker/TartLab"),
                ("GITHUB_REF", "refs/heads/main"),
                ("GITHUB_SHA", "b" * 40)):
            with self.subTest(field=field):
                changed = dict(identity)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    validate_ci_identity("v1.2.3", "a" * 40, changed)
        with self.assertRaisesRegex(ValueError, "stable"):
            validate_ci_identity("main", "a" * 40, identity)


class ModernReleaseTests(unittest.TestCase):
    firmware_sha256 = (
        "187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab")

    def _build(self, root: Path) -> tuple[Path, Path]:
        dist = root / "dist"
        dist.mkdir()
        (dist / "main.py").write_text("print('modern')\n", encoding="utf-8")
        packages = root / "packages.json"
        packages.write_text(json.dumps([{
            "name": "rootfiles",
            "source": "dist/*",
            "target": "/",
            "clear_first": False,
            "ownership": "system",
        }]), encoding="utf-8")
        release = root / "release"
        build_modern_release(
            dist, release, "modern-v1.2.3", packages_path=packages,
            source_epoch=1234, allow_dirty=True)
        return dist, release

    def test_modern_builder_uses_a_distinct_object_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            dist, release = self._build(Path(temporary))
            self.assertFalse((release / "manifest.json").exists())
            manifest = json.loads(
                (release / "modern-manifest.json").read_text(encoding="utf-8"))
            self.assertIsInstance(manifest, dict)
            self.assertEqual(manifest["schema"], 1)
            self.assertEqual(
                manifest["channel"]["repository"],
                "tdhoward/TartLab-modern-releases")
            result = check_modern_release(
                release, "lvgl-modern", self.firmware_sha256, dist=dist)
            self.assertFalse(result["mutation_performed"])
            self.assertEqual(result["packages"], 1)

    def test_provisioning_preflight_rejects_profile_and_firmware_mismatch(self):
        manifest = {
            "compatibility": {
                "runtime_profile": "lvgl-modern",
                "firmware": {"sha256": self.firmware_sha256},
            },
        }
        with self.assertRaisesRegex(ValueError, "Runtime profile mismatch"):
            validate_compatibility(
                manifest, "legacy-mp123", self.firmware_sha256)
        with self.assertRaisesRegex(ValueError, "Firmware identity mismatch"):
            validate_compatibility(manifest, "lvgl-modern", "0" * 64)

    def test_modern_builder_rejects_noncanonical_package_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "dist"
            dist.mkdir()
            (dist / "main.py").write_text("pass\n", encoding="utf-8")
            packages = root / "packages.json"
            packages.write_text(json.dumps([{
                "name": "escape",
                "source": "dist/*",
                "target": "/../device",
                "clear_first": True,
            }]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "target is unsafe"):
                build_modern_release(
                    dist, root / "release", "modern-v1.2.3",
                    packages_path=packages, source_epoch=1234,
                    allow_dirty=True)

    def test_modern_release_rejects_legacy_manifest_even_on_separate_feed(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, release = self._build(Path(temporary))
            (release / "manifest.json").write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy manifest"):
                check_modern_release(
                    release, "lvgl-modern", self.firmware_sha256)


class ModernReleaseAuthenticityTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_modern_policy(
            ROOT / "profiles/modern-release-authenticity.json")

    def test_checked_in_modern_policy_and_workflow_are_isolated(self):
        result = check_modern_authenticity()
        self.assertEqual(
            result["target_repository"],
            "tdhoward/TartLab-modern-releases")
        self.assertEqual(result["profile"], "lvgl-modern")

    def test_modern_policy_rejects_the_legacy_target(self):
        policy = copy.deepcopy(self.policy)
        policy["target_repository"] = "tdhoward/TartLab"
        with self.assertRaisesRegex(ValueError, "isolated repository"):
            validate_modern_policy(policy)

    def test_modern_keyless_identity_requires_source_tag_and_commit(self):
        identity = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "tdhoward/TartLab",
            "GITHUB_REF": "refs/tags/modern-v1.2.3",
            "GITHUB_SHA": "a" * 40,
        }
        validate_modern_ci_identity("modern-v1.2.3", "a" * 40, identity)
        changed = dict(identity)
        changed["GITHUB_REF"] = "refs/tags/v1.2.3"
        with self.assertRaisesRegex(ValueError, "GITHUB_REF"):
            validate_modern_ci_identity("modern-v1.2.3", "a" * 40, changed)

    def test_modern_authenticated_assets_require_modern_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary)
            for name in (
                    "modern-manifest.json", "build_metadata.json",
                    "checksums.json", "promotion_attestation.json",
                    "rootfiles.tar"):
                (release / name).write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                len(modern_release_assets(release, self.policy)), 5)
            (release / "manifest.json").write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy manifest"):
                modern_release_assets(release, self.policy)

    def test_modern_verification_pins_source_workflow_and_tag(self):
        command = modern_verification_command(
            Path("modern-manifest.json"), self.policy,
            bundle=Path("release-attestation.sigstore.json"),
            source_ref="refs/tags/modern-v1.2.3")
        self.assertIn("tdhoward/TartLab", command)
        self.assertIn(
            "tdhoward/TartLab/.github/workflows/promote-modern-release.yml",
            command)
        self.assertIn("refs/tags/modern-v1.2.3", command)
        self.assertIn("--deny-self-hosted-runners", command)


if __name__ == "__main__":
    unittest.main()
