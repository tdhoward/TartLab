import buttons
from machine import Pin

# Check if IDE button is pressed
IDE_BUTTON = Pin(buttons.IDE_BUTTON_PIN, Pin.IN)

# default button value is 1
if IDE_BUTTON.value() == 1:  # TODO: change to 0 when done developing IDE
    import ide
else:
    import app
