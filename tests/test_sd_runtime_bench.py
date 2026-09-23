"""Fail closed on misleading reset, scheduler and resumed-load evidence."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from sd_runtime_bench import check_scheduler, check_startup, validate_resume, validate_observations
from sd_bringup import expected_file


class RuntimeBenchTests(unittest.TestCase):
    def test_missing_observations_never_imply_physical_pass(self):
        good = {'visual_alignment_colors_flicker': True, 'touch_response': True,
                'cold_boot': True, 'notes': 'Operator observed'}
        self.assertTrue(validate_observations(good))
        self.assertFalse(validate_observations({**good, 'touch_response': False}))
        for value in (None, 1, 'yes'):
            with self.assertRaises(ValueError):
                validate_observations({**good, 'cold_boot': value})

    def test_reboot_after_soft_reset_and_recovered_panics_do_not_pass(self):
        healthy = b'\nStarting IDE\nHEALTHY mode=IDE'
        check_startup(b'MPY: soft reboot' + healthy, True)
        for log in (b'MPY: soft reboot\nESP-ROM: reboot' + healthy,
                    b'MPY: soft reboot\nGuru Meditation' + healthy,
                    b'MPY: soft reboot\nEntering recovery' + healthy,
                    b'MPY: soft reboot\nStarting IDE',
                    b'MPY: soft reboot\n>>> '):
            with self.assertRaises(ValueError):
                check_startup(log, True)

    def test_tick_or_zero_nesting_alone_cannot_pass_scheduler(self):
        before = {'heartbeats': 2}
        good = {'heartbeats': 3, 'nesting': 0, 'owner': 'ui', 'pending': False}
        check_scheduler(before, good)
        for change in ({'heartbeats': 2}, {'nesting': 1}, {'owner': 'game'}, {'pending': True}):
            with self.assertRaises(ValueError):
                check_scheduler(before, {**good, **change})

    def test_resume_rejects_foreign_paths_duplicate_coverage_and_bad_hashes(self):
        contract = {'requested_cycles': 2, 'requested_soft_resets': 3}
        directory = '/.tartlab-bench/runtime-' + 'a' * 32
        entry = {'path': directory + '/01-1234abcd.bin', **expected_file(1048576)}
        result = {'contract': contract, 'directory': directory, 'cycles': [entry], 'resets': []}
        validate_resume(result, contract)
        for change in ({'cycles': [entry, entry]}, {'cycles': [{**entry, 'path': '/main.py'}]},
                       {'cycles': [{**entry, 'sha256': 'wrong'}]}, {'pass': True}):
            with self.assertRaises(ValueError):
                validate_resume({**result, **change}, contract)


if __name__ == '__main__':
    unittest.main()
