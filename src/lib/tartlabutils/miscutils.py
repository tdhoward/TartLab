import os
import ujson
import random
import errno

# maintains 5 log files in the /logs folder
LOG_DIR = '/logs'
MAX_LOG_COUNT = 5
current_log_file = None

SETTINGS_FILE = '/settings.json'

# Returns 1 for file, 2 for folder, or 0 if doesn't exist
def file_exists(filepath):
    try:
        stat = os.stat(filepath)
        if stat[0] & 0x8000 == 0x8000:
            return 1  # regular file
        return 2   # folder
    except OSError:
        return 0   # doesn't exist
    
# Remove URL encoding
def unquote(s):
    res = s.split('%')
    for i in range(1, len(res)):
        item = res[i]
        try:
            res[i] = chr(int(item[:2], 16)) + item[2:]
        except ValueError:
            res[i] = '%' + item
    return "".join(res)
    

# recursively delete dir tree
def rmvdir(d):  # Remove file or tree
    if os.stat(d)[0] & 0x4000:  # Dir
        for f in os.ilistdir(d):
            if f[0] not in ('.', '..'):
                rmvdir("/".join((d, f[0])))  # File or Dir
        os.rmdir(d)
    else:  # File
        os.remove(d)

# Create folders and subfolders as needed
def mkdirs(path):
    # Remove leading and trailing slashes and split the path
    dirs = path.strip('/').split('/')
    current_path = ''
    for dir in dirs:
        current_path += '/' + dir
        try:
            os.mkdir(current_path)
        except OSError as e:
            if e.args[0] == errno.EEXIST:
                pass  # Directory already exists
            else:
                raise  # Re-raise exception if a different error occurred


def split_on_first(data, token = b'\r\n'):
    length = len(data)
    tl = len(token)
    for i in range(length - (tl - 1)):
        if data[i:i+tl] == token:
            return data[:i], data[i+tl:]
    # If no token is found, return the original data and an empty byte string
    return data, b''


def init_logs():
    global current_log_file
    if file_exists(LOG_DIR) != 2:
        os.mkdir(LOG_DIR)
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    if log_files:
        current_log_index = int(log_files[-1].split('.')[0])
        next_log_index = (current_log_index + 1)
        current_log_file = "{:06d}.log".format(next_log_index)
    else:
        current_log_file = "000000.log"

    # Start a new log file
    with open(LOG_DIR + '/' + current_log_file, 'w') as f:
        f.write("Log started\n")
    
    # Cull oldest logs if necessary
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    if len(log_files) > MAX_LOG_COUNT:
        oldest_log = log_files[0]
        os.remove(LOG_DIR + '/' + oldest_log)

def log(message):
    global current_log_file
    print(message)
    if current_log_file:
        with open(LOG_DIR + '/' + current_log_file, 'a') as f:
            f.write(message + "\n")

def get_logs():
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    all_logs = []
    for log_file in log_files:
        all_logs.append('------- REBOOT -------\n')
        with open(LOG_DIR + '/' + log_file, 'r') as f:
            all_logs.append(f.read())
    return "".join(all_logs)

# Function to generate a random AP name
def generate_ap_name():
    adjective = random.choice(["Adventurous", "Brave", "Clever", "Daring", "Energetic", "Friendly", "Gentle", "Happy", "Inquisitive", "Jolly", "Kind", "Lively", "Mighty", "Noble", "Optimistic", "Playful", "Quick", "Radiant", "Strong", "Wise"])
    animal = random.choice(["Antelope", "Bear", "Cat", "Dolphin", "Elephant", "Fox", "Giraffe", "Horse", "Iguana", "Jaguar", "Koala", "Lion", "Monkey", "Narwhal", "Owl", "Penguin", "Quail", "Rabbit", "Squirrel", "Tiger"])
    number = random.randint(10, 99)
    return f"Py{adjective}{animal}{number}"


def load_settings():
    settings = {}
    with open(SETTINGS_FILE, 'r') as f:
        settings = ujson.load(f)
    return settings

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        ujson.dump(settings, f)

def default_settings():
    settings = {
        'dbver': 1,
        'STARTUP_MODE': 'BUTTON',
        'pre-release-updates': False,
        'ap_name': generate_ap_name(),
        'hostname':'tartlab',
        'wifi_ssids': [],
        'wifi_passwords': []
    }
    save_settings(settings)
