"""Resumable normal-runtime SD/RGB/radio bench with reset and hash evidence.

Uses an already installed SD-root runtime. Leaves normal startup running.
Does not certify physical touch, visual quality, network throughput or power loss.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from phase1_device import RawRepl
from sd_bringup import expected_file, validate_files

ROOT = Path(__file__).resolve().parents[1]
ERRORS = (b'Traceback', b'Guru Meditation', b"panic'ed", b'Entering recovery',
          b'Uncaught exception', b'abort() was called', b'Brownout', b'Task watchdog')


def check_startup(output, soft):
    if (b'Starting IDE' not in output or b'HEALTHY mode=IDE' not in output
            or any(word in output for word in ERRORS)
            or (soft and (b'MPY: soft reboot' not in output or b'ESP-ROM:' in output))):
        raise ValueError('Normal startup failed; inspect startup log')


def check_scheduler(before, after):
    if after['nesting'] != 0 or after['heartbeats'] <= before['heartbeats']:
        raise ValueError('LVGL scheduler stopped progressing')
    if after['owner'] != 'ui' or after['pending']:
        raise ValueError('Display ownership did not settle')


def validate_resume(result, contract):
    directory = result.get('directory', '')
    if (result.get('contract') != contract or result.get('pass')
            or not re.fullmatch(r'/\.tartlab-bench/runtime-[0-9a-f]{32}', directory)
            or len(result.get('cycles', [])) > contract['requested_cycles']
            or len(result.get('resets', [])) > contract['requested_soft_resets']):
        raise ValueError('Resume contract differs or journal is invalid/complete')
    paths = [cycle['path'] for cycle in result['cycles']]
    if len(set(paths)) != len(paths) or any(not re.fullmatch(
            re.escape(directory) + r'/[0-9]{2,3}-[0-9a-f]{8}\.bin', path) for path in paths):
        raise ValueError('Invalid resume output paths')
    validate_files({entry['path']: entry for entry in result['cycles']},
                   {path: expected_file(1048576) for path in paths})


def validate_observations(value):
    fields = ('visual_alignment_colors_flicker', 'touch_response', 'cold_boot')
    if any(type(value.get(field)) is not bool for field in fields):
        raise ValueError('Complete every physical observation with true or false')
    if not isinstance(value.get('notes'), str):
        raise ValueError('Observation notes must be text')
    return all(value[field] for field in fields)


def restart(repl, log, soft=False):
    repl.enter()
    repl.exec('import os; os.sync()')
    if soft:
        repl.serial.write(b'\x02')
        repl._read_until(b'>>> ')
        repl.serial.write(b'\x04')
    else:
        repl.serial.write(b'import machine; machine.reset()\x04')
    output = bytearray()
    deadline = time.monotonic() + 75
    settled = None
    try:
        while time.monotonic() < deadline:
            output.extend(repl.serial.read(repl.serial.in_waiting or 1))
            if b'HEALTHY mode=IDE' in output and settled is None:
                # Starting IDE precedes Wi-Fi setup and the healthy commit.
                settled = time.monotonic() + 4
            if settled and time.monotonic() >= settled:
                break
    finally:
        log.write_bytes(output)
    check_startup(output, soft)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', default='run', choices=('run', 'observations'))
    parser.add_argument('--port')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--source', help='Existing verified 1 MiB baseline on SD')
    parser.add_argument('--cycles', type=int, default=16)
    parser.add_argument('--soft-resets', type=int, default=3)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.action == 'observations':
        value = json.loads((args.session / 'operator-observations.json').read_text())
        passed = validate_observations(value)
        print(json.dumps({'observations_complete': True, 'observations_pass': passed}))
        return 0 if passed else 1
    if not args.port or not args.inventory or not args.source:
        parser.error('run requires --port, --inventory and --source')
    if not 1 <= args.cycles <= 100 or not 1 <= args.soft_resets <= 20:
        parser.error('cycles must be 1..100 and soft-resets 1..20')
    inventory_bytes = args.inventory.read_bytes()
    inventory = json.loads(inventory_bytes)
    if not inventory.get('complete'):
        parser.error('inventory must be complete')
    args.session.mkdir(parents=True, exist_ok=True)
    journal = args.session / 'runtime-bench.json'
    contract = {'board': inventory['board'], 'source': args.source,
                'inventory_sha256': hashlib.sha256(inventory_bytes).hexdigest(),
                'requested_cycles': args.cycles, 'requested_soft_resets': args.soft_resets}
    if args.resume:
        result = json.loads(journal.read_text())
        validate_resume(result, contract)
    else:
        if journal.exists():
            parser.error('session exists; use --resume or a new session')
        result = {'contract': contract, 'cycles': [], 'resets': [], 'pass': False,
                  'directory': '/.tartlab-bench/runtime-' + uuid.uuid4().hex,
                  'visual_pass': None, 'physical_touch_pass': None}
    invocation = uuid.uuid4().hex[:8]
    result['checks_pass'] = False
    result.setdefault('invocations', []).append({
        'id': invocation,
        'tool_hashes': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                        for path in ('tools/sd_runtime_bench.py',
                                     'tools/device/sd_shared_runtime.py',
                                     'tools/device/sd_runtime_load.py')}})

    def save():
        temporary = journal.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        temporary.replace(journal)

    def log(name):
        return args.session / (invocation + '-' + name)

    save()
    operator = args.session / 'operator-observations.json'
    if not operator.exists():
        operator.write_text(json.dumps({'visual_alignment_colors_flicker': None,
                                       'touch_response': None, 'cold_boot': None,
                                       'notes': ''}, indent=2) + '\n')
    repl = RawRepl(args.port, timeout=30)
    pattern = expected_file(1048576)

    def boot():
        state = json.loads(repl.exec("import json, machine, vfs; from hdwconfig import BOARD_CONFIG; "
                                   "print(json.dumps(dict(board=BOARD_CONFIG['id'], "
                                   "boot=json.load(open('/state/boot.json')), "
                                   "mounts=[(repr(fs),p) for fs,p in vfs.mount()], "
                                   "nesting=__import__('lvgl')._nesting.value, "
                                   "reset_cause=machine.reset_cause())))"))
        log('boot-state-' + uuid.uuid4().hex[:8] + '.json').write_text(
            json.dumps(state, indent=2) + '\n')
        if (state['board'] != contract['board'] or state['boot']['health'] != 'healthy'
                or state['boot']['mode'] != 'IDE' or state['boot']['consecutive_failures'] != 0
                or state['nesting'] != 0
                or not any('VfsFat' in fs and p == '/' for fs, p in state['mounts'])
                or not any(p == '/flash' for _, p in state['mounts'])):
            raise ValueError('Unexpected normal-runtime boot state: %r' % state)
        return state

    def hashes(expected, label):
        repl.exec((ROOT / 'tools/device/sd_runtime_probe.py').read_text())
        records = {}
        path = log(label + '.json')
        for name, wanted in expected.items():
            actual = json.loads(repl.exec('print(json.dumps(sd_runtime_hashes(%r)))' % [name], timeout=90))
            validate_files(actual, {name: wanted})
            records.update(actual)
            path.write_text(json.dumps({'pass': False, 'files': records}, indent=2) + '\n')
        path.write_text(json.dumps({'pass': True, 'files': records}, indent=2) + '\n')
        return {'log': str(path), 'verified_files': len(records)}

    try:
        restart(repl, log('initial-startup.log'))
        repl.enter()
        result['before'] = boot()
        expected = {'/' + name: entry for name, entry in inventory['inventory'].items()}
        expected[args.source] = pattern
        expected.update({cycle['path']: pattern for cycle in result['cycles']})
        result['preflight_hashes'] = hashes(expected, 'preflight')
        save()
        print('PREFLIGHT: healthy IDE; %d hashes verified' % len(expected), flush=True)
        repl.exec('import os; os.sync()')
        repl.serial.write(b'\x04')
        log('raw-soft-reset.log').write_bytes(repl._read_until(b'raw REPL; CTRL-B to exit\r\n>', 30))
        output = repl.exec((ROOT / 'tools/device/sd_shared_runtime.py').read_text(), timeout=60)
        log('fixture.log').write_bytes(output)
        ready = json.loads(output.split(b'SD_SHARED_READY=')[1])
        if ready['board'] != contract['board'] or ready['nesting'] or not ready['heartbeats']:
            raise ValueError('Shared runtime preflight failed')
        result['fixture'] = ready
        repl.exec((ROOT / 'tools/device/sd_runtime_load.py').read_text())
        repl.exec('import os\ntry:\n    os.stat(%r)\nexcept OSError as error:\n'
                  '    if error.args[0] != 2: raise\n    os.mkdir(%r)\n    os.sync()' %
                  (result['directory'], result['directory']))
        for index in range(len(result['cycles']), args.cycles):
            target = result['directory'] + '/%02d-%s.bin' % (index + 1, uuid.uuid4().hex[:8])
            result.setdefault('attempted_outputs', []).append(target)
            save()
            before = json.loads(repl.exec('print(json.dumps(_load_sample()))'))
            handover = json.loads(repl.exec('print(json.dumps(_load_handover()))'))
            log('%02d-handover.json' % (index + 1)).write_text(json.dumps(handover) + '\n')
            check_scheduler(before, handover)
            wifi = {'ssid': 'TartLab-SD-' + uuid.uuid4().hex[:8], 'password': uuid.uuid4().hex}
            output = repl.exec('print(json.dumps(sd_runtime_load(%r,%r,%r,%r,_load_refresh)))' % (
                args.source, target, pattern, wifi), timeout=180)
            wifi = None
            log('%02d-load.log' % (index + 1)).write_bytes(output)
            current = json.loads(output)
            validate_files({target: current}, {target: pattern})
            if not all(current.get(key) is True for key in ('ap_active', 'ap_active_after_io', 'wifi_stopped')):
                raise ValueError('Wi-Fi lifecycle failed')
            after = json.loads(repl.exec('print(json.dumps(_load_sample()))'))
            log('%02d-scheduler.json' % (index + 1)).write_text(json.dumps(after) + '\n')
            check_scheduler(handover, after)
            result['cycles'].append({'path': target, 'invocation': invocation,
                                     **current, 'scheduler': after})
            save()
            print('LOAD %d/%d verified; LVGL heartbeat %d' % (index + 1, args.cycles, after['heartbeats']), flush=True)
        restart(repl, log('post-load-startup.log'))
        repl.enter()
        previous = boot()
        result['post_load_boot'] = previous
        for index in range(len(result['resets']), args.soft_resets):
            restart(repl, log('soft-%02d-startup.log' % (index + 1)), soft=True)
            repl.enter()
            current = boot()
            if (current['reset_cause'] != 5 or
                    current['boot']['sequence'] != previous['boot']['sequence'] + 1):
                raise ValueError('Soft reset did not run normal boot exactly once')
            result['resets'].append(current)
            previous = current
            save()
            print('SOFT RESET %d/%d healthy' % (index + 1, args.soft_resets), flush=True)
        expected.update({cycle['path']: pattern for cycle in result['cycles']})
        result['persistence'] = hashes(expected, 'persistence')
        result['checks_pass'] = True
    except BaseException as error:
        result.setdefault('errors', []).append({'invocation': invocation, 'error': str(error)})
        raise
    finally:
        try:
            restart(repl, log('restored-startup.log'))
            result['restored_startup'] = True
        except BaseException as error:
            result['restored_startup'] = False
            result.setdefault('errors', []).append({'invocation': invocation, 'restore_error': str(error)})
        result['pass'] = bool(result.get('checks_pass') and result['restored_startup'])
        save()
        repl.close()
    print(json.dumps({'pass': result['pass'], 'cycles': len(result['cycles']),
                      'persistence': result.get('persistence'), 'journal': str(journal)}))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
