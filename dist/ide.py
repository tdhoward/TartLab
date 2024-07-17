import sys
import gc
import network
import os
import ujson
import utime
import random
import uasyncio as asyncio
import io

from ahttpserver import HTTPResponse, HTTPServer
from ahttpserver.sse import EventSource
from ahttpserver.servefile import serve_file

network.hostname('tartlab')  # sets up tartlab.local on mDNS

USER_BASE_DIR = '/files/user'

def file_exists(filepath):
    try:
        stat = os.stat(filepath)
        return stat[0] & 0x8000 == 0x8000  # Check if it's a regular file
    except OSError:
        return False

class CaptureOutput(io.IOBase):
    def __init__(self):
        self.buffer = []

    def write(self, data):
        self.buffer.append(data.decode("utf-8"))
        return len(data)
    
    def get_output(self):
        return ''.join(self.buffer)

    def clear(self):
        self.buffer = []


# This isn't meant to be fast, just usable
replGlobals = {}
def pseudoREPL(source):
    global replGlobals
    try:
        # Capture the output
        capture = CaptureOutput()
        os.dupterm(capture)
        try:
            # Try to evaluate the input as an expression
            result = eval(source, replGlobals)
            if result is not None:
                print(result)
        except (SyntaxError, NameError):
            # If eval fails, fall back to exec
            try:
                exec(source, replGlobals)
            except Exception as e:
                print(f"Error: {e}")
        # Stop capturing
        os.dupterm(None)
        cap = capture.get_output()
        capture.clear()
        return cap
    except Exception as e:
        return f"Error: {e}"

sta_if = network.WLAN(network.STA_IF) # create station interface
ap_if = network.WLAN(network.AP_IF) #  create access-point interface


'''
sta_if.status()

network.STAT_IDLE               1000
network.STAT_CONNECTING         1001
network.STAT_GOT_IP             1010
network.STAT_BEACON_TIMEOUT     200
network.STAT_NO_AP_FOUND        201
network.STAT_WRONG_PASSWORD     202
network.STAT_ASSOC_FAIL         203
network.STAT_HANDSHAKE_TIMEOUT  204

Maybe eventually change this to poll for RSSI. Warn users when Wifi is weak.

'''

def scan_for_wifi(ssids: list[str], keys: list[str]):
    print("Scanning for WiFi networks...")
    networks = sta_if.scan()  # returns list of (ssid, bssid, channel, RSSI, security, hidden)
    networks.sort(key=lambda n:n[3], reverse=True)  # sort networks by RSSI
    for nwork in networks:
        network_name = nwork[0].decode('utf-8')
        for idx, s in enumerate(ssids):
            if s == network_name:
                ssid = s
                key = keys[idx]
                return True, ssid, key
    return False, "", ""


def connect_to_wifi(ssids: list[str], keys: list[str]):
    if len(ssids) == 0:
        return "0.0.0.0"
    retries = 20
    try:
        ap_if.disconnect()
        sta_if.disconnect()
    except:
        pass
    ap_if.active(False) #  de-activate the interfaces
    sta_if.active(False)
    utime.sleep(1)
    sta_if.active(True)
    scan_retries = 3
    foundSsid = False
    ssid = ""
    key = ""
    while not foundSsid and scan_retries > 0:
        foundSsid, ssid, key = scan_for_wifi(ssids, keys)
        scan_retries -= 1
    if not foundSsid:
        print(f'Could not find an accessible WiFi network in scan!')
        return "0.0.0.0"
    print(f'Found {ssid} network in scan.')
    if not sta_if.isconnected():
        print(f'Connecting to {ssid} network...')
        sta_if.active(True)
        sta_if.connect(ssid, key)

        # TODO: instead of just blindly waiting for a timeout, check for sta_if.status() and react accordingly.
        while (retries > 0):
            if (sta_if.isconnected()):
                print(sta_if.ifconfig())
                return sta_if.ifconfig()[0]
            print ('.', end = '')
            utime.sleep(1)
            retries -= 1

        if (retries == 0):
            sta_if.disconnect()  #  disconnect or you get errors
            sta_if.active(False)
            print("Unable to connect!")
            print(sta_if.ifconfig())
            return "0.0.0.0"
    else:
        print("Already connected!")
        print(sta_if.ifconfig())
        return sta_if.ifconfig()[0]


# Function to generate a random AP name (currently not used)
def generate_ap_name():
    adjective = random.choice(["Adventurous", "Brave", "Clever", "Daring", "Energetic", "Friendly", "Gentle", "Happy", "Inquisitive", "Jolly", "Kind", "Lively", "Mighty", "Noble", "Optimistic", "Playful", "Quick", "Radiant", "Strong", "Wise"])
    animal = random.choice(["Antelope", "Bear", "Cat", "Dolphin", "Elephant", "Fox", "Giraffe", "Horse", "Iguana", "Jaguar", "Koala", "Lion", "Monkey", "Narwhal", "Owl", "Penguin", "Quail", "Rabbit", "Squirrel", "Tiger"])
    number = random.randint(10, 99)
    return f"Py{adjective}{animal}{number}"


def create_soft_ap(ap_name):
    # Initialize the soft AP with the AP name from settings
    print(f'Creating WiFi hotspot named {ap_name}...')
    try:
        ap_if.disconnect()
        sta_if.disconnect()
    except:
        pass
    ap_if.active(False) #  de-activate the interfaces
    sta_if.active(False)
    utime.sleep(1)
    ap_if.active(True)
    ap_if.config(essid=ap_name)
    return "0.0.0.0"


def initialize():
    global settings
    # You have to do this one-at-a-time...
    try:
        os.mkdir('/files')  # make sure folder exists
    except OSError as e:
        if e.args[0] != 17:  # 17: EEXIST, directory already exists
            raise
    try:
        os.mkdir('/files/user')  # make sure folder exists
    except OSError as e:
        if e.args[0] != 17:  # 17: EEXIST, directory already exists
            raise
    # get settings or set defaults
    settings = {}
    try:
        with open('settings.json', 'r') as f:
            settings = ujson.load(f)
    except OSError:
        settings = {
            'IDE_BUTTON_PIN': 14,
            'ap_name': generate_ap_name(),
            'wifi_ssids': [],
            'wifi_passwords': []
        }
        with open('settings.json', 'w') as f:
            ujson.dump(settings, f)

initialize()
ip_address = connect_to_wifi(settings['wifi_ssids'], settings['wifi_passwords'])
if ip_address == "0.0.0.0":
    ip_address = create_soft_ap(settings["ap_name"])
app = HTTPServer(ip_address, 80)


def unquote(s):
    res = s.split('%')
    for i in range(1, len(res)):
        item = res[i]
        try:
            res[i] = chr(int(item[:2], 16)) + item[2:]
        except ValueError:
            res[i] = '%' + item
    return "".join(res)
    
# list folder contents, returns tuple (files, folders)
def list_files_and_folders(folder):
    try:
        files = []
        folders = []
        for f in os.listdir(folder):
            if file_exists(folder + '/' + f):
                files.append(f)
            else:
                folders.append(f)
        return files, folders
    except OSError:
        return [], []


# For making sure user input paths don't mess with other folders
def sanitize_path(path, base_path = USER_BASE_DIR):
    path = path.replace('\\','/').replace('//','/')
    combined_path = base_path + '/' + path
    # Split and normalize the path components
    parts = []
    for part in combined_path.split('/'):
        if part == '..':
            if parts:
                parts.pop()
        elif part and part != '.':
            parts.append(part)
    
    # Join the normalized parts back into a single path
    normalized_path = '/' + '/'.join(parts)
    
    # Ensure the path stays within the base_path
    if not normalized_path.startswith(base_path):
        raise ValueError("Invalid path")
    
    return normalized_path

# General GET requests
@app.route("GET", "/*")
async def static_files(reader, writer, request):
    local_path = "/static/"
    url_path = "/"
    subpath = unquote(request.path[len(url_path):])
    if subpath == '':
        subpath = 'index.html'
    try:
        full_path = sanitize_path(subpath, local_path)
    except:
        print('400: ' + full_path)
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    await serve_file(reader, writer, request, full_path, True)

# -----  User file operations  -----
# Serve user files with no caching
@app.route("GET", f'{USER_BASE_DIR}/*')
async def get_user_file(reader, writer, request):
    subpath = unquote(request.path[len(USER_BASE_DIR):])
    try:
        full_path = sanitize_path(subpath)
    except:
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    await serve_file(reader, writer, request, full_path, False)

# Handle POST requests for files
@app.route("POST", f'{USER_BASE_DIR}/*')
async def store_user_file(reader, writer, request):
    path = request.path
    filename = unquote(path[len(USER_BASE_DIR):])  # URL decoding the filename
    try:
        filename = sanitize_path(filename)
    except:
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return

    data = ujson.loads(request.body.decode("utf-8"))
    try:
        with open(filename, 'w') as file:
            file.write(data['content'])
    except Exception as ex:  # don't stop the server
        print(f'Filename was: {filename}')
        print(data)
        print(ex)
        response = HTTPResponse(500)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Error writing file!'}))
        await writer.drain()
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'response': 'success'}))
    await writer.drain()
    print(f"POST {path} with response code 200")

# Handle DELETE requests for user files
@app.route("DELETE", f'{USER_BASE_DIR}/*')
async def delete_user_file(reader, writer, request):
    path = request.path
    filename = unquote(path[len(USER_BASE_DIR):])  # URL decoding the filename
    try:
        filename = sanitize_path(filename)
    except:
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    try:
        os.remove(filename)
    except:
        response = HTTPResponse(404)
        await response.send(writer)
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'response': 'success'}))
    await writer.drain()
    print(f"DELETE {path} with response code 200")


# Serve help files with caching
@app.route("GET", "/files/help/*")
async def help_files(reader, writer, request):
    try:
        full_path = sanitize_path(unquote(request.path[len('/files/help'):]), '/files/help')
    except:
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    await serve_file(reader, writer, request, full_path, True)


# -----  API endpoints  -----
# retrieve list of files and folders
@app.route("GET", "/api/files/*")
async def api_list_files(reader, writer, request):
    try:
        folder = sanitize_path(request.path[len('/api/files'):], '/files')
    except:
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    files, folders = list_files_and_folders(folder)
    writer.write(ujson.dumps({'files': files, 'folders': folders}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")

# move a user file
@app.route("POST", "/api/files/move")
async def api_move_file(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    try:
        src = sanitize_path(data["src"])
        dest = sanitize_path(data["dest"])
        if src == dest:
            response = HTTPResponse(400)
            await response.send(writer)
            await writer.drain()
            writer.write(ujson.dumps({'error': 'File is already there.'}))
            await writer.drain()
            return
        os.rename(src, dest)
    except Exception as ex:
        print(f"API request: {request.path} with response code 400")
        print(data)
        print(ex)
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Invalid path!'}))
        await writer.drain()
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'files': list_files(request.path[len('/api'):])}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")


# get the disk usage
@app.route("GET", "/api/space")
async def api_get_space(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    fs_stat = os.statvfs('/')
    total = fs_stat[0] * fs_stat[2]
    free = fs_stat[0] * fs_stat[3]
    writer.write(ujson.dumps({'total_bytes': total, 'free_bytes': free}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")

# pseudo-REPL
@app.route("POST", "/api/repl")
async def api_repl(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    results = pseudoREPL(data['cmd'])
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'res': results}))
    await writer.drain()
    print(f"REPL command: '{data['cmd']}'")

# set a Python file as the primary app
@app.route("POST", "/api/setasapp")
async def api_setasapp(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    localized_filename = data['filename']   # /tmp/test/hello.py
    filename = USER_BASE_DIR + '/' + localized_filename  # /files/user/tmp/test/hello.py
    if not file_exists(filename) or filename[-3:] != '.py':
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Unable to set this file as app!'}))
        await writer.drain()
        return
    # create and overwrite app.py
    imp_pkg = localized_filename.rsplit('.', 1)[0]  # /tmp/test/hello
    imp_pkg = imp_pkg.replace('/', '.').lstrip('.')  # tmp.test.hello
    imp_command = f'import {imp_pkg}'  # import hello
    if '.' in imp_pkg:
        imp_name = imp_pkg.rsplit('.',1)[1]   # hello
        imp_command += f' as {imp_name}'  # import tmp.test.hello as hello
    content = f'# Auto-generated by TartLab (do not hand-edit!)\n# {localized_filename}\n{imp_command}'
    print(content)
    try:
        with open('app.py', 'w') as f:
            f.write(content)
    except Exception as ex:
        print(f"API request: {request.path} with response code 400")
        print(data)
        print(ex)
        response = HTTPResponse(400)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'error': 'Error writing app.py!'}))
        await writer.drain()
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'response': 'success'}))
    await writer.drain()
    print(f"SET AS APP {localized_filename} with response code 200")


async def say_hello_task():
    """ Show system is still alive """
    count = 0
    while True:
        print("hello", count)
        count += 1
        await asyncio.sleep(60)
        

async def free_memory_task():
    """ Avoid memory fragmentation """
    while True:
        gc.collect()
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        await asyncio.sleep(60)

try:
    def handle_exception(loop, context):
        # uncaught exceptions end up here
        print("global exception handler:", context)
        sys.print_exception(context["exception"])
        sys.exit()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

    loop.create_task(say_hello_task())
    loop.create_task(free_memory_task())
    loop.create_task(app.start())

    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    asyncio.run(app.stop())
    asyncio.new_event_loop()

