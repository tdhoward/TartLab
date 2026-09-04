import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "damage", ROOT / "src/lib/tartlabutils/damage.py")
DAMAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DAMAGE)


class DamageTrackerTests(unittest.TestCase):
    def test_clips_regions_and_ignores_empty_or_invisible_ones(self):
        tracker = DAMAGE.DamageTracker((10, 20, 30, 40))

        self.assertTrue(tracker.add((5, 15, 10, 10)))
        self.assertFalse(tracker.add((0, 0, 2, 2)))
        self.assertFalse(tracker.add((12, 22, 0, 3)))

        self.assertEqual(tracker.count, 1)
        self.assertEqual(tracker.area(0), [10, 20, 5, 5])

    def test_merges_overlap_and_cost_effective_neighbors_only(self):
        tracker = DAMAGE.DamageTracker(
            (0, 0, 100, 100), merge_overhead=10)

        tracker.add((0, 0, 10, 10))
        tracker.add((8, 0, 10, 10))
        tracker.add((40, 40, 3, 3))

        self.assertEqual(tracker.count, 2)
        self.assertIn([0, 0, 18, 10], tracker._regions[:tracker.count])
        self.assertIn([40, 40, 3, 3], tracker._regions[:tracker.count])

    def test_capacity_uses_least_expensive_union_and_stays_bounded(self):
        tracker = DAMAGE.DamageTracker(
            (0, 0, 100, 100), capacity=2, merge_overhead=0)

        tracker.add((0, 0, 2, 2))
        tracker.add((90, 90, 2, 2))
        tracker.add((4, 0, 2, 2))

        self.assertEqual(tracker.count, 2)
        self.assertEqual(tracker.pixel_count, 16)
        self.assertIn([0, 0, 6, 2], tracker._regions[:tracker.count])

    def test_clear_reuses_preallocated_region_objects(self):
        tracker = DAMAGE.DamageTracker((0, 0, 20, 20), capacity=2)
        storage = tracker._regions
        slots = tuple(map(id, storage))
        tracker.add((1, 1, 2, 2))

        tracker.clear()
        tracker.add((5, 5, 2, 2))

        self.assertIs(tracker._regions, storage)
        self.assertEqual(tuple(map(id, tracker._regions)), slots)
        self.assertEqual(tracker.area(0), [5, 5, 2, 2])


if __name__ == "__main__":
    unittest.main()
