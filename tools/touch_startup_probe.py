"""Repeat normal startup and retain touch/scheduler evidence, including REPL entry.

The scheduler sample follows Ctrl-C; a stall is not automatically a touch fault.
Leaves normal startup running. Does not certify physical touch or cold power-on.
"""
import argparse
import hashlib
import json
from pathlib import Path

from phase1_device import RawRepl
from sd_runtime_bench import restart


class RecordedSerial:
    """Keep bytes RawRepl normally discards when interrupting the application."""

    def __init__(self, serial, log):
        self.serial = serial
        self.log = log

    def __getattr__(self, name):
        return getattr(self.serial, name)

    def read(self, size=1):
        data = self.serial.read(size)
        self.log.write(data)
        self.log.flush()
        return data

    def reset_input_buffer(self):
        self.read(self.serial.in_waiting)


SAMPLE = '''import json, time, lvgl as lv, machine
from tartlabutils.platform import get_platform
p = get_platform()
h = p.controller._task_handler
_probe_beats = 0
def _probe_beat(timer):
    global _probe_beats
    _probe_beats += 1
t = lv.timer_create(_probe_beat, 100, None)
time.sleep_ms(2000)
t.delete()
print(json.dumps({'beats': _probe_beats, 'nesting': lv._nesting.value,
    'handler_active': h.is_running(), 'handler_running': h._running,
    'handler_scheduled': h._scheduled, 'reset_cause': machine.reset_cause(),
    'board': p.board['id'], 'i2c': p.board['touch']['i2c'],
    'boot': json.load(open('/state/boot.json'))}))
'''


def validate_sample(state, soft):
    if (state['beats'] <= 0 or state['nesting'] != 0
            or not state['handler_active']
            or state['boot']['health'] != 'healthy'
            or state['boot']['mode'] != 'IDE'
            or state['boot']['consecutive_failures'] != 0
            or (soft and state['reset_cause'] != 5)):
        raise ValueError('Post-interrupt scheduler/boot check failed; inspect sample and transcript')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 100:
        parser.error('cycles must be 1..100')
    args.session.mkdir(parents=True, exist_ok=True)
    journal = args.session / 'touch-startup.json'
    if journal.exists():
        parser.error('session already exists; select a new session')
    result = {'requested_cycles': args.cycles, 'cycles': [], 'pass': False,
              'physical_touch_pass': None, 'cold_power_on_pass': None,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def save():
        temporary = journal.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(journal)

    save()
    repl = RawRepl(args.port, timeout=30)
    with (args.session / 'serial.log').open('wb') as transcript:
        repl.serial = RecordedSerial(repl.serial, transcript)
        try:
            for index in range(args.cycles):
                record = {'soft': bool(index % 2), 'pass': False}
                result['cycles'].append(record)
                try:
                    restart(repl, args.session / ('%02d-startup.log' % index), soft=record['soft'])
                    record['startup_pass'] = True
                    repl.enter()
                    output = repl.exec(SAMPLE)
                    (args.session / ('%02d-sample.log' % index)).write_bytes(output)
                    record['post_interrupt'] = json.loads(output)
                    validate_sample(record['post_interrupt'], record['soft'])
                    record['pass'] = True
                except Exception as error:
                    record['error'] = repr(error)
                save()
                print(json.dumps({'cycle': index + 1, 'pass': record['pass'],
                                  'error': record.get('error')}), flush=True)
        finally:
            try:
                restart(repl, args.session / 'restored-startup.log')
                result['restored_startup'] = True
            except Exception as error:
                result['restored_startup'] = False
                result['restore_error'] = repr(error)
            repl.close()
            result['pass'] = (len(result['cycles']) == args.cycles
                              and all(item['pass'] for item in result['cycles'])
                              and result['restored_startup'])
            save()
    print(json.dumps({'pass': result['pass'], 'journal': str(journal)}))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
