"""Check real modern adapter imports and their filesystem package ownership."""

import importlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class DriverPackageTests(unittest.TestCase):
    def test_board_adapter_references_import_from_the_real_package_lazily(self):
        package = types.ModuleType("tartlabutils")
        package.__path__ = [str(ROOT / "src/lib/tartlabutils")]
        with patch.object(sys, "path", [str(ROOT / "src/lib")] + sys.path), \
                patch.dict(sys.modules, {"tartlabutils": package,
                                         "tartlabutils._emitters": None}):
            for name in tuple(sys.modules):
                if name == "tartlabdrivers" or name.startswith("tartlabdrivers."):
                    sys.modules.pop(name)
            importlib.import_module("tartlabdrivers")
            self.assertNotIn("tartlabdrivers.display.st7796", sys.modules)
            self.assertNotIn("tartlabdrivers.display.st77922", sys.modules)
            references = set()
            for path in sorted((ROOT / "boards").glob("*/runtime/*.py")):
                scope = {}
                exec(compile(path.read_bytes(), str(path), "exec"), scope)
                reference = scope["BOARD_CONFIG"]["display"]["adapter"]
                references.add(reference)
                adapter = __import__(reference, None, None, ("*",))
                self.assertTrue(callable(adapter.create_controller))
                self.assertTrue(callable(adapter.Platform))
                self.assertTrue(Path(adapter.__file__).is_relative_to(
                    ROOT / "src/lib/tartlabdrivers/display"))
            self.assertEqual(references, {"tartlabdrivers.display.st7796",
                                          "tartlabdrivers.display.st77922"})

    def test_modern_package_owns_the_complete_driver_tree(self):
        packages = json.loads((ROOT / "modern_packages.json").read_text())
        self.assertEqual([p for p in packages if p["name"] == "tartlabdrivers"], [{
            "name": "tartlabdrivers", "source": "dist/lib/tartlabdrivers",
            "target": "/lib/tartlabdrivers", "clear_first": True,
            "ownership": "system",
        }])
        legacy = json.loads((ROOT / "tartlab_packages.json").read_text())
        self.assertFalse(any("tartlabdrivers" in p["source"] for p in legacy))


if __name__ == "__main__":
    unittest.main()
