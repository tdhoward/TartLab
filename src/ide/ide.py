import sys
import gc
import network
import os
import ujson
import utime
import random
import uasyncio as asyncio
import io
from machine import Pin
#import webrepl
from tartlabutils import file_exists, unquote, rmvdir, check_for_update, main_update_routine, \
                    log, log_exception, get_logs, load_settings, save_settings, default_settings

from ahttpserver import HTTPResponse, HTTPServer
from ahttpserver.sse import EventSource
from ahttpserver.servefile import serve_file
from ahttpserver.response import sendHTTPResponse
from ahttpserver.multipart import handleMultipartUpload
from ahttpserver.server import HTTPServerError

# Display stuff
from hdwconfig import display_drv, IDE_BUTTON_PIN
from gfx.binfont import BinFont
from gfx.framebuf_plus import FrameBuffer, RGB565
from palettes import get_palette
display_drv.rotation = 90
WIDTH, HEIGHT = display_drv.width, display_drv.height
FONT_WIDTH = 8
BPP = display_drv.color_depth // 8  # Bytes per pixel
ba = bytearray(WIDTH * HEIGHT * BPP)
fb = FrameBuffer(ba, WIDTH, HEIGHT, RGB565)

if display_drv.requires_byte_swap:
    needs_swap = display_drv.disable_auto_byte_swap(True)
else:
    needs_swap = False

# Define color palette
class pal:
    BLACK = 0x0000
    WHITE = 0xFFFF
    RED = 0xF800 if not needs_swap else 0x00F8
    GREEN = 0x07E0 if not needs_swap else 0xE007
    BLUE = 0x001F if not needs_swap else 0xF800
    CYAN = 0x07FF if not needs_swap else 0xFF07
    MAGENTA = 0xF81F if not needs_swap else 0x1FF8
    YELLOW = 0xFFE0 if not needs_swap else 0xE0FF
    ORANGE = 0xFD20 if not needs_swap else 0x20FD
    PURPLE = 0x8010 if not needs_swap else 0x1080
    GREY = 0x8410 if not needs_swap else 0x1084

fb.fill(pal.BLACK)
fb.line(0, 0, WIDTH - 1, 0, pal.BLUE)
fb.line(WIDTH - 1, 0, WIDTH - 1, HEIGHT - 1, pal.BLUE)
fb.line(WIDTH - 1, HEIGHT - 1, 0, HEIGHT - 1, pal.BLUE)
fb.line(0, HEIGHT - 1, 0, 0, pal.BLUE)
text = 'TARTLAB'
fb.text(text, (WIDTH - FONT_WIDTH * len(text)) // 2, HEIGHT // 2 - 32, pal.WHITE)
display_drv.blit_rect(ba, 0, 0, WIDTH, HEIGHT)


USER_BASE_DIR = '/files/user'
IDE_BASE_DIR = '/ide'
settings = {}


def display_write(font, string, x, y, fg_color, bg_color, scale):
    """
    Write text to the display.
    """
    buffer_width = font.font_width * scale * len(string)
    buffer_height = font.font_height * scale
    buffer = bytearray(buffer_width * buffer_height * BPP)
    fb = FrameBuffer(buffer, buffer_width, buffer_height, RGB565)
    fb.fill(bg_color)
    font.text(fb, string, 0, 0, fg_color, scale)
    display_drv.blit_rect(buffer, x, y, buffer_width, buffer_height)

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

wifi_ssid = ''
def connect_to_wifi(ssids: list[str], keys: list[str]):
    global wifi_ssid
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
        wifi_ssid = ssid  # store the name
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


def create_soft_ap(ap_name):
    # Initialize the soft AP with the AP name from settings
    print(f'Creating WiFi hotspot named {ap_name}...')
    # we assume the interfaces start out deactivated by the connect_to_wifi function.
    ap_if.active(True)
    ap_if.config(essid=ap_name)
    ap_if.config(authmode=network.AUTH_OPEN)  # no password
    return '0.0.0.0'

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
        settings = load_settings()
    except OSError:
        default_settings()


# --------- Execution starts here -----------
# Since 'app' is used in decorators below, we need it to already exist.
initialize()
network.hostname(settings['hostname'])  # sets up hostname (e.g. tartlab.local) on mDNS (currently only works for STA interface)
sta_if = network.WLAN(network.STA_IF) # create station interface
ap_if = network.WLAN(network.AP_IF) #  create access-point interface
ip_address = connect_to_wifi(settings['wifi_ssids'], settings['wifi_passwords'])
softAP = False
if ip_address == "0.0.0.0":
    softAP = True
    wifi_ssid = settings["ap_name"]
    ip_address = create_soft_ap(wifi_ssid)
app = HTTPServer(ip_address, 80)

text = f'WiFi: {wifi_ssid}'
dirty = fb.text(text, (WIDTH - FONT_WIDTH * len(text)) // 2, HEIGHT // 2 - 8, pal.WHITE)
display_drv.blit_rect(ba, 0, 0, WIDTH, HEIGHT)  # due to bug, just blit whole screen
#display_drv.blit_rect(ba, dirty.x, dirty.y, dirty.w, dirty.h)
if softAP:
    text = '192.168.4.1'
else:
    text = ip_address
dirty = fb.text(text, (WIDTH - FONT_WIDTH * len(text)) // 2, HEIGHT // 2 + 8, pal.WHITE)
display_drv.blit_rect(ba, 0, 0, WIDTH, HEIGHT)
#display_drv.blit_rect(ba, dirty.x, dirty.y, dirty.w, dirty.h)
if not softAP:
    text = settings['hostname'] + '.local'
    dirty = fb.text(text, (WIDTH - FONT_WIDTH * len(text)) // 2, HEIGHT // 2 + 24, pal.WHITE)
    display_drv.blit_rect(ba, 0, 0, WIDTH, HEIGHT)


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
        log(f'Exception serving file: {e}')

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
        log(f'Exception serving file: {e}')

# Handle POST requests for files
@app.route("POST", f'{USER_BASE_DIR}/*')
async def store_user_file(reader, writer, request):
    path = request.path
    filename = unquote(path[len(USER_BASE_DIR):])  # URL decoding the filename
    try:
        filename = sanitize_path(filename)
    except:
        return await sendHTTPResponse(writer, 400, 'Invalid path!')
    try:
        print(request.body)
        data = ujson.loads(request.body.decode("utf-8"))
    except Exception as ex:
        log(f'{ex} for {filename}')
        return await sendHTTPResponse(writer, 500, 'Error parsing JSON!')
    try:
        with open(filename, 'w') as file:
            file.write(data['content'])
    except Exception as ex:  # don't stop the server
        log(f'Filename was: {filename}')
        log(ex)
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
        log(f'Exception serving file: {e}')


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
        log(ex)
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


# get the hostname setting
@app.route("GET", "/api/hostname")
async def api_get_hostname(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    hostname = settings['hostname']
    writer.write(ujson.dumps({'hostname': hostname}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")

# set the hostname setting
@app.route("POST", "/api/hostname")
async def api_get_hostname(reader, writer, request):
    global settings
    try:
        data = ujson.loads(request.body.decode("utf-8"))
        settings['hostname'] = data['hostname']
        save_settings(settings)
    except:
        return await sendHTTPResponse(writer, 400, 'Error setting hostname!')
    await sendHTTPResponse(writer, 200, 'success')
    print(f"API request: {request.path} with response code 200")


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
            assets, latest_version = await check_for_update(repo)
            updates.append((assets, latest_version))
        except Exception as e:
            log_exception(e)
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
    # TODO: Are there even any updates to do?
    await sendHTTPResponse(writer, 200, 'success')  # we return success right away, since we're restarting
    print(f"API request: {request.path} with response code 200")
    await main_update_routine()


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

# reset the memory of the pseudo-REPL
@app.route("POST", "/api/resetrepl")
async def api_resetrepl(reader, writer, request):
    global replGlobals
    replGlobals = {}
    await sendHTTPResponse(writer, 200, 'success')
    print(f"RESET REPL request with response code 200")


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
        log(ex)
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
        save_settings(settings)
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
                save_settings(settings)
                print(f"DELETE SSID {ssid} with response code 200")
                return await sendHTTPResponse(writer, 200, 'success')
    except:
        return await sendHTTPResponse(writer, 400, 'Unable to remove SSID!')
    return await sendHTTPResponse(writer, 404, 'SSID not found!')    


# get the stored logs
@app.route("GET", "/api/logs")
async def api_get_logs(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    logs = get_logs()
    writer.write(ujson.dumps({'logs': logs}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")


async def check_buttons():
    """ Check for user input on buttons """
    IDE_BUTTON = Pin(IDE_BUTTON_PIN, Pin.IN)
    bright = 1.0
    while True:
        if IDE_BUTTON.value() == 0:  # (unpressed button value is 1)
            bright -= 0.25
            if bright <= 0:
                bright = 1.0
            display_drv.brightness = bright
            while IDE_BUTTON.value() == 0:  # now wait until they release it
                await asyncio.sleep(0.25)
        await asyncio.sleep(0.2)
        

async def free_memory_task():
    """ Avoid memory fragmentation """
    while True:
        gc.collect()
        gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
        await asyncio.sleep(60)


def main():
    global sta_if, ap_if, ip_address, softAP, app

    try:
        def handle_exception(loop, context):
            # uncaught exceptions end up here
            log_exception(context["exception"])

        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_exception)

        loop.create_task(check_buttons())
        loop.create_task(free_memory_task())
        loop.create_task(app.start())
        #loop.create_task(webrepl.start_foreground(password='tartlab'))

        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run(app.stop())
        #asyncio.run(webrepl.stop())
        asyncio.new_event_loop()


if __name__ == '__main__':
    main()
