import ujson
from machine import Pin
import sys

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

# Check if IDE button is pressed
IDE_BUTTON = Pin(settings['IDE_BUTTON_PIN'], Pin.IN)

# default button value is 1
if IDE_BUTTON.value() == 1:  # TODO: change to 0 when done developing IDE
    import ide
else:
    import app  # launches the user's startup app
