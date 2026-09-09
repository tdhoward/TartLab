"""Copy to user files to try physical buttons. Reset returns to the launcher."""

import time
import machine
from tartlabutils.platform import get_platform
from tartlabutils.app import DirectCanvas


platform = get_platform()
canvas = DirectCanvas()
count = 0
try:
    if not platform.capabilities.get("buttons", False):
        from tartlabutils.platform import InputUnavailableError
        raise InputUnavailableError("This example needs physical buttons.")
    names = platform.buttons.names
    while True:
        canvas.fill(0x0841)
        canvas.text("Button counter", 12, 12, 0xFFFF)
        canvas.text("%s: add   %s: restart" % (names[0], names[-1]), 12, 38, 0xFFE0)
        canvas.text("Count: %d" % count, 12, 68, 0x07E0)
        canvas.text("Reset returns to launcher", 12, 100, 0xFFFF)
        canvas.show()
        while True:
            changed = False
            for name, pressed in platform.read_button_events():
                if not pressed:
                    if name == names[-1]:
                        machine.reset()
                    count += 1
                    changed = True
            if changed:
                break
            time.sleep_ms(5)
finally:
    canvas.close()
