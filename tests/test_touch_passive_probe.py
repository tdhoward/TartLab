import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from touch_passive_probe import instrument, classify, schedule, observe


class PassiveProbeTests(unittest.TestCase):
    def test_observation_does_not_interrupt_healthy_window(self):
        clock = [0]
        writes = []
        def event(kind, value):
            return ('TOUCH_REC=' + json.dumps(dict(kind=kind, value=value)) + '\n').encode()
        class Serial:
            in_waiting = 1
            def write(self, data):
                writes.append((clock[0], data))
            def read(self, count):
                clock[0] += 1
                if clock[0] == 1:
                    return event('init', {'reset_cause': 2}) + b'HEALTHY mode=IDE\n'
                return event('heartbeat', dict(phase='healthy', polls=clock[0], beats=clock[0]))
        serial = Serial()
        repl = types.SimpleNamespace(serial=serial, enter=lambda: serial.write(b'\x03'),
                                     exec=lambda code: b'')
        with TemporaryDirectory() as directory, patch('touch_passive_probe.time.monotonic', lambda: clock[0]):
            result = observe(repl, Path(directory) / 'passive.log', False, 60)
        self.assertTrue(result['pass'])
        self.assertEqual(result['elapsed_s'], 61)
        self.assertTrue(all(at == 0 for at, data in writes))

    def test_interleaving_balances_resets_within_each_variant(self):
        runs = schedule('command', 20)
        self.assertEqual(len(runs), 40)
        for command in (0, 1):
            for soft in (False, True):
                self.assertEqual(sum(run['command'] == command and run['soft'] == soft
                                     for run in runs), 10)
        resets = schedule('reset', 20)
        for reset in (False, True):
            for soft in (False, True):
                self.assertEqual(sum(run['reset'] == reset and run['soft'] == soft
                                     for run in resets), 10)

    def test_reset_preserves_other_pins_and_settles_after_int_floats(self):
        modules = {'gt911': types.SimpleNamespace(), 'lvgl': types.SimpleNamespace(),
                   'machine': types.SimpleNamespace()}
        spec = importlib.util.spec_from_file_location('reset_test', ROOT / 'tools/device/touch_flight_recorder.py')
        recorder = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(recorder)
        events = []
        recorder.time = types.SimpleNamespace(ticks_us=lambda: 0, ticks_ms=lambda: 0,
                                              sleep_ms=lambda ms: events.append(('sleep', ms)))
        recorder.emit = lambda *args: events.append(args)
        recorder.config = {'reset_settle_ms': 50}

        class Bus:
            regs = [0, 0xa0, 0, 0xf0]
            def readfrom_mem(self, addr, reg, size):
                return bytes((self.regs[1] if reg == 0 else self.regs[reg],))
            def writeto_mem(self, addr, reg, data):
                self.regs[reg] = data[0]
                events.append(('write', reg, data[0]))
        bus = Bus()
        options = dict(driver='PCA9557', address=24, reset_bit=0, interrupt_bit=1,
                       assert_ms=20, release_ms=100)
        recorder.audited_reset(bus, options, True)
        self.assertEqual(bus.regs[1], 0xa1)
        self.assertEqual(bus.regs[3], 0xf2)
        self.assertLess(events.index(('write', 3, 0xf2)), events.index(('sleep', 50)))
        events.clear()
        recorder.audited_reset(bus, options, False)
        self.assertFalse(any(event[0] == 'write' for event in events))
    def test_instrumentation_compiles_and_retains_network_calls(self):
        main = (ROOT / 'src/main.py').read_bytes()
        ide = (ROOT / 'src/ide/ide.py').read_bytes()
        payload = instrument(main, ide)
        self.assertEqual(payload['ide'].count(b"'wifi_sta_active', sta_if.active, True"), 2)
        self.assertIn(b"_touch_rec.call('healthy', mark_boot_healthy", payload['ide'])
        with self.assertRaises(ValueError):
            instrument(b'print("unknown main")', ide)

    def test_missing_heartbeat_and_transport_failure_never_pass(self):
        def event(kind, value):
            return ('TOUCH_REC=' + json.dumps(dict(kind=kind, value=value)) + '\n').encode()
        data = b'HEALTHY mode=IDE\n' + event('init', {'reset_cause': 5})
        self.assertFalse(classify(data, True, 70, 10)['pass'])
        for n in (1, 2):
            data += event('heartbeat', dict(phase='healthy', polls=n, beats=n))
        self.assertTrue(classify(data, True, 70, 10)['pass'])
        self.assertFalse(classify(data, False, 70, 10)['pass'])
        self.assertFalse(classify(data + event('failure', {}), True, 70, 10)['pass'])

    def test_first_error_is_preserved_and_future_polls_do_not_touch_bus(self):
        error = OSError(116)
        calls = []

        class Driver:
            PRESSED = 1
            def __init__(self):
                self._device = types.SimpleNamespace(dev_id=20)
                self._rx_buf = bytearray(6)
                self.writes = []
            def _read_reg(self, reg, num_bytes=None, buf=None):
                calls.append(reg)
                raise error
            def _write_reg(self, reg, value=None, buf=None):
                self.writes.append((reg, value))
            def _get_coords(self):
                self._read_reg(0x814e, 1)

        modules = {'gt911': types.SimpleNamespace(GT911=Driver),
                   'lvgl': types.SimpleNamespace(timer_create=lambda *args: None),
                   'machine': types.SimpleNamespace(mem32={1: 42}, reset_cause=lambda: 5)}
        spec = importlib.util.spec_from_file_location('recorder_test', ROOT / 'tools/device/touch_flight_recorder.py')
        recorder = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(recorder)
        recorder.time = types.SimpleNamespace(ticks_us=lambda: 100, ticks_diff=lambda a, b: a-b)
        recorder.emit = lambda *args: None
        recorder.install({'snapshot_registers': {'gpio': 1}, 'command': 0})
        driver = Driver()
        driver._write_reg(0x8040, 1)
        driver._write_reg(0x8046, 1)
        self.assertEqual(driver.writes, [(0x8040, 0), (0x8046, 0)])
        for _ in range(50):
            driver._write_reg(0x8041, 0)
        self.assertEqual(len(recorder.history), 32)
        self.assertEqual(len(recorder.initial), 32)
        with self.assertRaises(OSError) as caught:
            driver._get_coords()
        self.assertIs(caught.exception, error)
        self.assertIsNone(driver._get_coords())
        self.assertEqual(calls, [0x814e])
        self.assertEqual(recorder.failure['row'][3:7], [20, 0x814e, 1, 116])
        self.assertEqual(recorder.failure['registers'], {'gpio': 42})


if __name__ == '__main__':
    unittest.main()
