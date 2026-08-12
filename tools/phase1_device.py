"""Phase 1 hardware-test helper for a MicroPython device over raw REPL."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

import serial


class RawRepl:
    def __init__(self, port, baudrate=115200, timeout=10):
        self.serial = serial.Serial(
            port, baudrate, timeout=0.1, write_timeout=2, dsrdtr=False, rtscts=False)
        self.timeout = timeout

    def close(self):
        self.serial.close()

    def _read_until(self, marker, timeout=None):
        deadline = time.monotonic() + (timeout or self.timeout)
        data = bytearray()
        while marker not in data:
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for %r; received %r" % (marker, bytes(data[-200:])))
            waiting = self.serial.in_waiting
            chunk = self.serial.read(waiting or 1)
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def enter(self):
        self.serial.write(b"\r\x03\x03")
        time.sleep(0.2)
        self.serial.reset_input_buffer()
        self.serial.write(b"\r\x01")
        self._read_until(b"raw REPL; CTRL-B to exit\r\n>", 5)

    def exec(self, code, timeout=None):
        payload = code.encode("utf-8")
        # The legacy raw REPL has a small receive buffer and no host flow control.
        for offset in range(0, len(payload), 128):
            self.serial.write(payload[offset:offset + 128])
            time.sleep(0.01)
        self.serial.write(b"\x04")
        response = self._read_until(b"\x04>", timeout)
        if not response.startswith(b"OK"):
            raise RuntimeError("Raw REPL rejected command: %r" % response[:200])
        stdout_and_error = response[2:-2]
        split = stdout_and_error.find(b"\x04")
        if split < 0:
            raise RuntimeError("Malformed raw REPL response")
        stdout = stdout_and_error[:split]
        error = stdout_and_error[split + 1:]
        if error:
            raise RuntimeError(error.decode("utf-8", "replace"))
        return stdout

    def stream_file(self, remote_path, content, expected_sha256, timeout=180):
        """Write one verified file in acknowledged chunks over raw REPL."""
        self.exec("open(%r, 'wb').close()" % remote_path, timeout)
        chunk_size = 1536
        for offset in range(0, len(content), chunk_size):
            encoded = base64.b64encode(content[offset:offset + chunk_size])
            code = (
                "import ubinascii\n"
                "f=open(%r,'ab')\n"
                "f.write(ubinascii.a2b_base64(%r))\n"
                "f.close()\n" % (remote_path, encoded)
            )
            self.exec(code, timeout)
        verify_code = r'''
import uhashlib
path = %r
expected = %r
digest = uhashlib.sha256()
with open(path, 'rb') as stream:
    while True:
        chunk = stream.read(1024)
        if not chunk:
            break
        digest.update(chunk)
actual = ''.join('{:02x}'.format(byte) for byte in digest.digest())
if actual != expected:
    raise ValueError('Serial transfer hash mismatch')
print('SERIAL_STAGED=' + path + ' ' + actual)
''' % (remote_path, expected_sha256)
        return self.exec(verify_code, timeout)


PROBE_CODE = r'''
import os, sys, gc, machine, ujson
def safe(call, default=None):
    try:
        return call()
    except Exception:
        return default
def walk(path):
    total = 0
    count = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = os.ilistdir(current)
        except Exception:
            continue
        for entry in entries:
            child = current.rstrip('/') + '/' + entry[0]
            if entry[1] & 0x4000:
                stack.append(child)
            else:
                count += 1
                try:
                    total += os.stat(child)[6]
                except Exception:
                    pass
    return count, total
uname = safe(os.uname)
impl = safe(lambda: sys.implementation)
fs = safe(lambda: os.statvfs('/'))
file_count, content_bytes = walk('/')
settings = safe(lambda: ujson.load(open('/state/settings.json')), None)
if settings is None:
    settings = safe(lambda: ujson.load(open('/settings.json')), {})
repos = safe(lambda: ujson.load(open('/state/repos.json')), None)
if repos is None:
    repos = safe(lambda: ujson.load(open('/repos.json')), {})
info = {
    'sys_version': sys.version,
    'implementation': repr(impl),
    'uname': repr(uname),
    'reset_cause': safe(machine.reset_cause),
    'wake_reason': safe(machine.wake_reason),
    'heap_free': safe(gc.mem_free),
    'heap_alloc': safe(gc.mem_alloc),
    'statvfs': fs,
    'file_count': file_count,
    'content_bytes': content_bytes,
    'root_entries': safe(lambda: os.listdir('/'), []),
    'log_entries': safe(lambda: os.listdir('/state/logs'), safe(lambda: os.listdir('/logs'), [])),
    'settings_keys': sorted(settings.keys()) if isinstance(settings, dict) else [],
    'configured_wifi_count': len(settings.get('wifi_ssids', [])) if isinstance(settings, dict) else 0,
    'repos': repos,
}
try:
    import esp32
    info['esp32_data_heaps'] = esp32.idf_heap_info(esp32.HEAP_DATA)
except Exception as error:
    info['esp32_heap_error'] = repr(error)
print('PHASE1_PROBE=' + ujson.dumps(info))
'''


INVENTORY_CODE = r'''
import os, ujson
result = []
stack = ['/']
while stack:
    current = stack.pop()
    for entry in os.ilistdir(current):
        child = current.rstrip('/') + '/' + entry[0]
        if entry[1] & 0x4000:
            stack.append(child)
        else:
            result.append([child, os.stat(child)[6]])
result.sort()
print('PHASE1_INVENTORY=' + ujson.dumps(result))
'''


PROTECTED_DIGEST_CODE = r'''
import os, uhashlib, ujson
PATHS = (
    '/app.py', '/hdwconfig.py', '/device', '/files/user',
    '/state/selected_app.json',
)
def digest(root):
    value = uhashlib.sha256()
    stack = [root]
    while stack:
        path = stack.pop()
        try:
            entries = os.ilistdir(path)
        except OSError:
            entries = None
        if entries is None:
            value.update(path.encode())
            with open(path, 'rb') as stream:
                while True:
                    chunk = stream.read(1024)
                    if not chunk:
                        break
                    value.update(chunk)
        else:
            children = []
            for entry in entries:
                children.append(path.rstrip('/') + '/' + entry[0])
            children.sort(reverse=True)
            stack.extend(children)
    return ''.join('{:02x}'.format(byte) for byte in value.digest())
print('PROTECTED_DIGEST=' + ujson.dumps(
    dict((path, digest(path)) for path in PATHS)))
'''


DISPLAY_TOUCH_CODE = r'''
import time, ujson
from hdwconfig import display_drv, touch_drv
from graphics import FrameBuffer, RGB565
display_drv.disable_auto_byteswap(False)
display_drv.rotation = 90
width, height = display_drv.width, display_drv.height
buffer = bytearray(width * height * 2)
frame = FrameBuffer(buffer, width, height, RGB565)
def show(message, color=0xFFFF):
    frame.fill(0)
    scale = 2
    text_width = len(message) * 8 * scale
    frame.text(message, max(0, (width - text_width) // 2), (height - 16) // 2, color, scale)
    display_drv.blit_rect(buffer, 0, 0, width, height)
for name, color in [('RED', 0xF800), ('GREEN', 0x07E0), ('BLUE', 0x001F), ('WHITE', 0xFFFF), ('BLACK', 0x0000)]:
    display_drv.fill(color)
    print('COLOR=' + name)
    time.sleep_ms(1200)
results = []
for label in ('TOP LEFT', 'TOP RIGHT', 'BOTTOM RIGHT', 'BOTTOM LEFT', 'CENTER'):
    show('TOUCH ' + label)
    point = None
    deadline = time.ticks_add(time.ticks_ms(), 6000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        value = touch_drv.get_point()
        if value:
            point = value[0]
            break
        time.sleep_ms(50)
    results.append([label, point])
    if point:
        show('RECORDED', 0x07E0)
    else:
        show('NO TOUCH', 0xF800)
    time.sleep_ms(700)
show('TEST COMPLETE')
print('PHASE1_TOUCH=' + ujson.dumps({'width': width, 'height': height, 'results': results}))
'''


BUTTON_WATCH_CODE = r'''
import time
from machine import Pin
from hdwconfig import display_drv
buttons = [Pin(12, Pin.IN), Pin(0, Pin.IN)]
last = [button.value() for button in buttons]
display_drv.fill(0xFFFF)
print('BUTTON_START=' + str(last))
deadline = time.ticks_add(time.ticks_ms(), 15000)
changes = []
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    values = [button.value() for button in buttons]
    if values != last:
        changes.append([time.ticks_ms(), values])
        print('BUTTON_CHANGE=' + str(values))
        last = values
    time.sleep_ms(20)
display_drv.fill(0x0000)
print('BUTTON_CHANGES=' + str(changes))
'''


COLOR_TEST_CODE = r'''
import time
from hdwconfig import display_drv
display_drv.disable_auto_byteswap(False)
for name, color in [('RED', 0xF800), ('GREEN', 0x07E0), ('BLUE', 0x001F), ('WHITE', 0xFFFF), ('BLACK', 0x0000)]:
    display_drv.fill(color)
    print('COLOR=' + name)
    time.sleep_ms(1800)
'''


def connect(args):
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        return repl
    except Exception:
        repl.close()
        raise


def probe(args):
    repl = connect(args)
    try:
        output = repl.exec(PROBE_CODE, 20).decode("utf-8", "replace")
    finally:
        repl.close()
    marker = "PHASE1_PROBE="
    line = next(line for line in output.splitlines() if line.startswith(marker))
    data = json.loads(line[len(marker):])
    print(json.dumps(data, indent=2))


def inventory(repl):
    output = repl.exec(INVENTORY_CODE, 20).decode("utf-8", "replace")
    marker = "PHASE1_INVENTORY="
    line = next(line for line in output.splitlines() if line.startswith(marker))
    return json.loads(line[len(marker):])


def snapshot(args):
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    repl = connect(args)
    manifest = []
    try:
        files = inventory(repl)
        for index, (remote, expected_size) in enumerate(files, 1):
            relative = remote.lstrip("/")
            local = destination / Path(relative)
            resolved = local.resolve()
            if destination != resolved and destination not in resolved.parents:
                raise ValueError("Unsafe remote path: " + remote)
            local.parent.mkdir(parents=True, exist_ok=True)
            code = (
                "import ubinascii\n"
                "f=open(%r,'rb')\n"
                "while True:\n"
                " d=f.read(384)\n"
                " if not d: break\n"
                " print(ubinascii.b2a_base64(d).decode().strip())\n"
                "f.close()\n" % remote
            )
            encoded = repl.exec(code, max(args.timeout, expected_size / 4000 + 10))
            content = b"".join(base64.b64decode(line) for line in encoded.splitlines() if line)
            if len(content) != expected_size:
                raise IOError("Size mismatch for %s: %d != %d" % (remote, len(content), expected_size))
            local.write_bytes(content)
            manifest.append({
                "path": remote,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
            print("[%d/%d] backed up %s (%d bytes)" % (index, len(files), remote, expected_size), file=sys.stderr)
    finally:
        repl.close()
    (destination / "snapshot_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Backed up %d files to %s" % (len(manifest), destination))


def protected_digest(args):
    repl = connect(args)
    try:
        output = repl.exec(PROTECTED_DIGEST_CODE, 30)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def execute(args):
    repl = connect(args)
    try:
        output = repl.exec(args.code, args.timeout)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def display_touch(args):
    repl = connect(args)
    try:
        output = repl.exec(DISPLAY_TOUCH_CODE, 50)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def button_watch(args):
    repl = connect(args)
    try:
        output = repl.exec(BUTTON_WATCH_CODE, 25)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def color_test(args):
    repl = connect(args)
    try:
        output = repl.exec(COLOR_TEST_CODE, 20)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def preflight(args):
    base_url = args.base_url.rstrip("/")
    code = r'''
import os, ujson, urequests, uhashlib
from tarfile import TarFile
BASE = %r
ROOT = '/tmp/phase1_preflight'
NAMES = ('recovery.tar', 'defaults.tar', 'rootfiles.tar', 'tartlab.tar', 'tartlabutils.tar')
def kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0
def mkdirs(path):
    current = ''
    for part in path.strip('/').split('/'):
        if part:
            current += '/' + part
            if kind(current) == 0:
                os.mkdir(current)
def remove(path):
    if kind(path) == 2:
        for name in os.listdir(path):
            remove(path.rstrip('/') + '/' + name)
        os.rmdir(path)
    elif kind(path) == 1:
        os.remove(path)
def download(name):
    response = urequests.get(BASE + '/' + name)
    if response.status_code != 200:
        raise OSError('HTTP ' + str(response.status_code) + ' for ' + name)
    path = ROOT + '/' + name
    with open(path, 'wb') as stream:
        while True:
            chunk = response.raw.read(1024)
            if not chunk:
                break
            stream.write(chunk)
    response.close()
    return path
def digest(path):
    value = uhashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break
            value.update(chunk)
    return ''.join('{:02x}'.format(byte) for byte in value.digest())
def extract(path, destination):
    with open(path, 'rb') as stream:
        for info in TarFile(fileobj=stream):
            if 'PaxHeader' in info.name:
                continue
            target = destination + '/' + info.name
            mkdirs(target.rsplit('/', 1)[0])
            if info.type == 'file':
                with open(target, 'wb') as output:
                    while True:
                        chunk = info.subf.read(1024)
                        if not chunk:
                            break
                        output.write(chunk)
def python_files(path):
    result = []
    stack = [path]
    while stack:
        current = stack.pop()
        for entry in os.ilistdir(current):
            child = current.rstrip('/') + '/' + entry[0]
            if entry[1] & 0x4000:
                stack.append(child)
            elif child.endswith('.py'):
                result.append(child)
    return result
remove(ROOT)
mkdirs(ROOT)
manifest_path = download('manifest.json')
manifest = ujson.load(open(manifest_path))
expected = dict((item['file_name'], item['sha256']) for item in manifest)
compiled = []
for name in NAMES:
    path = download(name)
    actual = digest(path)
    if actual != expected[name]:
        raise ValueError('Hash mismatch for ' + name)
    destination = ROOT + '/stage/' + name[:-4]
    mkdirs(destination)
    extract(path, destination)
    for python_path in python_files(destination):
        with open(python_path, 'r') as source:
            compile(source.read(), python_path, 'exec')
        compiled.append(python_path)
print('PREFLIGHT_HASHED=' + str(len(NAMES)))
print('PREFLIGHT_COMPILED=' + str(len(compiled)))
print('PREFLIGHT_OK=True')
''' % base_url
    repl = connect(args)
    try:
        output = repl.exec(code, 120)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def ota_install(args):
    base_url = args.base_url.rstrip("/")
    version = args.version
    code = r'''
import ujson, urequests, uasyncio as asyncio
from tartlabutils import updater
BASE = %r
VERSION = %r

response = urequests.get(BASE + '/manifest.json')
if response.status_code != 200:
    raise OSError('HTTP ' + str(response.status_code) + ' for manifest.json')
manifest = response.json()
response.close()

assets = [{
    'name': 'manifest.json',
    'size': 4096,
    'browser_download_url': BASE + '/manifest.json',
}]
for package in manifest:
    assets.append({
        'name': package['file_name'],
        'size': package['archive_size'],
        'browser_download_url': BASE + '/' + package['file_name'],
    })

async def local_release(repo):
    return assets, VERSION

def progress(message, step, total):
    print('OTA_PROGRESS=%%d/%%d %%s' %% (step, total, message))

updater.check_for_update = local_release
repos_path = updater.REPOS_FILE
with open(repos_path, 'r') as stream:
    repos = ujson.load(stream)
target = None
for candidate in repos['list']:
    if candidate.get('name') == 'TartLab':
        target = candidate
        break
if target is None:
    raise ValueError('TartLab repository entry not found')

result = asyncio.run(updater.update_packages(target, progress))
installed = result == getattr(updater, 'UPDATE_INSTALLED', True)
if installed:
    with open(repos_path, 'w') as stream:
        ujson.dump(repos, stream)
    settings = updater.load_settings()
    settings['STARTUP_MODE'] = 'IDE'
    updater.save_settings(settings)
print('OTA_VERSION=' + str(target.get('installed_version')))
print('OTA_RESULT=' + str(result))
print('OTA_OK=' + str(installed))
''' % (base_url, version)
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 300))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def fault_update(args):
    base_url = args.base_url.rstrip("/")
    code = r'''
import os, ujson, uasyncio as asyncio
from tartlabutils import updater
BASE = %r
MANIFEST = %r
PACKAGE = %r
PACKAGE_SIZE = %d
VERSION = %r
FORCE_WRITE = %r
SIGNAL_PACKAGE = %r
SIGNAL_MARKER = %r

assets = [
    {'name': 'manifest.json', 'size': 1024,
     'browser_download_url': BASE + '/' + MANIFEST},
    {'name': PACKAGE, 'size': PACKAGE_SIZE,
     'browser_download_url': BASE + '/' + PACKAGE},
]

async def local_release(repo):
    return assets, VERSION

async def forced_write_error(*unused_args, **unused_kwargs):
    raise OSError('forced write error')

def progress(message, step, total):
    print('FAULT_PROGRESS=%%d/%%d %%s' %% (step, total, message))

updater.check_for_update = local_release
if FORCE_WRITE:
    updater.update_folder = forced_write_error
if SIGNAL_PACKAGE:
    original_download = updater.download_asset
    async def signaled_download(url, target_file):
        if target_file.endswith('/' + SIGNAL_PACKAGE):
            from hdwconfig import display_drv
            display_drv.disable_auto_byteswap(False)
            display_drv.fill(0xffff)
            print('POWER_DOWNLOAD_SIGNAL=True')
        return await original_download(url, target_file)
    updater.download_asset = signaled_download
if SIGNAL_MARKER:
    original_begin_update = updater.begin_update
    def signaled_begin_update(*values):
        result = original_begin_update(*values)
        from hdwconfig import display_drv
        import utime
        display_drv.disable_auto_byteswap(False)
        display_drv.fill(0xffff)
        print('POWER_MARKER_SIGNAL=True')
        while True:
            utime.sleep_ms(250)
        return result
    updater.begin_update = signaled_begin_update
with open(updater.REPOS_FILE, 'r') as stream:
    repos = ujson.load(stream)
target = next(item for item in repos['list'] if item.get('name') == 'TartLab')
result = asyncio.run(updater.update_packages(target, progress))
with open(updater.REPOS_FILE, 'r') as stream:
    committed = ujson.load(stream)
try:
    with open('/state/update.json', 'r') as stream:
        marker = ujson.load(stream)
except Exception:
    marker = None
try:
    target_kind = 1 if os.stat('/phase1_fault_target')[0] & 0x8000 else 2
except OSError:
    target_kind = 0
print('FAULT_RESULT=' + str(result))
print('FAULT_COMMITTED=' + str(committed['list'][0].get('installed_version')))
print('FAULT_MARKER_STATUS=' + str(marker.get('status') if marker else 'none'))
print('FAULT_TARGET_KIND=' + str(target_kind))
''' % (base_url, args.manifest, args.package, args.package_size,
       args.version, args.force_write, args.signal_package, args.signal_marker)
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 120))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def wifi_update(args):
    credentials = json.loads(args.credentials_file.read_text(encoding="utf-8"))
    ssid = credentials.get("ssid")
    password = credentials.get("password")
    if not isinstance(ssid, str) or not ssid or not isinstance(password, str):
        raise ValueError("Credential file must contain a non-empty ssid and string password")
    code = r'''
import os, time, ujson, network
SSID = %r
PASSWORD = %r

def kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0

def write_json(path, value):
    temporary = path + '.wifi_tmp'
    backup = path + '.wifi_bak'
    for stale in (temporary, backup):
        if kind(stale) == 1:
            os.remove(stale)
    with open(temporary, 'w') as stream:
        ujson.dump(value, stream)
    os.rename(path, backup)
    try:
        os.rename(temporary, path)
    except Exception:
        os.rename(backup, path)
        raise
    os.remove(backup)

updated = 0
for path in ('/state/settings.json', '/settings.json'):
    if kind(path) != 1:
        continue
    with open(path, 'r') as stream:
        settings = ujson.load(stream)
    names = list(settings.get('wifi_ssids', []))
    passwords = list(settings.get('wifi_passwords', []))
    while len(passwords) < len(names):
        passwords.append('')
    if SSID in names:
        index = names.index(SSID)
        names.pop(index)
        passwords.pop(index)
    names.insert(0, SSID)
    passwords.insert(0, PASSWORD)
    settings['wifi_ssids'] = names
    settings['wifi_passwords'] = passwords
    write_json(path, settings)
    updated += 1

station = network.WLAN(network.STA_IF)
station.active(True)
if station.isconnected():
    station.disconnect()
station.connect(SSID, PASSWORD)
for unused in range(60):
    if station.isconnected():
        break
    time.sleep_ms(250)
print('WIFI_SETTINGS_UPDATED=' + str(updated))
print('WIFI_CONNECTED=' + str(station.isconnected()))
if station.isconnected():
    print('WIFI_IP=' + station.ifconfig()[0])
''' % (ssid, password)
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 30))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def recovery_install(args):
    base_url = args.base_url.rstrip("/")
    code = r'''
import sys, ujson, urequests, network
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery
import recovery_update
BASE = %r
VERSION = %r

station = network.WLAN(network.STA_IF)
if not station.isconnected():
    station = recovery._connect_to_wifi()
print('RECOVERY_JOINED_NETWORK=' + str(station.isconnected()))

response = urequests.get(BASE + '/manifest.json')
if response.status_code != 200:
    raise OSError('HTTP ' + str(response.status_code) + ' for manifest.json')
manifest = response.json()
response.close()
assets = [{
    'name': 'manifest.json',
    'browser_download_url': BASE + '/manifest.json',
}]
for package in manifest:
    assets.append({
        'name': package['file_name'],
        'browser_download_url': BASE + '/' + package['file_name'],
    })
release = {'tag_name': VERSION, 'assets': assets}
recovery_update._release = lambda unused_repo: release
installed = recovery_update.update_to_latest(
    lambda message: print('RECOVERY_PROGRESS=' + message))
print('RECOVERY_INSTALLED=' + str(installed))
''' % (base_url, args.version)
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 300))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def recovery_resume(args):
    code = r'''
import sys
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery_update
installed = recovery_update.resume_staged_update(
    lambda message: print('RECOVERY_RESUME=' + message))
print('RECOVERY_RESUMED_VERSION=' + str(installed))
'''
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 300))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def serial_install(args):
    release_dir = args.release_dir.resolve()
    manifest_path = release_dir / "manifest.json"
    checksums_path = release_dir / "checksums.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    files = [manifest_path]
    for package in manifest:
        name = package.get("file_name")
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Unsafe package name in manifest: %r" % name)
        path = release_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        files.append(path)
    for path in files:
        expected = checksums.get(path.name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if not isinstance(expected, str) or actual != expected:
            raise ValueError("Release checksum mismatch: " + path.name)

    prepare_code = r'''
import os
ROOT = '/tmp/recovery'
def kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0
def remove(path):
    if kind(path) == 2:
        for name in os.listdir(path):
            remove(path.rstrip('/') + '/' + name)
        os.rmdir(path)
    elif kind(path) == 1:
        os.remove(path)
remove(ROOT)
if kind('/tmp') == 0:
    os.mkdir('/tmp')
os.mkdir(ROOT)
print('SERIAL_STAGE_READY=True')
'''
    repl = connect(args)
    try:
        output = repl.exec(prepare_code, 30)
        sys.stdout.buffer.write(output)
        for index, path in enumerate(files, 1):
            content = path.read_bytes()
            expected = checksums[path.name]
            print("Staging %d/%d %s (%d bytes)" % (
                index, len(files), path.name, len(content)), flush=True)
            output = repl.stream_file(
                "/tmp/recovery/" + path.name, content, expected,
                max(args.timeout, 300))
            sys.stdout.buffer.write(output)

        install_code = r'''
import sys, ujson
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery_update
VERSION = %r
manifest = recovery_update._read_json(
    recovery_update.TEMP_DIR + '/manifest.json', None)
recovery_update._validate_manifest(manifest)
for package in manifest:
    path = recovery_update.TEMP_DIR + '/' + package['file_name']
    if recovery_update._kind(path) != 1:
        raise ValueError('Staged package missing: ' + package['file_name'])
    if recovery_update._sha256(path) != package['sha256']:
        raise ValueError('Staged package hash mismatch: ' + package['file_name'])
    recovery_update._tar_members(path, package['target'], False)
if recovery_update._required_install_space(manifest) > recovery_update._free_space():
    raise OSError('Not enough disk space to extract release safely')
repos_path = recovery_update.STATE_REPOS
if recovery_update._kind(repos_path) != 1:
    repos_path = recovery_update.LEGACY_REPOS
repos = recovery_update._read_json(repos_path, {})
tartlab = recovery_update._tartlab_repo(repos)
if tartlab is None:
    raise ValueError('TartLab release state not found')
installed = recovery_update._install_verified_packages(
    tartlab, VERSION, manifest,
    lambda message: print('SERIAL_INSTALL=' + message))
from tartlabutils.state import read_json, write_json, SETTINGS_FILE
settings = read_json(SETTINGS_FILE, {})
settings['STARTUP_MODE'] = 'IDE'
write_json(SETTINGS_FILE, settings)
print('SERIAL_INSTALLED_VERSION=' + str(installed))
''' % args.version
        output = repl.exec(install_code, max(args.timeout, 300))
        sys.stdout.buffer.write(output)
    finally:
        repl.close()


def reset_device(args):
    repl = connect(args)
    try:
        payload = b"import machine\nmachine.reset()\n\x04"
        repl.serial.write(payload)
        time.sleep(0.5)
    finally:
        repl.close()
    print("Reset requested on %s" % args.port)


def guided_app_reset(args):
    repl = connect(args)
    try:
        code = (
            "import time, machine\n"
            "from hdwconfig import display_drv\n"
            "display_drv.fill(0xFFFF)\n"
            "time.sleep(5)\n"
            "display_drv.fill(0)\n"
            "machine.reset()\n"
        ).encode("utf-8")
        for offset in range(0, len(code), 128):
            repl.serial.write(code[offset:offset + 128])
            time.sleep(0.01)
        repl.serial.write(b"\x04")
        time.sleep(7)
    finally:
        repl.close()
    print("Guided APP reset completed on %s" % args.port)


def press_detected_app_reset(args):
    repl = connect(args)
    try:
        code = (
            "import time, machine\n"
            "from machine import Pin\n"
            "from hdwconfig import display_drv\n"
            "button=Pin(12,Pin.IN)\n"
            "display_drv.fill(0xFFFF)\n"
            "print('WAITING_FOR_BUTTON')\n"
            "while button.value()!=0: time.sleep_ms(20)\n"
            "print('BUTTON_DETECTED')\n"
            "machine.reset()\n"
        ).encode("utf-8")
        for offset in range(0, len(code), 128):
            repl.serial.write(code[offset:offset + 128])
            time.sleep(0.01)
        repl.serial.write(b"\x04")
        repl._read_until(b"BUTTON_DETECTED", 45)
        time.sleep(10)
    finally:
        repl.close()
    print("Press-detected APP reset completed on %s" % args.port)


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--port", default="COM6")
    result.add_argument("--baudrate", type=int, default=115200)
    result.add_argument("--timeout", type=int, default=15)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("probe").set_defaults(func=probe)
    commands.add_parser("protected-digest").set_defaults(func=protected_digest)
    commands.add_parser("reset").set_defaults(func=reset_device)
    commands.add_parser("guided-app-reset").set_defaults(func=guided_app_reset)
    commands.add_parser("press-detected-app-reset").set_defaults(func=press_detected_app_reset)
    commands.add_parser("display-touch").set_defaults(func=display_touch)
    commands.add_parser("button-watch").set_defaults(func=button_watch)
    commands.add_parser("color-test").set_defaults(func=color_test)
    preflight_parser = commands.add_parser("preflight")
    preflight_parser.add_argument("--base-url", required=True)
    preflight_parser.set_defaults(func=preflight)
    ota_parser = commands.add_parser("ota-install")
    ota_parser.add_argument("--base-url", required=True)
    ota_parser.add_argument("--version", default="phase1-hwtest")
    ota_parser.set_defaults(func=ota_install)
    fault_parser = commands.add_parser("fault-update")
    fault_parser.add_argument("--base-url", required=True)
    fault_parser.add_argument("--manifest", required=True)
    fault_parser.add_argument("--package", required=True)
    fault_parser.add_argument("--package-size", type=int, required=True)
    fault_parser.add_argument("--version", required=True)
    fault_parser.add_argument("--force-write", action="store_true")
    fault_parser.add_argument("--signal-package")
    fault_parser.add_argument("--signal-marker", action="store_true")
    fault_parser.set_defaults(func=fault_update)
    wifi_parser = commands.add_parser("wifi-update")
    wifi_parser.add_argument("--credentials-file", type=Path, required=True)
    wifi_parser.set_defaults(func=wifi_update)
    recovery_parser = commands.add_parser("recovery-install")
    recovery_parser.add_argument("--base-url", required=True)
    recovery_parser.add_argument("--version", required=True)
    recovery_parser.set_defaults(func=recovery_install)
    commands.add_parser("recovery-resume").set_defaults(func=recovery_resume)
    serial_parser = commands.add_parser("serial-install")
    serial_parser.add_argument("--release-dir", type=Path, required=True)
    serial_parser.add_argument("--version", required=True)
    serial_parser.set_defaults(func=serial_install)
    snapshot_parser = commands.add_parser("snapshot")
    snapshot_parser.add_argument("--output", type=Path, required=True)
    snapshot_parser.set_defaults(func=snapshot)
    execute_parser = commands.add_parser("exec")
    execute_parser.add_argument("--code", required=True)
    execute_parser.set_defaults(func=execute)
    return result


if __name__ == "__main__":
    options = parser().parse_args()
    options.func(options)
