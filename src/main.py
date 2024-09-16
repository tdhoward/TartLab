import sys

# add search folders for importing modules
dirs = ["/lib", 
        "/files/user", 
        "/configs", 
        "/lib/pydevices", 
        "/lib/pydevices/buses",
        "/lib/pydevices/display_drv",
        "/lib/pydevices/touch_drv",
        "/lib/pydevices/displays",
        "/lib/pydevices/utils"]

for d in dirs:
    if d not in sys.path:
        sys.path.insert(1, d)

import ujson
from machine import Pin
from tartlabutils import file_exists, init_logs, log

init_logs()
log('\nSystem startup')

import hdwconfig
log('\nHardware initialized')

# read the settings file to determine IDE button
try:
    with open('settings.json', 'r') as f:
        settings = ujson.load(f)
except OSError:  # doesn't exist
    print('No settings found.')
    log('No settings file found.')
    settings = {}

if 'STARTUP_MODE' not in settings:
    settings['STARTUP_MODE'] = 'BUTTON'  # use button state

# make sure we have a repos.json file
if not file_exists('repos.json'):
    repos = {
        'dbver': 1,
        'list': [
            {
                'name': 'TartLab',
                'repo': 'tdhoward/tartlab',  # owner/repo
                'installed_version': 0.1   # I guess we'll need to keep updating this
            }
        ]
    }
    with open('repos.json', 'w') as f:
        ujson.dump(repos, f)

# figure out whether to launch app or IDE
start_mode = settings['STARTUP_MODE']
if start_mode == 'BUTTON':
    # Check if IDE button is pressed
    IDE_BUTTON = Pin(hdwconfig.IDE_BUTTON_PIN, Pin.IN)
    if IDE_BUTTON.value() == 1:  # TODO: change to 0 when done developing IDE  (unpressed button value is 1)
        start_mode = 'IDE'
    else:
        start_mode = 'APP'
else:  # we only get here if we loaded a settings.json file with non-default STARTUP_MODE
    settings['STARTUP_MODE'] = 'BUTTON'  # resets to default after one boot
    with open('settings.json', 'w') as f:
        ujson.dump(settings, f)

if start_mode == 'IDE':
    log('Starting IDE')
    import ide
else:
    log('Starting APP')
    import app  # launches the user's startup app
