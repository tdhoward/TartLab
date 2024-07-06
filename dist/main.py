import ujson
from machine import Pin

# read the settings file to determine buttons
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
    import app
