"""Host checks for Phase 6 release authenticity and promotion policy."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
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
from check_modern_qualification import (  # noqa: E402
    REQUIRED_GATES, check as check_modern_qualification,
    validate as validate_modern_qualification,
)
from check_modern_support_window import (  # noqa: E402
    check as check_support_window, validate_backup as validate_support_backup,
    validate_policy as validate_support_policy,
)
from release_utils import sha256_file, sha256_source_file  # noqa: E402


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
            firmware = manifest["published_assets"]["firmware"]
            self.assertEqual(firmware["file_name"], "tartlab-modern-v1.2.3.bin")
            self.assertEqual(firmware["sha256"], self.firmware_sha256)
            self.assertTrue((release / firmware["file_name"]).is_file())
            self.assertEqual(
                json.loads((release / "compatibility.json").read_text(
                    encoding="utf-8"))["firmware"], firmware)
            self.assertIn(
                "promotion-gated-unreleased",
                (release / "MIGRATION.md").read_text(encoding="utf-8"))
            result = check_modern_release(
                release, "lvgl-modern", self.firmware_sha256, dist=dist)
            self.assertFalse(result["mutation_performed"])
            self.assertEqual(result["packages"], 1)
            self.assertEqual(result["published_provenance_assets"], 3)
            self.assertEqual(result["support_window_floor"], "v0.13")
            support_window = json.loads(
                (release / "support-window.json").read_text(encoding="utf-8"))
            self.assertEqual(
                support_window["direct_migration"]["minimum_tartlab_version"],
                "v0.13")

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

    def test_modern_release_rejects_tampered_published_firmware(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, release = self._build(Path(temporary))
            firmware = release / "tartlab-modern-v1.2.3.bin"
            with firmware.open("ab") as stream:
                stream.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
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
                    "rootfiles.tar", "compatibility.json",
                    "firmware-build-lock.json", "firmware-provenance.json",
                    "filesystem-vendor-lock.json", "support-window.json",
                    "MIGRATION.md",
                    "tartlab-modern-v1.2.3.bin"):
                (release / name).write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                len(modern_release_assets(release, self.policy)), 12)
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


class ModernQualificationTests(unittest.TestCase):
    candidate_sha256 = "a" * 64
    firmware_sha256 = (
        "187a04dc9c74be161aa46d8b8f76ff64cb7eb4305b15c6d416e5fef471c7f2ab")

    def _evidence(self):
        return {
            "schema": 1,
            "profile": "lvgl-modern",
            "version": "modern-v1.2.3",
            "target_repository": "tdhoward/TartLab-modern-releases",
            "candidate_checksums_sha256": self.candidate_sha256,
            "firmware_sha256": self.firmware_sha256,
            "board": {
                "model": "LilyGO T-Display-S3 Pro",
                "pcb_revision": "1.1",
                "chip_revision": "v0.2",
                "flash_size_bytes": 16777216,
                "psram_size_bytes": 8388608,
            },
            "operator": "sanitized-operator-id",
            "tested_at_utc": "2026-08-26T20:00:00Z",
            "artifacts": {
                "clean_provisioning_journal_sha256": "b" * 64,
                "migration_provisioning_journal_sha256": "c" * 64,
                "serial_log_sha256": "d" * 64,
                "support_window_policy_sha256": sha256_source_file(
                    ROOT / "profiles/modern-support-window.json"),
            },
            "gates": {
                name: {"status": "passed", "evidence": ["record:" + name]}
                for name in REQUIRED_GATES
            },
        }

    def test_complete_candidate_bound_qualification_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "qualification.json"
            path.write_text(
                json.dumps(self._evidence(), sort_keys=True) + "\n",
                encoding="utf-8")
            result = check_modern_qualification(
                path, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256,
                expected_sha256=sha256_file(path))
            self.assertEqual(result["passed_gates"], list(REQUIRED_GATES))

    def test_qualification_rejects_missing_or_failed_gate(self):
        missing = self._evidence()
        missing["gates"].pop("recovery")
        with self.assertRaisesRegex(ValueError, "missing=.*recovery"):
            validate_modern_qualification(
                missing, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256)

        failed = self._evidence()
        failed["gates"]["ota"]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "ota has not passed"):
            validate_modern_qualification(
                failed, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256)

    def test_qualification_rejects_candidate_or_channel_mismatch(self):
        wrong_candidate = self._evidence()
        wrong_candidate["candidate_checksums_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "different candidate"):
            validate_modern_qualification(
                wrong_candidate, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256)

        wrong_feed = self._evidence()
        wrong_feed["target_repository"] = "tdhoward/TartLab"
        with self.assertRaisesRegex(ValueError, "wrong repository"):
            validate_modern_qualification(
                wrong_feed, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256)

    def test_qualification_rejects_a_different_support_window(self):
        evidence = self._evidence()
        evidence["artifacts"]["support_window_policy_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "different support-window"):
            validate_modern_qualification(
                evidence, tag="modern-v1.2.3",
                candidate_sha256=self.candidate_sha256)


class ModernSupportWindowTests(unittest.TestCase):
    def test_checked_in_policy_approves_v013_as_the_floor(self):
        result = check_support_window(
            backup=ROOT / "tests/fixtures/legacy_mp123/layout")
        self.assertEqual(result["minimum_tartlab_version"], "v0.13")
        self.assertEqual(result["source"]["installed_version"], "v0.13")
        self.assertEqual(result["source"]["layout"], "legacy-root-v1")

    def test_policy_rejects_a_weakened_floor_or_automatic_old_migration(self):
        policy = json.loads((
            ROOT / "profiles/modern-support-window.json").read_text(
                encoding="utf-8"))
        weakened = copy.deepcopy(policy)
        weakened["direct_migration"]["minimum_tartlab_version"] = "v0.1"
        with self.assertRaisesRegex(ValueError, "minimum_tartlab_version"):
            validate_support_policy(weakened)
        automatic = copy.deepcopy(policy)
        automatic["below_floor"]["automatic_migration_allowed"] = True
        with self.assertRaisesRegex(ValueError, "below-floor"):
            validate_support_policy(automatic)

    def test_source_below_floor_is_rejected_before_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            backup = Path(temporary) / "backup"
            shutil.copytree(
                ROOT / "tests/fixtures/legacy_mp123/layout", backup)
            repos_path = backup / "repos.json"
            repos = json.loads(repos_path.read_text(encoding="utf-8"))
            repos["list"][0]["installed_version"] = "v0.12"
            repos_path.write_text(json.dumps(repos), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "older than the v0.13"):
                validate_support_backup(backup)

    def test_prerelease_and_unrecognized_layout_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prerelease = root / "prerelease"
            shutil.copytree(
                ROOT / "tests/fixtures/legacy_mp123/layout", prerelease)
            repos_path = prerelease / "repos.json"
            repos = json.loads(repos_path.read_text(encoding="utf-8"))
            repos["list"][0]["installed_version"] = "v0.13-alpha"
            repos_path.write_text(json.dumps(repos), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stable TartLab version"):
                validate_support_backup(prerelease)

            unknown = root / "unknown"
            shutil.copytree(
                ROOT / "tests/fixtures/legacy_mp123/layout", unknown)
            (unknown / "state").mkdir()
            shutil.move(unknown / "repos.json", unknown / "state/repos.json")
            with self.assertRaisesRegex(ValueError, "outside the supported"):
                validate_support_backup(unknown)


if __name__ == "__main__":
    unittest.main()
