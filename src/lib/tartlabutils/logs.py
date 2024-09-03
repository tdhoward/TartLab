import os

# maintains 5 log files in the /logs folder

LOG_DIR = '/logs'
MAX_LOG_COUNT = 5
current_log_file = None

def init_logs():
    global current_log_file
    if not os.path.exists(LOG_DIR):
        os.mkdir(LOG_DIR)
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    if log_files:
        current_log_index = int(log_files[-1].split('.')[0])
        next_log_index = (current_log_index + 1)
        current_log_file = f"{str(next_log_index).zfill(6)}.log"
    else:
        current_log_file = "000000.log"

    # Start a new log file
    with open(os.path.join(LOG_DIR, current_log_file), 'w') as f:
        f.write("Log started\n")
    
    # Cull oldest logs if necessary
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    if len(log_files) > MAX_LOG_COUNT:
        oldest_log = log_files[0]
        os.remove(os.path.join(LOG_DIR, oldest_log))

def log(message):
    global current_log_file
    if current_log_file:
        with open(os.path.join(LOG_DIR, current_log_file), 'a') as f:
            f.write(message + "\n")

def get_logs():
    log_files = sorted([f for f in os.listdir(LOG_DIR) if f.endswith('.log')])
    all_logs = []
    for log_file in log_files:
        with open(os.path.join(LOG_DIR, log_file), 'r') as f:
            all_logs.append(f.read())
    return "".join(all_logs)
