import io
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from touch_startup_probe import RecordedSerial, validate_sample


class TouchStartupTests(unittest.TestCase):
    def test_repl_entry_preserves_discarded_error_evidence(self):
        serial = Mock(in_waiting=18)
        serial.read.return_value = b'OSError: 116\r\n'
        log = io.BytesIO()
        RecordedSerial(serial, log).reset_input_buffer()
        self.assertEqual(log.getvalue(), b'OSError: 116\r\n')
        serial.reset_input_buffer.assert_not_called()

    def test_healthy_boot_does_not_excuse_dead_scheduler_or_hard_reset(self):
        state = {'beats': 2, 'nesting': 0, 'handler_active': True,
                 'reset_cause': 5, 'boot': {'health': 'healthy', 'mode': 'IDE',
                                          'consecutive_failures': 0}}
        validate_sample(state, True)
        for change in ({'beats': 0}, {'nesting': 1}, {'handler_active': False},
                       {'reset_cause': 3}):
            with self.assertRaises(ValueError):
                validate_sample(dict(state, **change), True)
