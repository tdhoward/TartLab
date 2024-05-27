import sys
import gc
import network
import os
import ujson
import utime
import random
import uasyncio as asyncio

from ahttpserver import HTTPResponse, HTTPServer
from ahttpserver.sse import EventSource
from ahttpserver.servefile import serve_file


# Function to generate a random AP name (currently not used)
def generate_ap_name():
    adjective = random.choice(["Adventurous", "Brave", "Clever", "Daring", "Energetic", "Friendly", "Gentle", "Happy", "Inquisitive", "Jolly", "Kind", "Lively", "Mighty", "Noble", "Optimistic", "Playful", "Quick", "Radiant", "Strong", "Wise"])
    animal = random.choice(["Antelope", "Bear", "Cat", "Dolphin", "Elephant", "Fox", "Giraffe", "Horse", "Iguana", "Jaguar", "Koala", "Lion", "Monkey", "Narwhal", "Owl", "Penguin", "Quail", "Rabbit", "Squirrel", "Tiger"])
    number = random.randint(10, 99)
    return f"Py{adjective}{animal}{number}"


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


# Function to connect to a local WiFi network
def connect_to_wifi(ssid, password):
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            print('Connecting to WiFi...')
            sleep(1)
        print('Connected to WiFi. Network config:', wlan.ifconfig())
        return wlan.ifconfig()[0]
    except:
        print(f'Error connecting to the {ssid} access point!')
        return '0.0.0.0'


initialize()
ip_address = connect_to_wifi(settings['wifi_ssid'], settings['wifi_password'])
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
    

# Serve static files with caching
@app.route("GET", "/*")
async def static_files(reader, writer, request):
    local_path = "/static/"
    url_path = "/"
    subpath = request.path[len(url_path):]
    if subpath == '':
        subpath = 'index.html'
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, True)


# Serve user files with no caching
@app.route("GET", "/files/user/*")
async def user_files(reader, writer, request):
    local_path = "/files/user/"
    url_path = "/files/user/"
    subpath = request.path[len(url_path):]
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, False)


# Serve help files with caching
@app.route("GET", "/files/help/*")
async def help_files(reader, writer, request):
    local_path = "/files/help/"
    url_path = "/files/help/"
    subpath = request.path[len(url_path):]
    full_path = local_path + subpath
    await serve_file(reader, writer, request, full_path, True)


# Function to list files in the /files directory
def list_files():
    try:
        return [f for f in os.listdir('/files')]
    except OSError:
        return []

# Handle /api GET requests
@app.route("GET", "/api/*")
async def handle_api(reader, writer, request):
    path = request.path
    if path == '/api/files':
        response = HTTPResponse(200, "application/json", close=True)
        await response.send(writer)
        await writer.drain()
        writer.write(ujson.dumps({'files': list_files()}))
        await writer.drain()
        print(f"API request: {path} with response code 200")
    elif path == '/api/space':
        response = HTTPResponse(200, "application/json", close=True)
        await response.send(writer)
        await writer.drain()
        fs_stat = os.statvfs('/')
        total = fs_stat[0] * fs_stat[2]
        free = fs_stat[0] * fs_stat[3]
        writer.write(ujson.dumps({'total_bytes': total, 'free_bytes': free}))
        await writer.drain()
        print(f"API request: {path} with response code 200")


# Handle /api POST requests for files
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


# Handle /api DELETE requests for files
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
