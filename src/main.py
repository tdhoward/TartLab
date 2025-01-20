import sys

# add search folders for importing modules
dirs = ["/lib",
        "/",
        "/files/user", 
        "/configs", 
        "/lib/pydevices", 
        "/lib/pydevices/bus_drv",
        "/lib/pydevices/display_drv",
        "/lib/pydevices/touch_drv",
        "/lib/pydevices/add_ons"]

for d in dirs:
    if d not in sys.path:
        sys.path.insert(1, d)

import ujson
from machine import Pin
from tartlabutils import file_exists, init_logs, log, log_exception, load_settings, save_settings

init_logs()
log('System startup')

from hdwconfig import IDE_BUTTON_PIN, display_drv
WIDTH, HEIGHT = display_drv.width, display_drv.height
#display_drv.rotation = 0
#display_drv.fill_rect(0, 0, WIDTH, HEIGHT, 0x0000)  # clear with black

# read the settings file to determine IDE button
settings = {}
try:
    settings = load_settings()
except OSError:  # doesn't exist
    print('No settings found.')
    log('No settings file found.')

if 'STARTUP_MODE' not in settings:
    settings['STARTUP_MODE'] = 'BUTTON'  # use button state

# make sure we have a repos.json file
if not file_exists('repos.json'):
    repos = {
        'dbver': 1,
        'list': [
            {
                'name': 'TartLab',
                'repo': 'tdhoward/tartlab',
                'installed_version': 'v0.9'   # I guess we'll need to keep updating this
            }
        ]
    }
    with open('repos.json', 'w') as f:
        ujson.dump(repos, f)

# figure out whether to launch app or IDE
start_mode = settings['STARTUP_MODE']
if start_mode == 'BUTTON':
    # Check if IDE button is pressed
    IDE_BUTTON = Pin(IDE_BUTTON_PIN, Pin.IN)
    if IDE_BUTTON.value() == 1:  # 0 for production, 1 for dev  (unpressed button value is 1)
        start_mode = 'IDE'
    else:
        start_mode = 'APP'
else:  # we only get here if we loaded a settings.json file with non-default STARTUP_MODE
    settings['STARTUP_MODE'] = 'BUTTON'  # resets to default after one boot
    save_settings(settings)

if start_mode == 'IDE':
    log('Starting IDE')
    import ide
    ide.main()
else:
    log('Starting APP')
    try:
        import app  # launches the user's startup app
    except Exception as ex:
        log_exception(ex)
        display_drv.fill(0xF800)  # fill screen with red to indicate error
