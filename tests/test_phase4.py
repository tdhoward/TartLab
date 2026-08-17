import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pydevices_inventory import check_inventory, distribution_paths
from pydevices_upstream import check_upstream_mapping, validate_mapping
from vendor_pydevices import (
    apply_patch_manifest,
    audit_runtime_imports,
    check_vendor_lock,
    validate_vendor_lock,
)


class PyDevicesImportInventoryTests(unittest.TestCase):
    def test_reviewed_static_inventory_matches_source_and_vendor_lock(self):
        inventory = check_inventory()
        categories = inventory["categories"]

        self.assertIn("graphics/__init__.py", categories["core_startup_ide"]["files"])
        board = categories["t_display_s3_pro_adapter"]["files"]
        self.assertIn("board_configs/t_display_s3_pro/board_config.py", board)
        self.assertIn("bus_drv/spibus.py", board)
        self.assertIn("display_drv/st7796.py", board)
        self.assertIn("touch_drv/cst226.py", board)
        examples = categories["shipped_examples"]["files"]
        self.assertIn("add_ons/displaybuf.py", examples)
        self.assertIn("add_ons/qoi_reader.py", examples)
        self.assertIn("eventsys/keys.py", examples)

    def test_every_locked_file_has_exactly_one_payload_classification(self):
        inventory = json.loads(
            (ROOT / "vendor/legacy-pydevices.imports.json").read_text())
        classified = list(inventory["retained_unreachable_files"])
        for category in inventory["categories"].values():
            classified.extend(category["files"])
        self.assertEqual(len(classified), len(set(classified)))

        lock = json.loads(
            (ROOT / "vendor/legacy-pydevices.lock.json").read_text())
        self.assertEqual(set(classified), {item["path"] for item in lock["files"]})

    def test_generated_distribution_must_match_reviewed_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp) / "dist"
            target = dist / "lib/pydevices"
            shutil.copytree(ROOT / "src/lib/pydevices", target)
            check_inventory(dist=dist)

            unreviewed = target / "unreviewed_driver.py"
            unreviewed.write_text("VALUE = 1\n")
            with self.assertRaisesRegex(
                    ValueError, "unexpected=.*unreviewed_driver.py"):
                check_inventory(dist=dist)

    def test_distribution_inventory_ignores_host_cache_files(self):
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp) / "dist"
            root = dist / "lib/pydevices"
            (root / "__pycache__").mkdir(parents=True)
            (root / "driver.py").write_text("VALUE = 1\n")
            (root / "__pycache__/driver.pyc").write_bytes(b"cache")
            self.assertEqual(distribution_paths(dist), {"driver.py"})


class PyDevicesUpstreamMappingTests(unittest.TestCase):
    def test_mapping_covers_every_reachable_file_at_reviewed_pins(self):
        mapping = check_upstream_mapping()
        self.assertEqual(mapping["summary"], {
            "drop_in_compatible_files": 0,
            "mapped_files": 38,
            "pinned_repositories": 4,
            "reviewed_reachable_files": 39,
            "without_current_equivalent": 1,
        })

        entries = {entry["local_path"]: entry
                   for entry in mapping["mappings"]}
        board = entries["board_configs/t_display_s3_pro/board_config.py"]
        self.assertEqual(board["upstream"], [{
            "path": (
                "board_configs/busdisplay/spi/t-display-s3-pro/"
                "board_config.py"),
            "repository": "pydevices",
        }])
        qoi = entries["add_ons/qoi_reader.py"]
        self.assertEqual(qoi["relationship"], "no_current_equivalent")
        self.assertEqual(qoi["upstream"], [])
        self.assertTrue(all(
            entry["drop_in_compatible"] is False
            for entry in mapping["mappings"]))

    def test_mapping_rejects_duplicate_local_classification(self):
        mapping = check_upstream_mapping()
        invalid = copy.deepcopy(mapping)
        invalid["mappings"].append(copy.deepcopy(invalid["mappings"][0]))
        inventory = json.loads(
            (ROOT / "vendor/legacy-pydevices.imports.json").read_text())
        with self.assertRaisesRegex(ValueError, "duplicate local paths"):
            validate_mapping(invalid, inventory)


class PyDevicesCandidatePipelineTests(unittest.TestCase):
    def test_candidate_lock_is_explicit_and_not_promotion_approved(self):
        lock = check_vendor_lock()
        self.assertEqual(lock["promotion_status"], "research-only")
        self.assertEqual(lock["summary"], {
            "dependency_files": 18,
            "mapped_equivalent_sources": 47,
            "patch_files": 0,
            "pinned_repositories": 4,
            "selected_source_files": 65,
        })
        destinations = {item["destination"] for item in lock["files"]}
        self.assertIn("board_config.py", destinations)
        self.assertIn("board_peripherals.py", destinations)
        self.assertNotIn("qoi_reader.py", destinations)

    def test_candidate_lock_rejects_missing_audited_source(self):
        lock = check_vendor_lock()
        invalid = copy.deepcopy(lock)
        invalid["files"].pop(0)
        invalid["summary"]["mapped_equivalent_sources"] -= 1
        invalid["summary"]["selected_source_files"] -= 1
        mapping = check_upstream_mapping()
        with self.assertRaisesRegex(
                ValueError, "mapped-equivalent coverage mismatch"):
            validate_vendor_lock(invalid, mapping)

    def test_runtime_import_audit_rejects_unapproved_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / "module.py").write_text("import unreviewed_dependency\n")
            with self.assertRaisesRegex(
                    ValueError, "external import allowlist mismatch"):
                audit_runtime_imports(runtime, [], [])

    def test_patch_manifest_requires_exact_preimage_and_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            runtime.mkdir()
            target = runtime / "module.py"
            before = b"VALUE = 1\n"
            after = b"VALUE = 2\n"
            target.write_bytes(before)
            patch = {
                "operations": [{
                    "after_sha256": hashlib.sha256(after).hexdigest(),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "path": "module.py",
                    "replacements": [{
                        "count": 1,
                        "new": "VALUE = 2",
                        "old": "VALUE = 1",
                    }],
                }],
                "schema": 1,
            }
            patch_path = root / "compat.patch.json"
            patch_path.write_text(json.dumps(patch))
            apply_patch_manifest(patch_path, runtime, {"module.py"})
            self.assertEqual(target.read_bytes(), after)
            with self.assertRaisesRegex(ValueError, "preimage mismatch"):
                apply_patch_manifest(patch_path, runtime, {"module.py"})


if __name__ == "__main__":
    unittest.main()
