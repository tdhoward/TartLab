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

def connect_to_wifi(ssid: str, key: str):
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
    network_names = []
    scan_retries = 3
    while ssid not in network_names and scan_retries > 0:
        print("Scanning for WiFi networks...")
        networks = sta_if.scan()
        network_names = [i[0].decode("utf-8") for i in networks]
        scan_retries -= 1
    if ssid not in network_names:
        print(f'Could not find {ssid} network in scan!')
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
    try:
        os.mkdir('/files')  # make sure folder exists
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
            'ap_name': generate_ap_name(),
            'wifi_ssid': 'your_wifi_ssid',
            'wifi_password': 'your_wifi_password'
        }
        with open('settings.json', 'w') as f:
            ujson.dump(settings, f)

initialize()
ip_address = connect_to_wifi(settings['wifi_ssid'], settings['wifi_password'])
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
    
# Function to list files in the specified directory
def list_files(folder):
    try:
        return [f for f in os.listdir(folder)]
    except OSError:
        return []


# GET requests
@app.route("GET", "/*")
async def static_files(reader, writer, request):
    local_path = "/static/"
    url_path = "/"
    subpath = unquote(request.path[len(url_path):])
    if subpath == '':
        subpath = 'index.html'
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, True)

# Serve user files with no caching
@app.route("GET", "/files/user/*")
async def user_files(reader, writer, request):
    local_path = "/files/user/"
    url_path = "/files/user/"
    subpath = unquote(request.path[len(url_path):])
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, False)

# Serve help files with caching
@app.route("GET", "/files/help/*")
async def help_files(reader, writer, request):
    local_path = "/files/help/"
    url_path = "/files/help/"
    subpath = unquote(request.path[len(url_path):])
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, True)

# retrieve list of files
@app.route("GET", "/api/files/*")
async def handle_api(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'files': list_files(request.path[len('/api'):])}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")

# get the disk usage
@app.route("GET", "/api/space")
async def handle_api(reader, writer, request):
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    fs_stat = os.statvfs('/')
    total = fs_stat[0] * fs_stat[2]
    free = fs_stat[0] * fs_stat[3]
    writer.write(ujson.dumps({'total_bytes': total, 'free_bytes': free}))
    await writer.drain()
    print(f"API request: {request.path} with response code 200")


# Handle API POST requests for files
@app.route("POST", "/api/files/*")
async def handle_api(reader, writer, request):
    path = request.path
    filename = unquote(path[len('/api/files/'):])  # URL decoding the filename
    data = ujson.loads(request.body.decode("utf-8"))
    with open('/files/' + filename, 'w') as file:
        file.write(data['content'])
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'response': 'success'}))
    await writer.drain()
    print(f"API request: POST {path} with response code 200")


# Handle API DELETE requests for files
@app.route("DELETE", "/api/files/*")
async def handle_api(reader, writer, request):
    path = request.path
    filename = unquote(path[len('/api/files/'):])  # URL decoding the filename
    try:
        os.remove('/files/' + filename)
    except:
        response = HTTPResponse(404)
        await response.send(writer)
        return
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'response': 'success'}))
    await writer.drain()
    print(f"API request: DELETE {path} with response code 200")


# pseudo-REPL
@app.route("POST", "/api/repl")
async def handle_api(reader, writer, request):
    data = ujson.loads(request.body.decode("utf-8"))
    results = pseudoREPL(data['cmd'])
    response = HTTPResponse(200, "application/json", close=True)
    await response.send(writer)
    await writer.drain()
    writer.write(ujson.dumps({'res': results}))
    await writer.drain()
    print(f"REPL command: '{data['cmd']}'")


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

