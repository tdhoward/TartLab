"""Board-local contracts for the unqualified non-touch T-Display-S3 port."""

import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_phase5
from tests.test_buttons import load


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'boards/lilygo_t_display_s3/runtime/t_display_s3_modern.py'


class BoardTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(PAYLOAD.read_text())
        assignments = [node for node in tree.body if isinstance(node, ast.Assign)]
        self.assertEqual(len(assignments), 1)
        self.assertEqual(len(tree.body), 2)  # docstring plus the declarative object
        self.config = ast.literal_eval(assignments[0].value)
        self.helpers = load('board')

    def test_explicit_absent_touch_named_buttons_and_i80_wiring(self):
        self.helpers.validate_board_config(self.config)
        self.assertIsNone(self.config['touch'])
        self.assertEqual(self.config['navigation'], {'next': 'A', 'activate': 'B'})
        self.assertEqual([pin['number'] for pin in self.helpers.pin_definitions(self.config, 'BUTTON')], [0, 14])
        self.assertNotIn('spi', self.config['display'])

    def test_factory_selects_i80_without_spi_or_i2c_and_keeps_wire_order(self):
        modern = test_phase5.load_modern_rendering()
        factory, _, _ = test_phase5.load_factory(modern)
        recorded = []
        bus = object()
        def create_bus(**options):
            recorded.append(options)
            return bus
        self.assertEqual(factory._transport(self.config, SimpleNamespace(),
                         SimpleNamespace(I80Bus=create_bus)), (None, bus))
        self.assertEqual(recorded, [{'freq': 16000000, 'dc': 7, 'cs': 6, 'wr': 8,
                                    'data0': 39, 'data1': 40, 'data2': 41, 'data3': 42,
                                    'data4': 45, 'data5': 46, 'data6': 47, 'data7': 48}])
        with patch.dict(sys.modules, {'i2c': None}):
            self.assertEqual(factory._touch(self.config, None), (None, None, None))
        invalid = deepcopy(self.config)
        invalid['display']['spi'] = {}
        with self.assertRaises(ValueError):
            factory._transport(invalid, None, None)

    def test_power_and_read_strobe_sequence_is_declarative(self):
        modern = test_phase5.load_modern_rendering()
        factory, _, _ = test_phase5.load_factory(modern)
        actions = []
        def pin(number, mode, value):
            actions.append(('pin', number, value))
            return number
        pin.OUT = 1
        with patch('time.sleep_ms', lambda delay: actions.append(('delay', delay)), create=True):
            outputs = factory._outputs(self.config, SimpleNamespace(Pin=pin))
        self.assertEqual(outputs, [15, 9])
        self.assertEqual(actions, [('pin', 15, 1), ('delay', 100), ('pin', 9, 1), ('delay', 0)])


if __name__ == '__main__':
    unittest.main()
