import ujson
from machine import Pin
import sys
from tartlabutils import file_exists

# add search folders for importing modules
if "/lib" not in sys.path:
    sys.path.insert(1, '/lib')
sys.path.insert(1, '/files/user')

# read the settings file to determine IDE button
try:
    with open('settings.json', 'r') as f:
        settings = ujson.load(f)
except OSError:  # doesn't exist
    print('No settings found.')
    settings = {}
if 'IDE_BUTTON_PIN' not in settings:
    settings['IDE_BUTTON_PIN'] = 14  # default button pin

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

# Check if IDE button is pressed
IDE_BUTTON = Pin(settings['IDE_BUTTON_PIN'], Pin.IN)

# default button value is 1
if IDE_BUTTON.value() == 1:  # TODO: change to 0 when done developing IDE
    import ide
else:
    import app  # launches the user's startup app
