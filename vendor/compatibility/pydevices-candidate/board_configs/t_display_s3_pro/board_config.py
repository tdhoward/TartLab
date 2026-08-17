# SPDX-License-Identifier: GPL-3.0-or-later
"""Legacy T-Display-S3 Pro board contract over current PyDevices APIs."""

import board_config as _board
import events
import eventsys


class LegacyBroker:
    """Expose the subset of the old Broker API used by TartLab applications."""

    events = events

    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def devices(self):
        return self.runtime.devices

    def poll(self):
        pending = self.runtime.poll()
        return pending[0] if pending else None

    def subscribe(self, callback, event_types=None, device_types=None):
        return self.runtime.subscribe(
            callback, event_types=event_types, device_types=device_types)

    def unsubscribe(self, callback, event_types=None, device_types=None):
        return self.runtime.unsubscribe(
            callback, event_types=event_types, device_types=device_types)

    def register_device(self, device):
        return self.runtime.register(device)

    def unregister_device(self, device):
        return self.runtime.unregister(device)

    def quit(self):
        return self.runtime.request_quit()


display_bus = _board.display_bus
display_drv = _board.display_drv
i2c = _board.i2c
touch_drv = getattr(_board, "touch", None)
touch_read_func = getattr(_board, "touch_read", None)
touch_rotation_table = getattr(_board, "touch_rotation_table", None)
runtime = eventsys.Runtime()
touch_dev = runtime.add_touch(
    touch_read_func,
    display=display_drv,
    touch_rotation_table=touch_rotation_table,
)
broker = LegacyBroker(runtime)

__all__ = (
    "display_bus", "display_drv", "i2c", "touch_drv", "touch_read_func",
    "touch_rotation_table", "broker", "touch_dev",
)
