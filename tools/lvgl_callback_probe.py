"""Measure callback-exception nesting and soft-reset retention; restore IDE."""

import argparse
import json
from pathlib import Path
import uuid

from phase1_device import RawRepl
from sd_runtime_bench import ROOT, restart


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--expect-clean', action='store_true',
                        help='require balanced nesting and a working timer after soft reset')
    args = parser.parse_args()
    args.session.mkdir(parents=True, exist_ok=True)
    prefix = uuid.uuid4().hex[:8]
    result = {'complete': False, 'restored_startup': False}
    repl = RawRepl(args.port, timeout=30)

    def raw_reset(name):
        repl.serial.write(b'\x04')
        output = repl._read_until(b'raw REPL; CTRL-B to exit\r\n>', 30)
        (args.session / (prefix + '-' + name + '.log')).write_bytes(output)
        if b'MPY: soft reboot' not in output or b'ESP-ROM:' in output:
            raise ValueError('Expected a raw soft reset')

    try:
        try:
            restart(repl, args.session / (prefix + '-initial.log'))
            result['initial_startup'] = True
        except ValueError as error:
            # Record normal-runtime failure separately. A reachable raw REPL
            # can still test native cleanup without a display or touch driver.
            result['initial_startup'] = False
            result['initial_startup_error'] = str(error)
        repl.enter()
        repl.exec('import os; os.sync()')
        raw_reset('before')
        code = (ROOT / 'tools/device/lvgl_callback_exception.py').read_text()
        output = repl.exec(code)
        (args.session / (prefix + '-probe.log')).write_bytes(output)
        result['probe'] = json.loads(output)
        if not result['probe']['caught']:
            raise ValueError('Test callback did not run')
        result['nesting_leaked'] = result['probe']['after'] != result['probe']['before']
        raw_reset('after')
        result['after_soft_reset'] = json.loads(repl.exec('''import json, lvgl as lv
_probe_after = {'nesting': lv._nesting.value}
if not lv.is_initialized(): lv.init()
_probe_beats = 0
def _probe_beat(timer):
    global _probe_beats
    _probe_beats += 1
_probe_timer = lv.timer_create(_probe_beat, 1, None)
lv.tick_inc(10)
lv.timer_handler()
_probe_after['callback_runs'] = _probe_beats
_probe_after['nesting_after_callback'] = lv._nesting.value
print(json.dumps(_probe_after))'''))
        result['cleanup_pass'] = (
            not result['nesting_leaked'] and result['after_soft_reset']['nesting'] == 0
            and result['after_soft_reset']['callback_runs'] > 0
            and result['after_soft_reset']['nesting_after_callback'] == 0)
        if args.expect_clean and not result['cleanup_pass']:
            raise ValueError('Native callback exception/reset cleanup failed')
        result['complete'] = True
    except BaseException as error:
        result['error'] = str(error)
        raise
    finally:
        try:
            restart(repl, args.session / (prefix + '-restored.log'))
            result['restored_startup'] = True
        except BaseException as error:
            result['restore_error'] = str(error)
        repl.close()
        path = args.session / (prefix + '-callback-probe.json')
        path.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'evidence': str(path), **result}))
    return 0 if (result['complete'] and result['restored_startup']
                 and result['initial_startup']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
