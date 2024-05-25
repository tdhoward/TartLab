import sys
import gc
import network
import os
import ujson
import utime
import random
import uasyncio as asyncio

from ahttpserver import HTTPResponse, HTTPServer, sendfile
from ahttpserver.sse import EventSource


# HTML, JS, CSS files to serve
FILE_TYPES = {
    'html': 'text/html',
    'css': 'text/css',
    'js': 'application/javascript',
    'svg': 'image/svg+xml',
    'png': 'image/png',
    'py': 'text/x-python',
    'ico': 'image/x-icon',
    'jpg': 'image/jpeg',
}

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
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)
    while not wlan.isconnected():
        print('Connecting to WiFi...')
        sleep(1)
    print('Connected to WiFi. Network config:', wlan.ifconfig())
    return wlan.ifconfig()[0]


initialize()
ip_address = connect_to_wifi(settings['wifi_ssid'], settings['wifi_password'])
app = HTTPServer(ip_address, 80)


def unquote(s):
    """Kindly rewritten by Damien from Micropython"""
    """No longer uses caching because of memory limitations"""
    res = s.split('%')
    for i in xrange(1, len(res)):
        item = res[i]
        try:
            res[i] = chr(int(item[:2], 16)) + item[2:]
        except ValueError:
            res[i] = '%' + item
    return "".join(res)
    
# Since there is no strftime in micropython...
# Days and Months mappings for HTTP-date format (for Last-Modified header)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_http_date(gmtime_tuple):
    # gmtime_tuple format: (year, month, mday, hour, minute, second, weekday, yearday)
    year, month, mday, hour, minute, second, weekday, _ = gmtime_tuple
    return "{}, {:02d} {} {:04d} {:02d}:{:02d}:{:02d} GMT".format(
        DAYS[weekday], mday, MONTHS[month - 1], year, hour, minute, second
    )

# Serve static files
@app.route("GET", "/*")
async def serve_file(reader, writer, request):
    path = request.path
    if path == '/':
        path = '/index.html'
    full_path = path if path.startswith('/') else '/' + path
    extension = full_path.split('.')[-1]
    caching = True
    content_type = FILE_TYPES.get(extension, 'application/octet-stream')
    extra_headers = dict()
    try:
        # Set up headers for caching
        file_stat = os.stat(full_path)
        if caching:
            last_modified_time = file_stat[8]  # The 8th element is the last modified time
            last_modified_str = format_http_date(utime.gmtime(last_modified_time))
            last_modified_bytes = last_modified_str.encode()
            # b'If-Modified-Since': b'Wed, 22 May 2024 17:57:58 GMT'
            if b'If-Modified-Since' in request.header:
                print(request.header[b'If-Modified-Since'])
                if request.header[b'If-Modified-Since'] == last_modified_bytes:
                    response = HTTPResponse(304)
                    await response.send(writer)
                    return
            extra_headers['Last-Modified'] = last_modified_str
            extra_headers['Cache-Control'] = 'public, max-age=3600'
        else:
            extra_headers['Cache-Control'] = 'no-cache'
        file_size = str(file_stat[6])  # in bytes
        extra_headers['Content-Length'] = file_size
        response = HTTPResponse(200, content_type, close=True, header=extra_headers)
        await response.send(writer)
        await sendfile(writer, full_path)
        await writer.drain()
        print(f"Served file: {full_path} with response code 200")
    except OSError:
        response = HTTPResponse(404)
        await response.send(writer)
        print(f"File not found: {full_path} with response code 404")

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
