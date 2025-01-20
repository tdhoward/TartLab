"""
hardware_setup.py - hardware setup for MicroPython-Touch using DisplayBuffer on displaysys.
See:  https://github.com/peterhinch/micropython-touch

Usage:
    from hardware_setup import display
    <your code here>
"""

from displaybuf import DisplayBuffer as SSD
from board_config import display_drv, broker

# format = SSD.GS4_HMSB  # 4-bit (16 item) lookup table of 16-bit RGB565 colors; w*h/2 buffer
# format = SSD.GS8  # 256 8-bit RGB332 colors; w*h buffer
format = SSD.RGB565  # all 65,536 16-bit RGB565 colors; w*h*2 buffer

ssd = SSD(display_drv, format)


# enable screenshot functionality
def screenshot(event):
    if event.type == broker.events.MOUSEBUTTONDOWN and event.button == 3:
        ssd.screenshot()


broker.subscribe(screenshot, event_types=[broker.events.MOUSEBUTTONDOWN])
# End screenshot functionality


class Poller:
    def __init__(self, poll_func):
        self._poll_func = poll_func
        self._touched = False
        self.col = None
        self.row = None

    def poll(self):
        self._poll_func()
        return True if self._touched else False

    def callback(self, event):
        if event.type == broker.events.MOUSEMOTION and event.buttons[0] == 1:
            self.col, self.row = event.pos
            self._touched = True
        elif event.type == broker.events.MOUSEBUTTONDOWN and event.button == 1:
            self.col, self.row = event.pos
            self._touched = True
        elif event.type == broker.events.MOUSEBUTTONUP and event.button == 1:
            self._touched = False


tpad = Poller(broker.poll)
broker.subscribe(
    tpad.callback,
    event_types=[
        broker.events.MOUSEMOTION,
        broker.events.MOUSEBUTTONDOWN,
        broker.events.MOUSEBUTTONUP,
    ],
)

from gui.core.tgui import Display  # noqa: E402

display = Display(ssd, tpad)
