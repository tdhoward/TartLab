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


if __name__ == "__main__":
    unittest.main()
