"""Coverage and observation boundaries for repeatable device work."""

import ast
import configparser
import gzip
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.grid_puzzle_support import ENGINE as g
from tools import grid_puzzle_benchmark as b


class BenchmarkTests(unittest.TestCase):
    def test_workload_matrix_keeps_all_rooms_and_extreme_occupancy(self):
        pack = g.validate_level_pack(b.workloads())
        self.assertEqual(len(pack["levels"]), 11)
        moving = next(d for d in pack["levels"] if d["name"] == "Stress moving spiders")
        dense = next(d for d in pack["levels"] if d["name"] == "Stress dense explosions")
        self.assertGreaterEqual(sum(a[0] == g.SPIDER for a in moving["actors"]), 79)
        self.assertEqual(sum(a[0] == g.SPIDER for a in dense["actors"]), 190)
        spears = next(d for d in pack["levels"] if "long spears" in d["name"])
        self.assertEqual({a[2] for a in spears["actors"] if a[0] == g.EMITTER}, set(range(4)))
        self.assertEqual(b.workloads(), b.workloads())
        ast.parse(b.SETUP)

    def test_missing_coverage_and_missed_or_dropped_time_cannot_pass(self):
        normal = {"debug": False, "frame_work_us": {"max": 40000},
                  "dropped_update_ms": 0, "missed_deadlines": 0}
        debug = {**normal, "debug": True}
        self.assertEqual(b.performance_status({"normal": normal}, 2, 50), "pending")
        self.assertEqual(b.performance_status({"normal": normal, "debug": debug}, 2, 50), "passed")
        for field, value in (("dropped_update_ms", 10), ("missed_deadlines", 1),
                             ("frame_work_us", {"max": 51000})):
            result = {**normal, field: value}
            self.assertEqual(b.performance_status({"normal": result, "debug": debug}, 2, 50), "failed")

    def test_form_requires_actual_observations_and_retains_edits_on_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            b.write_json(output / "report.json", {"binding": "build-a", "results": {},
                         "expected_results": 22, "performance": "failed"})
            b.make_form(output, "build-a")
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(b.status(output), 1)
            self.assertIn("controls: pending", stream.getvalue())
            form = configparser.ConfigParser(interpolation=None)
            form.read(output / "operator.ini")
            form["session"]["observer"] = "Test observer"
            form["session"]["observed_at_utc"] = "yesterday"
            form["check:controls"]["status"] = "passed"
            with (output / "operator.ini").open("w") as f:
                form.write(f)
            original = (output / "operator.ini").read_bytes()
            b.make_form(output, "build-a")
            self.assertEqual((output / "operator.ini").read_bytes(), original)
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(b.status(output), 1)
            self.assertIn("UTC", stream.getvalue())
            self.assertIn("observation notes required", stream.getvalue())
            form["session"]["binding"] = "old-build"
            with (output / "operator.ini").open("w") as f:
                form.write(f)
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(b.status(output), 1)
            self.assertIn("different build", stream.getvalue())

    def test_install_manifest_preserves_existing_help_and_is_idempotent(self):
        original = {"help_system_version": 1, "folders": [
            {"folder name": "Examples", "entries": [{"file": "custom.py", "title": "Custom"}]}]}
        merged = b.merge_manifest(json.dumps(original).encode())
        self.assertEqual(b.merge_manifest(merged), merged)
        entries = json.loads(merged)["folders"][0]["entries"]
        self.assertEqual(sum(e["file"].startswith("grid_puzzle") for e in entries), 3)
        self.assertIn(original["folders"][0]["entries"][0], entries)

    def test_install_builds_and_packages_fresh_ide_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            web = root / "src/ide/www"
            dist = web / "dist"
            dist.mkdir(parents=True)
            (dist / "bundle.js").write_text("stale editor")
            def build(command, **kwargs):
                self.assertEqual(command[-2:], ["run", "build"])
                self.assertEqual(kwargs["cwd"], web)
                self.assertTrue(kwargs["check"])
                (dist / "bundle.js").write_text("JSON editor " * 300)
                (dist / "index.html").write_text('<script src="bundle.js"></script>')
                (dist / "img").mkdir()
                (dist / "img/logo.svg").write_text("<svg/>")
            with patch.object(b, "ROOT", root), patch("subprocess.run", side_effect=build) as run, \
                    patch("makedist.source_date_epoch", return_value=0), \
                    patch("makedist.npm_executable", return_value="npm"):
                payloads = b.build_ide_payloads(root)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(gzip.decompress(payloads["/ide/www/bundle.js.gz"]), b"JSON editor " * 300)
            self.assertIn("/ide/www/index.html", payloads)
            self.assertIn("/ide/www/img/logo.svg", payloads)
            self.assertNotIn("/ide/www/bundle.js", payloads)


if __name__ == "__main__":
    unittest.main()
