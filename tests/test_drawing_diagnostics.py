import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from drawing_diagnostics import (
    SHAPES, STAGE_CASES, TEXT_VARIANTS, device_program, extract_result,
    render_section, validate_result)


def result():
    samples = 3
    stages = {}
    for case in STAGE_CASES:
        stages[case] = {
            "render_us": [1000, 1100, 1200],
            "pack_and_loop_us": [100, 110, 120],
            "submit_us": [200, 210, 220],
            "wait_us": [300, 310, 320],
            "show_us": [600, 630, 660],
            "total_us": [1600, 1730, 1860],
            "transfers": [3, 3, 3],
        }
    shapes = {}
    dimensions = ((144, 36), (72, 72), (36, 144))
    for key, (width, height) in zip(SHAPES, dimensions):
        shapes[key] = {
            "width": width,
            "height": height,
            "bytes": 10_368,
            "tiled_total_us": [6000, 6300, 6600],
            "tiled_pack_us": [100, 110, 120],
            "tiled_submit_us": [200, 210, 220],
            "tiled_wait_us": [5700, 5980, 6260],
            "tiled_transfers": [3, 3, 3],
            "raw_total_us": [2000, 2100, 2200],
            "raw_submit_us": [200, 210, 220],
            "raw_wait_us": [1800, 1890, 1980],
            "raw_transfers": [1, 1, 1],
        }
    return {
        "schema": 1,
        "profile": "modern",
        "matrix": {
            "samples": samples,
            "transfer_rows": 16,
            "equal_area_bytes": 10_368,
            "text_width": 144,
            "text_height": 36,
        },
        "stages": stages,
        "shapes": shapes,
        "text_rendering": {
            key: [1000, 1100, 1200] for key in TEXT_VARIANTS},
        "lifecycle": {
            "iterations": 10,
            "allocation_balance": 0,
            "heap_free": [100_000] * 10,
            "final_owner": "ui",
            "transfer_pending": False,
        },
        "collection": {"collected_at": "2026-09-02T00:00:00+00:00"},
    }


class DrawingDiagnosticTests(unittest.TestCase):
    def test_program_is_micropython_compatible_source(self):
        source = device_program(7)
        compile(source, "<drawing-diagnostics>", "exec")
        self.assertIn("SAMPLES = 7", source)
        self.assertNotIn("__SAMPLES__", source)
        self.assertIn("working_modern_app.__dict__", source)
        self.assertNotIn("__MODERN_APP_SOURCE__", source)

    def test_program_rejects_too_few_samples(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            device_program(2)

    def test_extract_validate_and_render(self):
        expected = result()
        output = b"noise\r\nDRAWING_DIAGNOSTICS=" + json.dumps(expected).encode()
        actual = extract_result(output)
        validate_result(actual)
        report = render_section(actual)
        self.assertIn("| DirectCanvas piece | 1.10", report)
        self.assertIn("| 144 x 36 | 3 | 6.30 | 2.10 | 3.0x |", report)
        self.assertIn("15,360-byte bounce buffer", report)
        self.assertIn("PortraitCanvas cached sprite", report)
        self.assertIn("allocation balance 0", report)

    def test_validation_rejects_changed_matrix(self):
        value = result()
        value["matrix"]["transfer_rows"] = 24
        with self.assertRaisesRegex(ValueError, "matrix differs"):
            validate_result(value)


if __name__ == "__main__":
    unittest.main()
