import network
import uos
import ujson
import usocket as socket
import random

# Configuration for the soft AP
PASSWORD = 'yourpassword'

# Lists of adjectives and animals
ADJECTIVES = ["Adventurous", "Brave", "Clever", "Daring", "Energetic", "Friendly", "Gentle", "Happy", "Inquisitive", "Jolly", "Kind", "Lively", "Mighty", "Noble", "Optimistic", "Playful", "Quick", "Radiant", "Strong", "Wise"]
ANIMALS = ["Antelope", "Bear", "Cat", "Dolphin", "Elephant", "Fox", "Giraffe", "Horse", "Iguana", "Jaguar", "Koala", "Lion", "Monkey", "Narwhal", "Owl", "Penguin", "Quail", "Rabbit", "Squirrel", "Tiger"]

# HTML, JS, CSS files to serve
FILE_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.py': 'text/x-python',
    '.ico': 'image/x-icon',
    '.jpg': 'image/jpeg',
}

# Function to generate a random AP name
def generate_ap_name():
    adjective = random.choice(ADJECTIVES)
    animal = random.choice(ANIMALS)
    number = random.randint(10, 99)
    return f"Py{adjective}{animal}{number}"

# Function to ensure the /files directory exists
def ensure_files_directory():
    try:
        uos.mkdir('/files')
    except OSError as e:
        if e.args[0] != 17:  # 17: EEXIST, directory already exists
            raise

# Function to ensure the settings.json file exists and to load the settings
def ensure_settings():
    settings = {}
    try:
        with open('settings.json', 'r') as f:
            settings = ujson.load(f)
    except OSError:
        # Generate a new AP name if settings.json does not exist
        ap_name = generate_ap_name()
        settings = {'ap_name': ap_name}
        with open('settings.json', 'w') as f:
            ujson.dump(settings, f)
    return settings

# Function to serve static files
def serve_file(client, path):
    try:
        with open(path, 'rb') as file:
            client.send('HTTP/1.1 200 OK\r\n')
            client.send('Content-Type: {}\r\n'.format(FILE_TYPES.get(uos.path.splitext(path)[1], 'application/octet-stream')))
            client.send('\r\n')
            while True:
                chunk = file.read(1024)
                if not chunk:
                    break
                client.send(chunk)
    except OSError:
        client.send('HTTP/1.1 404 Not Found\r\n\r\n')

# Function to list files in the /files directory
def list_files():
    try:
        return [f for f in uos.listdir('/files')]
    except OSError:
        return []

# Function to handle API requests
def handle_api_request(client, method, path):
    if method == 'GET' and path == '/files':
        files = list_files()
        response = ujson.dumps({'files': files})
        client.send('HTTP/1.1 200 OK\r\n')
        client.send('Content-Type: application/json\r\n\r\n')
        client.send(response)
    elif method == 'POST' and path.startswith('/files/'):
        filename = path[len('/files/'):]
        content_length = 0
        while True:
            line = client.readline()
            if not line or line == b'\r\n':
                break
            if line.startswith(b'Content-Length:'):
                content_length = int(line.split(b':')[1].strip())
        
        content = client.read(content_length)
        data = ujson.loads(content)
        with open('/files/' + filename, 'w') as file:
            file.write(data['content'])
        
        client.send('HTTP/1.1 200 OK\r\n\r\n')

# Main loop to handle client connections
def start_server():
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    server = socket.socket()
    server.bind(addr)
    server.listen(1)
    
    print('Server listening on', addr)
    
    while True:
        client, addr = server.accept()
        print('Client connected from', addr)
        try:
            request_line = client.readline().decode()
            method, path, _ = request_line.split()
            if path.startswith('/api'):
                handle_api_request(client, method, path[len('/api'):])
            else:
                serve_file(client, '.' + path)
        except Exception as e:
            print('Error:', e)
        finally:
            client.close()

# Ensure the /files directory exists
ensure_files_directory()

# Ensure the settings.json file exists and load settings
settings = ensure_settings()

# Initialize the soft AP with the AP name from settings
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=settings['ap_name'], password=PASSWORD)

# Start the server
start_server()
