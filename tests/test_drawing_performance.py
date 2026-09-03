import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from drawing_performance import (
    device_program, extract_result, render_report, validate_result)


def result(profile):
    implementations = {}
    if profile == "modern":
        definitions = (
            ("direct_canvas", "DirectCanvas", "landscape", 480, 222, 360, 180),
            ("portrait_canvas", "PortraitCanvas", "portrait", 222, 480, 180, 360),
        )
    else:
        definitions = (
            ("display_drv_landscape", "display_drv", "landscape", 480, 222, 360, 180),
            ("display_drv_portrait", "display_drv", "portrait", 222, 480, 180, 360),
        )
    for key, api, orientation, width, height, field_width, field_height in definitions:
        implementations[key] = {
            "api": api,
            "orientation": orientation,
            "logical_width": width,
            "logical_height": height,
            "field_width": field_width,
            "field_height": field_height,
            "full_grid_us": [10_000, 12_000, 11_000],
            "piece_move_us": [1_000, 1_200, 1_100],
            "text_redraw_us": [2_000, 2_200, 2_100],
        }
    return {
        "schema": 1,
        "profile": profile,
        "matrix": {
            "samples": 3,
            "frame_counts": {
                "full_grid": 1, "piece_move": 30, "text_redraw": 10},
            "block_size": 18,
            "blocks_per_grid": 200,
            "colors": "black-and-white-rgb565-byte-order-invariant",
        },
        "implementations": implementations,
        "collection": {"collected_at": "2026-09-02T00:00:00+00:00"},
    }


class DrawingPerformanceTests(unittest.TestCase):
    def test_help_trees_do_not_publish_benchmark_apps(self):
        for help_tree in ("help", "help-legacy"):
            root = ROOT / "src/files" / help_tree
            manifest = (root / "manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("drawing_performance", manifest)
            self.assertFalse((root / "drawing_performance_landscape.py").exists())
            self.assertFalse((root / "drawing_performance_portrait.py").exists())

    def test_device_program_is_micropython_compatible_source(self):
        source = device_program("modern", 7)
        compile(source, "<drawing-performance>", "exec")
        self.assertIn("PROFILE = 'modern'", source)
        self.assertIn("SAMPLES = 7", source)
        self.assertIn("working_modern_app.__dict__", source)
        self.assertNotIn("__MODERN_APP_SOURCE__", source)

    def test_device_program_rejects_too_few_samples(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            device_program("legacy", 2)

    def test_extract_and_validate_result(self):
        expected = result("modern")
        output = b"noise\r\nDRAWING_PERFORMANCE=" + json.dumps(expected).encode()
        actual = extract_result(output)
        validate_result(actual, "modern")
        self.assertEqual(actual, expected)

    def test_validation_rejects_wrong_connected_profile(self):
        with self.assertRaisesRegex(ValueError, "expected legacy"):
            validate_result(result("modern"), "legacy")

    def test_report_has_four_simple_rows(self):
        modern = result("modern")
        modern["collection"]["modern_app_source"] = "working_tree_in_memory"
        report = render_report(modern, result("legacy"))
        self.assertIn("| display_drv | Landscape | 11.00 | 1.10 | 2.10 |", report)
        self.assertIn("| DirectCanvas | Landscape | 11.00 | 1.10 | 2.10 |", report)
        self.assertIn("| PortraitCanvas | Portrait | 11.00 | 1.10 | 2.10 |", report)
        self.assertIn("Modern app source: `working_tree_in_memory`", report)
        self.assertNotIn("pending device swap", report)

    def test_report_marks_legacy_pending(self):
        report = render_report(result("modern"))
        self.assertEqual(report.count("pending device swap"), 7)


if __name__ == "__main__":
    unittest.main()
