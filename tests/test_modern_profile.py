"""Host checks for the published modern CI profile."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_modern_profile import (  # noqa: E402
    REQUIRED_DIST_FILES, check, distribution_inventory, validate_profile,
)


class ModernProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(
            (ROOT / "profiles/lvgl-modern.json").read_text(encoding="utf-8"))

    def test_checked_in_profile_has_an_isolated_published_release_path(self):
        result = check()
        self.assertEqual(result, {
            "profile": "lvgl-modern",
            "artifact_status": "published",
            "release_version": "modern-v0.14.8",
            "release_repository": "tdhoward/TartLab-modern-releases",
        })

    def test_profile_rejects_the_legacy_release_channel(self):
        profile = copy.deepcopy(self.profile)
        profile["release_channel"]["repository"] = "tdhoward/TartLab"
        with self.assertRaisesRegex(ValueError, "isolated repository"):
            validate_profile(profile)

    def test_published_profile_requires_the_exact_qualification(self):
        profile = copy.deepcopy(self.profile)
        profile["hardware_qualification"]["evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "qualification does not match"):
            validate_profile(profile)

    def test_unreleased_profile_cannot_claim_release_qualification(self):
        profile = copy.deepcopy(self.profile)
        profile["status"] = "promotion-gated-unreleased"
        with self.assertRaisesRegex(ValueError, "must not claim"):
            validate_profile(profile)

        profile["hardware_qualification"] = None
        validate_profile(profile)

    def test_profile_rejects_an_unpinned_adapter_change(self):
        profile = copy.deepcopy(self.profile)
        profile["application_adapter"]["inputs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "adapter hash mismatch"):
            validate_profile(profile)

    def test_distribution_requires_the_modern_adapter_and_compilable_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            for relative in REQUIRED_DIST_FILES:
                path = dist / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("pass\n", encoding="utf-8")
            inventory = distribution_inventory(dist)
            self.assertEqual(len(inventory), len(REQUIRED_DIST_FILES))

            (dist / "lib/tartlabutils/modern.py").unlink()
            with self.assertRaisesRegex(ValueError, "modern.py"):
                distribution_inventory(dist)


if __name__ == "__main__":
    unittest.main()
