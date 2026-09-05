import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from racer_benchmark import MARKER, device_program, extract_result  # noqa: E402


class RacerBenchmarkTests(unittest.TestCase):
    def test_program_is_bounded_and_does_not_write_the_device(self):
        source = device_program(5)

        compile(source, "<racer-benchmark>", "exec")
        self.assertIn("SAMPLES = 5", source)
        self.assertIn("for sample in range(SAMPLES)", source)
        self.assertIn("FrameClock", source)
        self.assertIn("DirtyRegionAnimator", source)
        self.assertIn("ScanoutAnimator", source)
        self.assertIn("RoadBandCache", source)
        self.assertIn("ENTITY_COUNTS = (0, 3, 8, 16)", source)
        self.assertIn("SPEEDS = (80, 120)", source)
        self.assertIn("ENTITY_PROFILES = ('road-relative', 'mixed-movement')", source)
        self.assertIn("self.requires_full_frame_seed = getattr(", source)
        self.assertIn("def shadow_valid(self):", source)
        self.assertIn("def wait_for_frame_sync(self, timeout_ms=30):", source)
        self.assertIn("'frame_sync_us': summary(frame_sync_values)", source)
        self.assertNotIn("__MODERN_APP_SOURCE__", source)
        self.assertNotIn("__DAMAGE_SOURCE__", source)
        self.assertNotIn("__TIMING_SOURCE__", source)
        self.assertNotIn("__MOTION_SOURCE__", source)
        self.assertNotIn("__RACER_SOURCE__", source)
        self.assertNotIn("machine.reset", source)
        self.assertNotIn("open(", source)

    def test_rejects_too_few_samples(self):
        with self.assertRaises(ValueError):
            device_program(2)

    def test_rejects_invalid_entity_counts(self):
        with self.assertRaises(ValueError):
            device_program(3, ())
        with self.assertRaises(ValueError):
            device_program(3, (1, -1))

    def test_extract_result(self):
        expected = {
            "samples": 12,
            "target_frame_ms": 50,
            "work_deadline_misses": 0,
        }
        output = ("noise\r\n" + MARKER + json.dumps(expected) + "\r\n").encode()

        self.assertEqual(extract_result(output), expected)


if __name__ == "__main__":
    unittest.main()
