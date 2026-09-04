import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "timing", ROOT / "src/lib/tartlabutils/timing.py")
TIMING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TIMING)

FrameClock = TIMING.FrameClock


class FakeTime:
    def __init__(self, modulus=None, sleep_overshoot=0):
        self.absolute_ms = 0
        self.modulus = modulus
        self.sleep_overshoot = sleep_overshoot
        self.sleeps = []

    def ticks_ms(self):
        if self.modulus is None:
            return self.absolute_ms
        return self.absolute_ms % self.modulus

    def ticks_add(self, value, delta):
        result = value + delta
        if self.modulus is not None:
            result %= self.modulus
        return result

    def ticks_diff(self, new, old):
        if self.modulus is None:
            return new - old
        half = self.modulus // 2
        return (new - old + half) % self.modulus - half

    def sleep_ms(self, milliseconds):
        self.sleeps.append(milliseconds)
        self.absolute_ms += milliseconds + self.sleep_overshoot

    def advance(self, milliseconds):
        self.absolute_ms += milliseconds


def make_clock(fake, frame_ms=50, update_ms=50, max_updates=2):
    return FrameClock(
        frame_ms, update_ms, max_updates,
        ticks_ms=fake.ticks_ms,
        ticks_diff=fake.ticks_diff,
        ticks_add=fake.ticks_add,
        sleep_ms=fake.sleep_ms)


class FrameClockTests(unittest.TestCase):
    def test_sleeps_only_for_remaining_frame_budget(self):
        fake = FakeTime()
        clock = make_clock(fake)

        self.assertEqual(clock.updates_due(), 0)
        self.assertEqual(clock.pace(), 50)
        self.assertEqual(clock.updates_due(), 1)

        fake.advance(17)
        self.assertEqual(clock.pace(), 33)
        self.assertEqual(fake.sleeps, [50, 33])
        self.assertEqual(clock.missed_deadlines, 0)

    def test_caps_catch_up_and_records_dropped_simulation_time(self):
        fake = FakeTime()
        clock = make_clock(fake)
        fake.advance(180)

        self.assertEqual(clock.updates_due(), 2)
        self.assertEqual(clock.dropped_update_ms, 50)
        self.assertEqual(clock.updates_due(), 0)

    def test_reports_late_deadline_without_adding_a_full_delay(self):
        fake = FakeTime()
        clock = make_clock(fake)
        fake.advance(61)

        self.assertEqual(clock.pace(), 0)
        self.assertEqual(clock.missed_deadlines, 1)
        self.assertEqual(fake.sleeps, [])
        self.assertEqual(clock.pace(), 39)

    def test_small_sleep_overshoot_is_not_a_work_deadline_miss(self):
        fake = FakeTime(sleep_overshoot=1)
        clock = make_clock(fake)

        self.assertEqual(clock.pace(), 50)
        self.assertEqual(clock.missed_deadlines, 0)
        self.assertEqual(clock.updates_due(), 1)

    def test_wrap_safe_clock_keeps_absolute_cadence(self):
        fake = FakeTime(modulus=256)
        fake.absolute_ms = 240
        clock = make_clock(fake, frame_ms=20, update_ms=20)

        self.assertEqual(clock.pace(), 20)
        self.assertEqual(fake.ticks_ms(), 4)
        self.assertEqual(clock.updates_due(), 1)
        fake.advance(7)
        self.assertEqual(clock.pace(), 13)
        self.assertEqual(clock.missed_deadlines, 0)


if __name__ == "__main__":
    unittest.main()
