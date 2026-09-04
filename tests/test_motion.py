import importlib.util
from pathlib import Path
import unittest

from tests.test_timing import FakeTime, make_clock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "motion", ROOT / "src/lib/tartlabutils/motion.py")
MOTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOTION)

StagedMotion = MOTION.StagedMotion


class StagedMotionTests(unittest.TestCase):
    def test_starting_speed_advances_four_units_per_normal_frame(self):
        motion = StagedMotion(((0, 80), (1200, 120)), 4)

        deltas = [motion.advance(50) for unused in range(20)]

        self.assertEqual(deltas, [4] * 20)
        self.assertEqual(motion.distance, 80)
        self.assertEqual(motion.stage, 0)

    def test_speed_stage_changes_distance_without_changing_update_period(self):
        motion = StagedMotion(((0, 80), (20, 120)), 4)

        slow = [motion.advance(50) for unused in range(5)]
        fast = [motion.advance(50) for unused in range(4)]

        self.assertEqual(slow, [4, 4, 4, 4, 4])
        self.assertEqual(fast, [4, 8, 4, 8])
        self.assertEqual(motion.speed_per_second, 120)
        self.assertEqual(motion.distance, 44)

    def test_equal_simulated_time_is_independent_of_render_work(self):
        def simulate(render_ms):
            fake = FakeTime()
            clock = make_clock(fake)
            motion = StagedMotion(((0, 80), (40, 120)), 4)
            updates_run = 0
            emitted_units = 0
            wrapped_phase = 0
            next_checkpoint = 16
            checkpoints = []
            while updates_run < 20:
                updates = clock.updates_due()
                for unused in range(updates):
                    delta = motion.advance(clock.update_ms)
                    emitted_units += delta
                    wrapped_phase = (wrapped_phase + delta) % 48
                    updates_run += 1
                    if motion.distance >= next_checkpoint:
                        checkpoints.append(next_checkpoint)
                        next_checkpoint += 16
                if updates:
                    fake.advance(render_ms)
                clock.pace()
            return (motion.distance_milliunits, emitted_units, wrapped_phase,
                    tuple(checkpoints))

        self.assertEqual(simulate(5), simulate(42))

    def test_carries_fractional_and_sub_quantum_distance(self):
        motion = StagedMotion(((0, 15),), 4)

        self.assertEqual([motion.advance(50) for unused in range(5)],
                         [0, 0, 0, 0, 0])
        self.assertEqual(motion.advance(50), 4)
        self.assertEqual(motion.distance, 4)

    def test_uses_caller_defined_units(self):
        motion = StagedMotion(((0, 10),), 1)

        self.assertEqual(motion.advance(250), 2)
        self.assertEqual(motion.distance_milliunits, 2500)
        self.assertEqual(motion.distance, 2)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            StagedMotion(())
        with self.assertRaises(ValueError):
            StagedMotion(((1, 80),))
        with self.assertRaises(ValueError):
            StagedMotion(((0, 80), (0, 120)))
        with self.assertRaises(ValueError):
            StagedMotion(((0, 0),))
        with self.assertRaises(ValueError):
            StagedMotion(((0, 80),), 0)
        with self.assertRaises(ValueError):
            StagedMotion(((0, 80),)).advance(-1)


if __name__ == "__main__":
    unittest.main()
