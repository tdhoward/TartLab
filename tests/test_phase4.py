import copy
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


if __name__ == "__main__":
    unittest.main()
