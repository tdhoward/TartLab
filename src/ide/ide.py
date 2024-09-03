import sys
import gc
import network
import os
import ujson
import utime
import random
import uasyncio as asyncio
import io
from tartlabutils import file_exists, unquote, rmvdir, check_for_update, main_update_routine, \
                        log, get_logs

from ahttpserver import HTTPResponse, HTTPServer
from ahttpserver.sse import EventSource
from ahttpserver.servefile import serve_file
from ahttpserver.response import sendHTTPResponse
from ahttpserver.multipart import handleMultipartUpload
from ahttpserver.server import HTTPServerError


network.hostname('tartlab')  # sets up tartlab.local on mDNS (currently only works for STA interface)

USER_BASE_DIR = '/files/user'
IDE_BASE_DIR = '/ide'
SETTINGS_FILE = '/settings.json'


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

network_names = []  # stores the list of network names from when we scanned.
def scan_for_wifi(ssids: list[str], keys: list[str]):
    global network_names
    print("Scanning for WiFi networks...")
    networks = sta_if.scan()  # returns list of (ssid, bssid, channel, RSSI, security, hidden)
    networks.sort(key=lambda n:n[3], reverse=True)  # sort networks by RSSI
    for nwork in networks:
        network_name = nwork[0].decode('utf-8')
        if network_name != "" and network_name not in network_names:
            network_names.append(network_name)
    for network_name in network_names:
        for idx, s in enumerate(ssids):
            if s == network_name:
                ssid = s
                key = keys[idx]
                return True, ssid, key
    return False, "", ""


def connect_to_wifi(ssids: list[str], keys: list[str]):
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
    if len(ssids) == 0:
        scan_for_wifi([],[])  # scan anyway, so we capture the available SSIDs
        sta_if.active(False)
        return "0.0.0.0"
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
    # we assume the interfaces start out deactivated by the connect_to_wifi function.
    ap_if.active(True)
    ap_if.config(essid=ap_name)
    ap_if.config(authmode=network.AUTH_OPEN)  # no password
    return '0.0.0.0'

def load_settings():
    global settings
    settings = {}
    with open(SETTINGS_FILE, 'r') as f:
        settings = ujson.load(f)

def save_settings():
    global settings
    with open(SETTINGS_FILE, 'w') as f:
        ujson.dump(settings, f)

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
    try:
        load_settings()
    except OSError:
        settings = {
            'dbver': 1,
            'STARTUP_MODE': 'BUTTON',
            'IDE_BUTTON_PIN': 14,
            'ap_name': generate_ap_name(),
            'wifi_ssids': [],
            'wifi_passwords': []
        }
        save_settings()

initialize()
ip_address = connect_to_wifi(settings['wifi_ssids'], settings['wifi_passwords'])
softAP = False
if ip_address == "0.0.0.0":
    softAP = True
    ip_address = create_soft_ap(settings["ap_name"])
app = HTTPServer(ip_address, 80)


# list folder contents, returns tuple (files, folders)
def list_files_and_folders(folder):
    try:
        files = []
        folders = []
        if folder != USER_BASE_DIR:
            folders.append('..')
        for f in os.listdir(folder):
            ex = file_exists(folder + '/' + f)
            if ex == 1:
                files.append(f)
            elif ex == 2:
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


# get the Python file currently set as the primary app
# returns a tuple of (localized_filename, error)
def get_app():
    localized_filename = ""
    try:
        with open('app.py', 'r') as f:
            lines = f.readlines()
            if len(lines) < 3:
                return "",'Invalid app.py!'
            localized_filename = lines[1][2:].strip()
    except:
        return "",'Invalid app.py!'
    return localized_filename,''


# General GET requests
@app.route("GET", "/*")
async def static_files(reader, writer, request):
    local_path = f'{IDE_BASE_DIR}/www/'
    url_path = "/"
    subpath = unquote(request.path[len(url_path):])
    if subpath == '':
        subpath = 'index.html'
    try:
        full_path = sanitize_path(subpath, local_path)
    except:
        print('400: ' + full_path)
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        await serve_file(reader, writer, request, full_path, True)
    except Exception as e:
        print(f'Exception serving file: {e}')

# -----  User file operations  -----
# Serve user files with no caching
@app.route("GET", f'{USER_BASE_DIR}/*')
async def get_user_file(reader, writer, request):
    subpath = unquote(request.path[len(USER_BASE_DIR):])
    try:
        full_path = sanitize_path(subpath)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        await serve_file(reader, writer, request, full_path, False)
    except Exception as e:
        print(f'Exception serving file: {e}')

# Handle POST requests for files
@app.route("POST", f'{USER_BASE_DIR}/*')
async def store_user_file(reader, writer, request):
    path = request.path
    filename = unquote(path[len(USER_BASE_DIR):])  # URL decoding the filename
    try:
        filename = sanitize_path(filename)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    data = ujson.loads(request.body.decode("utf-8"))
    try:
        with open(filename, 'w') as file:
            file.write(data['content'])
    except Exception as ex:  # don't stop the server
        print(f'Filename was: {filename}')
        print(ex)
        return await sendHTTPResponse(writer, 500, 'Error writing file!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"POST {path} with response code 200")

# Handle DELETE requests for user files
@app.route("DELETE", f'{USER_BASE_DIR}/*')
async def delete_user_file(reader, writer, request):
    path = request.path
    filename = unquote(path[len(USER_BASE_DIR):])  # URL decoding the filename
    try:
        filename = sanitize_path(filename)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        os.remove(filename)
    except:
        return await sendHTTPResponse(writer, 404, 'Could not remove file!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"DELETE {path} with response code 200")


# Serve help files with caching
@app.route("GET", "/files/help/*")
async def help_files(reader, writer, request):
    try:
        full_path = sanitize_path(unquote(request.path[len('/files/help'):]), '/files/help')
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        await serve_file(reader, writer, request, full_path, True)
    except Exception as e:
        print(f'Exception serving file: {e}')


# -----  API endpoints  -----
# retrieve list of files and folders, as well as an indication of which file is the current app
@app.route("GET", "/api/files/*")
async def api_list_files(reader, writer, request):
    try:
        folder = sanitize_path(request.path[len('/api/files'):], '/files')
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    files, folders = list_files_and_folders(folder)
    app_filename, error = get_app()
    if app_filename == '':
        return await sendHTTPResponse(writer, 400, error)
    app_filename = USER_BASE_DIR + '/' + app_filename
    app = -1
    # figure out whether the app file is supposedly in this folder
    if app_filename.startswith(folder):
        localized_app_filename = app_filename[len(folder) + 1:]
        # figure out whether the app file is one of the listed files (and which one)
        if localized_app_filename in files:
            app = files.index(localized_app_filename)
    writer.write(ujson.dumps({'files': files, 'folders': folders, 'app': app}))
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
            return await sendHTTPResponse(writer, 400, 'File is already there.')
        os.rename(src, dest)
    except Exception as ex:
        print(f"API request: {request.path} with response code 400")
        print(ex)
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"API request: {request.path} with response code 200")


# upload a file
@app.route("POST", "/api/files/upload/*")
async def api_upload_file(reader, writer, request):
    try:
        folder = sanitize_path(request.path[len('/api/files/upload'):])
        await handleMultipartUpload(reader, writer, request, folder)
    except HTTPServerError as e:
        return await sendHTTPResponse(writer, 404, str(e))
    await sendHTTPResponse(writer, 200, 'success')
    print(f"POST {request.path} with response code 200")


# Create new folder
@app.route("POST", "/api/folder/create")
async def create_new_folder(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    try:
        foldername = data['newFolderName']
        foldername = sanitize_path(foldername)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        os.mkdir(foldername)
    except:
        return await sendHTTPResponse(writer, 404, 'Could not create folder!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"POST {request.path} with response code 200")


# Rename folder
@app.route("POST", "/api/folder/rename")
async def rename_folder(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    try:
        src = data['src']
        dest = data['dest']
        srcfolder = sanitize_path(src)
        destfolder = sanitize_path(dest)
        if file_exists(srcfolder) != 2:  # make sure srcfolder is a real folder
            return await sendHTTPResponse(writer, 400, 'Invalid source path!')
        if file_exists(destfolder) != 0:  # make sure destfolder doesn't exist
            return await sendHTTPResponse(writer, 400, 'Destination path already exists!')
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        os.rename(srcfolder, destfolder)
    except:
        return await sendHTTPResponse(writer, 404, 'Could not rename folder!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"POST {request.path} with response code 200")


# Delete user folder and all subfolders and files
@app.route("POST", "/api/folder/delete")
async def delete_folder(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    try:
        foldername = data['folderName']
        foldername = sanitize_path(foldername)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        if file_exists(foldername) != 2:  # not a folder, or doesn't exist
            return await sendHTTPResponse(writer, 400, 'Invalid folder path!')
        rmvdir(foldername)
    except:
        return await sendHTTPResponse(writer, 404, 'Could not delete folder!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"DELETE {request.path} with response code 200")


# get the installed versions of repos
@app.route("GET", "/api/versions")
async def api_get_versions(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    repos = {}
    with open('repos.json', 'r') as f:
        repos = ujson.load(f)
    writer.write(ujson.dumps(repos))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")


# check for version updates for the repos
@app.route("GET", "/api/checkupdates")
async def api_check_updates(reader, writer, request):
    global softAP
    if softAP:
        return await sendHTTPResponse(writer, 400, 'This WiFi has no internet access.')
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    repos = {}
    with open('repos.json', 'r') as f:
        repos = ujson.load(f)
    updates = []
    for repo in repos['list']:
        try:
            assets, latest_version = check_for_update(repo)
            updates.append((assets, latest_version))
        except Exception as e:
            updates.append(('error', e))
    writer.write(ujson.dumps(updates))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")


# start updates for the repos
@app.route("POST", "/api/doupdates")
async def api_do_updates(reader, writer, request):
    global softAP
    if softAP:
        return await sendHTTPResponse(writer, 400, 'This WiFi has no internet access.')
    await sendHTTPResponse(writer, 200, 'success')  # we return success right away, since we're restarting
    print(f"API request: {request.path} with response code 200")
    main_update_routine()


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
    if file_exists(filename) != 1 or filename[-3:] != '.py':
        return await sendHTTPResponse(writer, 400, 'Unable to set this file as app!')
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
        print(ex)
        return await sendHTTPResponse(writer, 400, 'Error writing app.py!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"SET AS APP {localized_filename} with response code 200")

# get the stored and scanned SSIDs
@app.route("GET", "/api/ssids")
async def api_get_ssids(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    scanned = [n for n in network_names if n not in settings['wifi_ssids']]
    writer.write(ujson.dumps({'stored': settings['wifi_ssids'], 'scanned': scanned}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")

# add new SSID
@app.route("POST", "/api/add_ssid")
async def api_add_ssid(reader, writer, request):
    global settings
    data = ujson.loads(request.body.decode("utf-8"))
    ssid = data['ssid']
    password = data['password']
    if ssid in settings['wifi_ssids']:
        return await sendHTTPResponse(writer, 400, 'SSID is already stored!')
    try:
        settings['wifi_ssids'].append(ssid)
        settings['wifi_passwords'].append(password)
        save_settings()
    except:
        return await sendHTTPResponse(writer, 400, 'Unable to save SSID!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"ADD SSID {ssid} with response code 200")

# delete the SSID
@app.route("DELETE", "/api/remove_ssid/*")
async def api_add_ssid(reader, writer, request):
    global settings
    ssid = unquote(request.path[len('/api/remove_ssid/'):])
    try:
        for idx, s in enumerate(settings['wifi_ssids']):
            if s == ssid:
                del settings['wifi_ssids'][idx]  # remove ssid and password
                del settings['wifi_passwords'][idx]
                save_settings()
                print(f"DELETE SSID {ssid} with response code 200")
                return await sendHTTPResponse(writer, 200, 'success')
    except:
        return await sendHTTPResponse(writer, 400, 'Unable to remove SSID!')
    return await sendHTTPResponse(writer, 404, 'SSID not found!')    


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
        sys.exit()  # TODO: remove for production

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

