"""Experimental internal /main.py: mount a prepared SD root, then run it.

Copy the selected declarative board payload to internal /hdwconfig.py too.
The full TartLab distribution belongs at the FAT card's root. This bootstrap
is a bench prototype; production updater/recovery integration is still pending.
"""

import sys
from hdwconfig import BOARD_CONFIG
from external_root import activate, open_sd

card = None
ready = False
try:
    card = open_sd(BOARD_CONFIG)
    activate(card, required=("boot.py", "main.py", "device/board.json", "device/hdwconfig.py"))
    ready = True
except Exception as error:
    if card is not None:
        card.deinit()
    print("SD startup unavailable; internal filesystem and serial REPL retained.")
    sys.print_exception(error)

if ready:
    # Do not leave the bootstrap selector cached as TartLab's protected selector.
    del sys.modules["hdwconfig"]
    with open("/boot.py") as stream:
        exec(stream.read(), globals())
    with open("/main.py") as stream:
        exec(stream.read(), globals())
