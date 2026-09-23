"""Journal bounded passive normal-startup GT911 observations and restore files.

The only Ctrl-C is before a reset or after an observation window has ended.
Resume requires identical tool/config hashes and installed original file hashes.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import time
import uuid

from phase1_device import RawRepl
from sd_runtime_bench import ERRORS, restart
from touch_startup_probe import RecordedSerial

ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / 'tools/device/touch_flight_recorder.py'
REMOTE_RECORDER = '/touch_flight_recorder.py'
REMOTE_CONFIG = '/touch_flight_config.json'
TARGETS = {'main': '/main.py', 'ide': '/ide/ide.py'}
FINGERPRINT = '''import esp32, hashlib, binascii, json
_part = esp32.Partition(esp32.Partition.RUNNING)
_digest = hashlib.sha256()
_block = bytearray(4096)
for _offset in range(0, _part.info()[3], len(_block)):
    _part.readblocks(_offset // len(_block), _block)
    _digest.update(_block)
print(json.dumps(dict(partition=_part.info(),
    sha256=binascii.hexlify(_digest.digest()).decode())))
del _block, _digest, _part
'''


def sha(content):
    return hashlib.sha256(content).hexdigest()


def schedule(experiment, count):
    if experiment == 'baseline':
        return [{'variant': 'baseline', 'soft': bool(index % 2)} for index in range(count)]
    if experiment == 'reset':
        return [{'variant': 'reset' if index % 2 else 'no-reset',
                 'reset': bool(index % 2), 'soft': bool((index // 2) % 2)}
                for index in range(count * 2)]
    return [{'variant': 'command-%d' % (1 - index % 2),
             'command': 1 - index % 2, 'soft': bool((index // 2) % 2)}
            for index in range(count * 2)]


def summarize(result):
    variants = {}
    for run in result['runs']:
        name = run.get('setting', {}).get('variant', 'baseline')
        totals = variants.setdefault(name, {'startups': 0, 'hard': 0, 'soft': 0,
            'screen_passes': 0, 'transport_failures': 0, 'polls_observed': 0,
            'transactions_observed': 0, 'elapsed_s': 0, 'coordinate_reads': 0})
        totals['startups'] += 1
        totals['soft' if run['soft'] else 'hard'] += 1
        totals['screen_passes'] += int(run['pass'])
        totals['transport_failures'] += int(run['transport_failure'])
        totals['elapsed_s'] += run['elapsed_s']
        if run['beats']:
            final = run['beats'][-1]
            totals['polls_observed'] += final['polls']
            totals['transactions_observed'] += final['transactions']
            if 'coordinate_reads' not in final:
                totals['coordinate_reads'] = None
            elif totals['coordinate_reads'] is not None:
                totals['coordinate_reads'] += final['coordinate_reads']
    for totals in variants.values():
        totals['elapsed_s'] = round(totals['elapsed_s'], 1)
    return {'variants': variants, 'physical_touch_pass': None,
            'conclusion': ('failures captured; classify before attributing cause'
                           if any(v['transport_failures'] for v in variants.values())
                           else 'inconclusive; no transport failure reproduced'),
            'counts_are_lower_bounds': True}


def validate_identity(record, board):
    if not record['init']:
        return
    rows = record['init'][0]['transactions']
    reads = {row[4]: row[11:17] for row in rows if row[2] == 'read'}
    expected = board['display']['native_size']
    try:
        dimensions = [reads[reg][0] | (reads[reg][1] << 8) for reg in (0x8146, 0x8148)]
        valid = reads[0x8140][:3] == list(b'911') and dimensions == list(expected)
        for beat in record['beats']:
            point = beat.get('last_raw_point')
            if point and not all(0 <= point[n] < dimensions[n] for n in range(2)):
                valid = False
    except (KeyError, IndexError):
        valid = False
    record['identity_coordinates_valid'] = valid
    if not valid:
        record['pass'] = False


def instrument(main, ide):
    main = main.decode('utf-8').replace('\r\n', '\n')
    ide = ide.decode('utf-8').replace('\r\n', '\n')
    anchor = 'import ujson\n'
    if main.count(anchor) != 1:
        raise ValueError('Unexpected installed main import anchor')
    main = main.replace(anchor, anchor +
        "import touch_flight_recorder as _touch_rec\n"
        "_touch_rec.install(ujson.load(open('/touch_flight_config.json')))\n"
        "_touch_rec.mark('main')\n")
    ide = 'import touch_flight_recorder as _touch_rec\n' + ide
    changes = {'ap_if.active': 'wifi_ap_active', 'sta_if.active': 'wifi_sta_active',
               'sta_if.scan': 'wifi_scan', 'sta_if.connect': 'wifi_connect',
               'platform.configure_open_access_point': 'wifi_ap',
               'HTTPServer': 'ide_setup', 'mark_boot_healthy': 'healthy'}
    edits = []
    seen = set()
    # AST byte offsets work for both packaged minified and development sources.
    lines = ide.encode().splitlines(True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for node in ast.walk(ast.parse(ide)):
        if not isinstance(node, ast.Call):
            continue
        name = ast.unparse(node.func)
        if name not in changes:
            continue
        seen.add(name)
        start = offsets[node.lineno - 1] + node.col_offset
        end = offsets[node.func.end_lineno - 1] + node.func.end_col_offset
        edits.append((start, end + 1, ('_touch_rec.call(%r, %s, ' %
                                    (changes[name], name)).encode()))
    if seen != set(changes):
        raise ValueError('Missing installed IDE calls: %r' % (set(changes) - seen))
    encoded = ide.encode()
    for start, end, replacement in sorted(edits, reverse=True):
        encoded = encoded[:start] + replacement + encoded[end:]
    ide = encoded.decode()
    compile(main, 'instrumented-main', 'exec')
    compile(ide, 'instrumented-ide', 'exec')
    return {'main': main.encode(), 'ide': ide.encode()}


def fetch(repl, path):
    length = int(repl.exec('import os; print(os.stat(%r)[6])' % path))
    content = bytearray()
    for offset in range(0, length, 2048):
        code = ('import ubinascii\nf=open(%r,"rb")\nf.seek(%d)\n'
                'print(ubinascii.b2a_base64(f.read(2048)).decode().strip())\nf.close()')
        content.extend(base64.b64decode(repl.exec(code % (path, offset))))
    return bytes(content)


def enter_quiet(repl):
    """Outside an observation window, pause diagnostic UART timer output."""
    repl.enter()
    repl.exec("import sys\n_rec=sys.modules.get('touch_flight_recorder')\n"
              "if _rec is not None and _rec.timer is not None:\n    _rec.timer.pause()")


def observe(repl, path, soft, window, startup_timeout=90):
    enter_quiet(repl)
    repl.exec('import os; os.sync()')
    if soft:
        repl.serial.write(b'\x02')
        repl._read_until(b'>>> ')
        repl.serial.write(b'\x04')
    else:
        repl.serial.write(b'import machine; machine.reset()\x04')
    started = time.monotonic()
    healthy_at = None
    deadline = started + startup_timeout
    output = bytearray()
    with path.open('wb') as log:
        while time.monotonic() < deadline:
            data = repl.serial.read(repl.serial.in_waiting or 1)
            if not data:
                continue
            log.write(data)
            log.flush()
            output.extend(data)
            if healthy_at is None and b'HEALTHY mode=IDE' in output:
                healthy_at = time.monotonic()
                deadline = healthy_at + window
    return classify(bytes(output), soft, time.monotonic() - started,
                    None if healthy_at is None else healthy_at - started)


def classify(output, soft, elapsed, healthy_seconds):
    events = []
    for line in output.splitlines():
        if b'TOUCH_REC=' in line:
            events.append(json.loads(line.split(b'TOUCH_REC=', 1)[1]))
    init = [event['value'] for event in events if event['kind'] == 'init']
    beats = [event['value'] for event in events if event['kind'] == 'heartbeat']
    failures = [event['value'] for event in events if event['kind'] == 'failure']
    reset_audits = [event['value'] for event in events if event['kind'] == 'reset_audit']
    healthy_beats = [beat for beat in beats if beat['phase'] == 'healthy']
    reset_ok = len(init) == 1 and ((init[0]['reset_cause'] == 5) == soft)
    progressing = (len(healthy_beats) >= 2 and
                   all(after['polls'] > before['polls'] and
                       after['beats'] > before['beats'] and
                       not after.get('failed', False)
                       for before, after in zip(healthy_beats, healthy_beats[1:])))
    passed = (healthy_seconds is not None and reset_ok and progressing
              and not failures and not any(word in output for word in ERRORS))
    return {'pass': passed, 'soft': soft, 'elapsed_s': elapsed,
            'healthy_at_s': healthy_seconds, 'init': init, 'beats': beats,
            'failures': failures, 'transport_failure': bool(failures),
            'reset_audits': reset_audits,
            'scheduler_progress': progressing, 'reset_verified': reset_ok,
            'physical_touch_pass': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'status'), nargs='?', default='run')
    parser.add_argument('--port')
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--cycles', type=int, default=20)
    parser.add_argument('--window', type=int, default=60)
    parser.add_argument('--failure-target', type=int, default=3)
    parser.add_argument('--experiment', choices=('baseline', 'command', 'reset'), default='baseline')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.action == 'status':
        result = json.loads((args.session / 'passive.json').read_text())
        print(json.dumps(dict(summarize(result), complete=result['complete'],
                              restored=result.get('restored_startup'))))
        return
    if not args.port or not args.config:
        parser.error('run requires --port and --config')
    if args.cycles < 2 or args.cycles % 2 or args.window < 30 or args.failure_target < 1:
        parser.error('cycles must be positive/even, window >=30, failure target >=1')
    contract = {'tool_sha': sha(Path(__file__).read_bytes()),
                'recorder_sha': sha(RECORDER.read_bytes()),
                'config_sha': sha(args.config.read_bytes()),
                'cycles': args.cycles, 'window': args.window,
                'failure_target': args.failure_target, 'port': args.port}
    contract['experiment'] = args.experiment
    contract['schedule'] = schedule(args.experiment, args.cycles)
    args.session.mkdir(parents=True, exist_ok=True)
    journal = args.session / 'passive.json'
    if args.resume:
        result = json.loads(journal.read_text())
        if result['contract'] != contract or result.get('complete'):
            parser.error('resume contract differs or run already complete')
    else:
        if journal.exists():
            parser.error('session exists; use --resume')
        result = {'contract': contract, 'runs': [], 'complete': False}

    def save():
        temporary = journal.with_suffix('.tmp')
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(journal)

    save()
    # Bundle the exact implementation for audit even if local sources change.
    for name, content in (('runner.py', Path(__file__).read_bytes()),
                          ('recorder.py', RECORDER.read_bytes()),
                          ('config.json', args.config.read_bytes())):
        path = args.session / name
        if path.exists() and path.read_bytes() != content:
            raise ValueError('Session source bundle differs: ' + name)
        path.write_bytes(content)
    repl = RawRepl(args.port, timeout=30)
    with (args.session / 'host-transitions.log').open('ab') as transitions:
        repl.serial = RecordedSerial(repl.serial, transitions)
        originals = {}
        mutated = False
        try:
            repl.enter()
            device = json.loads(repl.exec(
                "import json, sys; from tartlabutils.platform import configure_paths; "
                "configure_paths(); from hdwconfig import BOARD_CONFIG; "
                "print(json.dumps(dict(version=sys.version, board=BOARD_CONFIG)))"))
            device['firmware'] = json.loads(repl.exec(FINGERPRINT, timeout=90))
            device['factory_sha256'] = sha(fetch(repl, '/lib/tartlabutils/factory.py'))
            if args.resume and device != result['device']:
                raise ValueError('Resume device firmware/config/factory differs')
            result['device'] = device
            if device['board']['id'] != json.loads(args.config.read_text())['board']:
                raise ValueError('Connected board does not match diagnostic config')
            for name, remote in TARGETS.items():
                backup = args.session / (name + '-original.py')
                actual = fetch(repl, remote)
                if backup.exists():
                    if actual != backup.read_bytes():
                        raise ValueError('Installed file differs from original backup: ' + remote)
                else:
                    backup.write_bytes(actual)
                originals[name] = actual
            payload = instrument(originals['main'], originals['ide'])
            original_hashes = {name: sha(data) for name, data in originals.items()}
            if args.resume and original_hashes != result['original_hashes']:
                raise ValueError('Resume original file hashes differ')
            result['original_hashes'] = original_hashes
            result['instrumented_hashes'] = {name: sha(data) for name, data in payload.items()}
            save()
            for remote in (REMOTE_RECORDER, REMOTE_CONFIG):
                exists = int(repl.exec('import os; print(int(%r in os.listdir("/")))' % remote[1:]))
                if exists:
                    raise ValueError('Diagnostic path already exists: ' + remote)
            mutated = True
            for remote, content in ((REMOTE_RECORDER, RECORDER.read_bytes()),
                                    (REMOTE_CONFIG, args.config.read_bytes())):
                repl.stream_file(remote, content, sha(content))
            for name, content in payload.items():
                (args.session / (name + '-instrumented.py')).write_bytes(content)
                repl.stream_file(TARGETS[name], content, sha(content))
            print('Installed verified recorder; passive observation begins', flush=True)
            for index in range(len(result['runs']), len(contract['schedule'])):
                if (args.experiment == 'baseline' and
                        sum(run['transport_failure'] for run in result['runs']) >= args.failure_target):
                    break
                setting = contract['schedule'][index]
                attempt = {'index': index, 'setting': setting,
                           'id': uuid.uuid4().hex[:8], 'complete': False}
                result.setdefault('attempts', []).append(attempt)
                save()
                if args.experiment in ('command', 'reset'):
                    variant_config = json.loads(args.config.read_text())
                    variant_config[args.experiment] = setting[args.experiment]
                    encoded = (json.dumps(variant_config, sort_keys=True) + '\n').encode()
                    (args.session / ('%02d-config.json' % index)).write_bytes(encoded)
                    enter_quiet(repl)
                    repl.stream_file(REMOTE_CONFIG, encoded, sha(encoded))
                log_name = '%02d-%s-passive.log' % (index, attempt['id'])
                attempt['log'] = log_name
                save()
                record = observe(repl, args.session / log_name,
                                 setting['soft'], args.window)
                attempt['complete'] = True
                record['setting'] = setting
                record['log'] = log_name
                validate_identity(record, result['device']['board'])
                if record['init']:
                    expected_command = setting.get('command', 1)
                    writes = {row[4]: row[11] for row in record['init'][0]['transactions']
                              if row[2] == 'write'}
                    if (writes.get(0x8040) != expected_command or
                            writes.get(0x8046) != expected_command):
                        record['pass'] = False
                        record['command_mismatch'] = True
                if args.experiment == 'reset':
                    audits = record['reset_audits']
                    if len(audits) != 1 or audits[0]['performed'] != setting['reset']:
                        record['pass'] = False
                        record['reset_audit_missing'] = True
                    if setting['reset'] and record['init']:
                        expected_address = variant_config['reset_expected_address']
                        if any(row[3] != expected_address for row in record['init'][0]['transactions']):
                            record['pass'] = False
                            record['reset_address_mismatch'] = True
                result['runs'].append(record)
                result['summary'] = summarize(result)
                save()
                print(json.dumps({'run': index + 1, 'pass': record['pass'],
                                  'transport_failure': record['transport_failure'],
                                  'polls': record['beats'][-1]['polls'] if record['beats'] else 0}), flush=True)
                if not record['pass'] and not record['transport_failure']:
                    raise RuntimeError('Non-transport startup/recorder failure; inspect before continuing')
            result['complete'] = True
        finally:
            if mutated:
                try:
                    enter_quiet(repl)
                    for name, content in originals.items():
                        repl.stream_file(TARGETS[name], content, sha(content))
                    repl.exec('import os\nfor _path in %r:\n'
                              '    try:\n        os.remove(_path)\n'
                              '    except OSError as _error:\n'
                              '        if _error.args[0] != 2: raise\nos.sync()' %
                              ((REMOTE_RECORDER, REMOTE_CONFIG),))
                    result['restored_hashes'] = {name: sha(fetch(repl, remote))
                                               for name, remote in TARGETS.items()}
                    restart(repl, args.session / 'restored-startup.log')
                    result['restored_startup'] = True
                except Exception as error:
                    result['restore_error'] = repr(error)
                    result['restored_startup'] = False
            repl.close()
            result['summary'] = summarize(result)
            save()
    print(json.dumps({'complete': result['complete'], 'journal': str(journal),
                      'restored': result.get('restored_startup')}))


if __name__ == '__main__':
    main()
