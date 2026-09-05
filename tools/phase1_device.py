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
        last_error = None
        for unused_attempt in range(2):
            self.serial.write(b"\r\x03\x03")
            time.sleep(0.2)
            self.serial.reset_input_buffer()
            self.serial.write(b"\r\x01")
            try:
                self._read_until(b"raw REPL; CTRL-B to exit\r\n>", 5)
                return
            except TimeoutError as error:
                # A running TartLab app can finish its Ctrl-C teardown just
                # after the first prompt deadline. Retrying the transition on
                # the same open port avoids requiring a sacrificial command.
                last_error = error
        raise last_error

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


PYDEVICES_BENCHMARK_CODE = r'''
import gc, os, time, ujson
from hdwconfig import display_drv, touch_drv

def class_name(value):
    value_type = type(value)
    return getattr(value_type, '__module__', '') + '.' + getattr(value_type, '__name__', '')

def timed(call, count):
    values = []
    for unused in range(count):
        start = time.ticks_us()
        call()
        values.append(time.ticks_diff(time.ticks_us(), start))
    return values

display_drv.rotation = 90
display_drv.disable_auto_byteswap(False)
width, height = display_drv.width, display_drv.height
gc.collect()
heap_before_buffer = gc.mem_free()
colors = [0x0000, 0xF800, 0x07E0, 0x001F, 0xFFFF, 0x0000]
color_index = [0]
def fill_next():
    display_drv.fill(colors[color_index[0]])
    color_index[0] = (color_index[0] + 1) % len(colors)
fill_us = timed(fill_next, len(colors))
buffer = bytearray(width * height * 2)
gc.collect()
heap_with_buffer = gc.mem_free()
blit_us = timed(lambda: display_drv.blit_rect(buffer, 0, 0, width, height), 6)
touch_us = []
touch_results = []
for unused in range(20):
    start = time.ticks_us()
    value = touch_drv.get_point()
    touch_us.append(time.ticks_diff(time.ticks_us(), start))
    if value:
        touch_results.append(value)
    time.sleep_ms(10)
del buffer
gc.collect()
filesystem = os.statvfs('/')
result = {
    'display_class': class_name(display_drv),
    'touch_class': class_name(touch_drv),
    'width': width,
    'height': height,
    'color_depth': display_drv.color_depth,
    'requires_byteswap': display_drv.requires_byteswap,
    'fill_us': fill_us,
    'full_frame_blit_us': blit_us,
    'touch_poll_us': touch_us,
    'touch_results': touch_results,
    'heap_before_buffer': heap_before_buffer,
    'heap_with_buffer': heap_with_buffer,
    'heap_after': gc.mem_free(),
    'filesystem_free_bytes': filesystem[0] * filesystem[3],
}
display_drv.fill(0)
print('PYDEVICES_BENCHMARK=' + ujson.dumps(result))
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


def pydevices_benchmark(args):
    repl = connect(args)
    try:
        output = repl.exec(PYDEVICES_BENCHMARK_CODE, 60)
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def boot_timing(args):
    repl = connect(args)
    markers = (
        b"System startup",
        b"Starting IDE",
        b"Scanning for WiFi networks...",
        b"HEALTHY mode=IDE",
    )
    found = {}
    captured = bytearray()
    started = time.monotonic()
    port = None
    try:
        repl.serial.write(b"import machine\nmachine.reset()\n\x04")
        repl.close()
        repl = None
        deadline = started + args.timeout
        while len(found) < len(markers) and time.monotonic() < deadline:
            if port is None:
                try:
                    port = serial.Serial(
                        args.port, args.baudrate, timeout=0.1,
                        write_timeout=2, dsrdtr=False, rtscts=False)
                except serial.SerialException:
                    time.sleep(0.05)
                    continue
            try:
                waiting = port.in_waiting
                chunk = port.read(waiting or 1)
            except serial.SerialException:
                port.close()
                port = None
                time.sleep(0.05)
                continue
            if not chunk:
                continue
            captured.extend(chunk)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            for marker in markers:
                if marker not in found and marker in captured:
                    found[marker] = elapsed_ms
    finally:
        if repl is not None:
            repl.close()
        if port is not None:
            port.close()
    if len(found) != len(markers):
        missing = [marker.decode() for marker in markers if marker not in found]
        raise TimeoutError("Boot markers not observed: %r" % missing)
    print(json.dumps({
        "reset_to_system_startup_ms": found[markers[0]],
        "reset_to_ide_start_ms": found[markers[1]],
        "reset_to_wifi_scan_ms": found[markers[2]],
        "reset_to_ide_healthy_ms": found[markers[3]],
    }, indent=2))


def interrupt_trace(args):
    port = serial.Serial(
        args.port, args.baudrate, timeout=0.1, write_timeout=2,
        dsrdtr=False, rtscts=False)
    captured = bytearray()
    try:
        port.reset_input_buffer()
        port.write(b"\x03")
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            waiting = port.in_waiting
            chunk = port.read(waiting or 1)
            if chunk:
                captured.extend(chunk)
                if b">>> " in captured or b"raw REPL" in captured:
                    break
    finally:
        port.close()
    sys.stdout.write(captured.decode("utf-8", "replace"))


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
    manifest_name = args.manifest
    code = r'''
import ujson, urequests, uasyncio as asyncio
from tartlabutils import updater
BASE = %r
VERSION = %r
MANIFEST_NAME = %r

response = urequests.get(BASE + '/' + MANIFEST_NAME)
if response.status_code != 200:
    raise OSError('HTTP ' + str(response.status_code) + ' for ' + MANIFEST_NAME)
document = response.json()
response.close()
if MANIFEST_NAME == 'modern-manifest.json':
    manifest = document.get('packages') if isinstance(document, dict) else None
else:
    manifest = document
if not isinstance(manifest, list) or not manifest:
    raise ValueError('Invalid local release manifest')

assets = [{
    'name': MANIFEST_NAME,
    'size': 4096,
    'browser_download_url': BASE + '/' + MANIFEST_NAME,
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
''' % (base_url, version, manifest_name)
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
LOW_SPACE = %r

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

original_check_for_update = updater.check_for_update
original_download = updater.download_asset
original_free_space = updater._free_space
original_update_folder = updater.update_folder
original_begin_update = updater.begin_update
updater.check_for_update = local_release
download_count = [0]
async def counted_download(url, target_file):
    download_count[0] += 1
    return await original_download(url, target_file)
updater.download_asset = counted_download
if LOW_SPACE == 'pre':
    updater._free_space = lambda: 0
elif LOW_SPACE == 'post':
    free_space_calls = [0]
    def post_staging_low_space():
        free_space_calls[0] += 1
        return original_free_space() if free_space_calls[0] == 1 else 0
    updater._free_space = post_staging_low_space
if FORCE_WRITE:
    updater.update_folder = forced_write_error
if SIGNAL_PACKAGE:
    signaled_original_download = updater.download_asset
    async def signaled_download(url, target_file):
        if target_file.endswith('/' + SIGNAL_PACKAGE):
            from hdwconfig import display_drv
            display_drv.disable_auto_byteswap(False)
            display_drv.fill(0xffff)
            print('POWER_DOWNLOAD_SIGNAL=True')
        return await signaled_original_download(url, target_file)
    updater.download_asset = signaled_download
if SIGNAL_MARKER:
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
try:
    result = asyncio.run(updater.update_packages(target, progress))
finally:
    updater.check_for_update = original_check_for_update
    updater.download_asset = original_download
    updater._free_space = original_free_space
    updater.update_folder = original_update_folder
    updater.begin_update = original_begin_update
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
print('FAULT_DOWNLOADS=' + str(download_count[0]))
''' % (base_url, args.manifest, args.package, args.package_size,
       args.version, args.force_write, args.signal_package, args.signal_marker,
       args.low_space)
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
import sys, ujson, urequests, network, time
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery
import recovery_update
BASE = %r
VERSION = %r
SIGNAL_PACKAGE = %r

def progress(message):
    print('RECOVERY_PROGRESS=' + message)
    if SIGNAL_PACKAGE and message == 'Installing ' + SIGNAL_PACKAGE:
        for path in ('/lib/pydevices', '/configs'):
            if path not in sys.path:
                sys.path.insert(0, path)
        from hdwconfig import display_drv
        display_drv.disable_auto_byteswap(False)
        display_drv.fill(0xffff)
        print('RECOVERY_POWER_SIGNAL=' + SIGNAL_PACKAGE)
        while True:
            time.sleep_ms(250)

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
installed = recovery_update.update_to_latest(progress)
print('RECOVERY_INSTALLED=' + str(installed))
''' % (base_url, args.version, args.signal_package)
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 300))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


def _recovery_browser_code(args):
    base_url = args.base_url.rstrip("/")
    return r'''
import sys, urequests
if '/recovery' not in sys.path:
    sys.path.insert(0, '/recovery')
import recovery
import recovery_update
BASE = %r
VERSION = %r
MANIFEST_NAME = %r
STAGE_BEFORE_BROWSER = %r

station = recovery._connect_to_wifi()
print('RECOVERY_BROWSER_STATION_IP=' + station.ifconfig()[0])
response = urequests.get(BASE + '/' + MANIFEST_NAME)
if response.status_code != 200:
    raise OSError('HTTP ' + str(response.status_code) + ' for ' + MANIFEST_NAME)
document = response.json()
response.close()
if isinstance(document, dict):
    packages = document.get('packages')
else:
    packages = document
if not isinstance(packages, list) or not packages:
    raise ValueError('Recovery qualification manifest has no packages')
assets = [{
    'name': MANIFEST_NAME,
    'browser_download_url': BASE + '/' + MANIFEST_NAME,
}]
for package in packages:
    assets.append({
        'name': package['file_name'],
        'browser_download_url': BASE + '/' + package['file_name'],
    })
release = {'tag_name': VERSION, 'assets': assets}
recovery_update._release = lambda unused_repo: release
if STAGE_BEFORE_BROWSER:
    repos_path = recovery_update.STATE_REPOS
    if recovery_update._kind(repos_path) != 1:
        repos_path = recovery_update.LEGACY_REPOS
    repos = recovery_update._read_json(repos_path, {})
    tartlab = recovery_update._tartlab_repo(repos)
    if tartlab is None:
        raise ValueError('TartLab release state not found')
    if recovery_update._kind(recovery_update.TEMP_DIR) == 0:
        recovery_update._mkdirs(recovery_update.TEMP_DIR)
    manifest_path = recovery_update.TEMP_DIR + '/' + MANIFEST_NAME
    recovery_update._download_verified(
        BASE + '/' + MANIFEST_NAME, manifest_path)
    document = recovery_update._read_json(manifest_path, None)
    packages = recovery_update._manifest_packages(document, tartlab, VERSION)
    for package in packages:
        path = recovery_update.TEMP_DIR + '/' + package['file_name']
        recovery_update._download_verified(
            BASE + '/' + package['file_name'], path, package['sha256'])
        recovery_update._tar_members(path, package['target'], False)
    if recovery_update._required_install_space(packages) > recovery_update._free_space():
        raise OSError('Not enough disk space to extract release safely')
    recovery_update._write_json(recovery_update.UPDATE_STATE, {
        'schema': 1,
        'status': 'installing',
        'repos': [{
            'name': 'TartLab',
            'previous_version': tartlab['installed_version'],
            'pending_version': VERSION,
        }],
        'source': 'recovery',
        'completed_packages': [],
    })
    recovery_update.update_to_latest = recovery_update.resume_staged_update
    print('RECOVERY_BROWSER_STAGED=True')
print('RECOVERY_BROWSER_READY=True')
recovery.run('qualification_corrective_update')
''' % (base_url, args.version, args.manifest, args.stage_before_browser)


def recovery_browser(args):
    """Run the real recovery page with a local, authenticated release adapter."""
    code = _recovery_browser_code(args)
    repl = connect(args)
    completed = False
    try:
        payload = code.encode("utf-8")
        for offset in range(0, len(payload), 128):
            repl.serial.write(payload[offset:offset + 128])
            time.sleep(0.01)
        repl.serial.write(b"\x04")
        output = repl._read_until(
            b"RECOVERY_BROWSER_READY=True", max(args.timeout, 60))
        if not output.startswith(b"OK"):
            raise RuntimeError("Raw REPL rejected recovery browser command")
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()

        deadline = time.monotonic() + max(args.timeout, 300)
        tail = bytearray(output[-512:])
        while time.monotonic() < deadline:
            try:
                waiting = repl.serial.in_waiting
                chunk = repl.serial.read(waiting or 1)
            except serial.SerialException:
                break
            if not chunk:
                continue
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            tail.extend(chunk)
            if len(tail) > 1024:
                del tail[:-1024]
            if b"Recovery installed " in tail and \
                    b"boot health is pending" in tail:
                completed = True
                break
        if not completed:
            raise TimeoutError("Recovery browser session ended before update completion")
    finally:
        repl.close()


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


def recovery_retry(args):
    """Clear the durable recovery failure count and request a normal boot."""

    repl = connect(args)
    try:
        output = repl.exec(
            "import sys\n"
            "if '/recovery' not in sys.path: sys.path.insert(0, '/recovery')\n"
            "import recovery\n"
            "recovery._retry()\n"
            "print('RECOVERY_RETRY=True')\n",
            max(args.timeout, 30))
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        repl.serial.write(b"import machine\nmachine.reset()\n\x04")
        time.sleep(0.5)
    finally:
        repl.close()
    print("Recovery retry requested on %s" % args.port)


def update_status(args):
    """Read durable update/repository state without initializing the display."""

    code = r'''
import os, ujson
def read(path, default):
    try:
        return ujson.load(open(path))
    except Exception:
        return default
def kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0
print('UPDATE_STATUS=' + ujson.dumps({
    'boot': read('/state/boot.json', {}),
    'update': read('/state/update.json', None),
    'repos': read('/state/repos.json', {}),
    'temporary_root_kind': kind('/tmp'),
    'temporary_root_entries': sorted(os.listdir('/tmp'))
        if kind('/tmp') == 2 else [],
    'recovery_stage_kind': kind('/tmp/recovery'),
    'recovery_stage_entries': sorted(os.listdir('/tmp/recovery'))
        if kind('/tmp/recovery') == 2 else [],
    'qualification_stage_kind': kind('/qualification/modern-update'),
}))
'''
    repl = connect(args)
    try:
        output = repl.exec(code, max(args.timeout, 30))
    finally:
        repl.close()
    sys.stdout.buffer.write(output)


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
    commands.add_parser("recovery-retry").set_defaults(func=recovery_retry)
    commands.add_parser("update-status").set_defaults(func=update_status)
    commands.add_parser("guided-app-reset").set_defaults(func=guided_app_reset)
    commands.add_parser("press-detected-app-reset").set_defaults(func=press_detected_app_reset)
    commands.add_parser("display-touch").set_defaults(func=display_touch)
    commands.add_parser("button-watch").set_defaults(func=button_watch)
    commands.add_parser("color-test").set_defaults(func=color_test)
    commands.add_parser("pydevices-benchmark").set_defaults(
        func=pydevices_benchmark)
    commands.add_parser("boot-timing").set_defaults(func=boot_timing)
    commands.add_parser("interrupt-trace").set_defaults(func=interrupt_trace)
    preflight_parser = commands.add_parser("preflight")
    preflight_parser.add_argument("--base-url", required=True)
    preflight_parser.set_defaults(func=preflight)
    ota_parser = commands.add_parser("ota-install")
    ota_parser.add_argument("--base-url", required=True)
    ota_parser.add_argument("--version", default="phase1-hwtest")
    ota_parser.add_argument(
        "--manifest", choices=("manifest.json", "modern-manifest.json"),
        default="manifest.json")
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
    fault_parser.add_argument("--low-space", choices=("pre", "post"))
    fault_parser.set_defaults(func=fault_update)
    wifi_parser = commands.add_parser("wifi-update")
    wifi_parser.add_argument("--credentials-file", type=Path, required=True)
    wifi_parser.set_defaults(func=wifi_update)
    recovery_parser = commands.add_parser("recovery-install")
    recovery_parser.add_argument("--base-url", required=True)
    recovery_parser.add_argument("--version", required=True)
    recovery_parser.add_argument(
        "--signal-package",
        help="pause with a white display before installing this package")
    recovery_parser.set_defaults(func=recovery_install)
    recovery_browser_parser = commands.add_parser("recovery-browser")
    recovery_browser_parser.add_argument("--base-url", required=True)
    recovery_browser_parser.add_argument("--version", required=True)
    recovery_browser_parser.add_argument(
        "--manifest", choices=("manifest.json", "modern-manifest.json"),
        default="manifest.json")
    recovery_browser_parser.add_argument("--stage-before-browser", action="store_true")
    recovery_browser_parser.set_defaults(func=recovery_browser)
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
