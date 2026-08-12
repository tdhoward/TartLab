"""Test-only implementation of TartLab's startup platform contract."""


class HeadlessDisplay:
    def __init__(self, width=222, height=480, color_depth=16):
        self.width = width
        self.height = height
        self.color_depth = color_depth
        self.requires_byteswap = False
        self.brightness = 1.0
        self.fills = []
        self.deinitialized = False

    def fill(self, color):
        self.fills.append(color)

    def deinit(self):
        self.deinitialized = True


class HeadlessInput:
    def __init__(self):
        self.events = []
        self.deinitialized = False

    def queue(self, event):
        self.events.append(event)

    def read(self):
        if self.events:
            return self.events.pop(0)
        return None

    def deinit(self):
        self.deinitialized = True


class HeadlessIDEView:
    def __init__(self):
        self.events = []

    def show_startup(self, version):
        self.events.append(("startup", version))

    def show_network(self, wifi_name, address, hostname=None):
        self.events.append(("network", wifi_name, address, hostname))

    def show_update_progress(self, status, step, steps):
        self.events.append(("update", status, step, max(step, steps)))


class HeadlessWLAN:
    def __init__(self, networks=None, address="0.0.0.0"):
        self.networks = list(networks or [])
        self.address = address
        self.enabled = False
        self.connected = False
        self.connection_attempts = []
        self.configuration = {}

    def active(self, value=None):
        if value is None:
            return self.enabled
        self.enabled = bool(value)

    def disconnect(self):
        self.connected = False

    def scan(self):
        return list(self.networks)

    def connect(self, ssid, password):
        self.connection_attempts.append((ssid, password))
        available = [item[0].decode("utf-8") for item in self.networks]
        self.connected = ssid in available

    def isconnected(self):
        return self.connected

    def ifconfig(self):
        return (self.address, "255.255.255.0", self.address, self.address)

    def config(self, **values):
        self.configuration.update(values)


class HeadlessPlatform:
    def __init__(
            self, ide_button_value=1, width=222, height=480,
            networks=None, station_address="10.0.0.42"):
        self.display = HeadlessDisplay(width, height)
        self.input = HeadlessInput()
        self.ide_view = HeadlessIDEView()
        self.station = HeadlessWLAN(networks, station_address)
        self.access_point = HeadlessWLAN(address="192.168.4.1")
        self.ide_button_pin = None
        self.width = width
        self.height = height
        self.hostname = None
        self.sleeps = []
        self.capabilities = {
            "display": True,
            "touch": True,
            "ide_button": True,
            "backlight": True,
            "network": True,
            "headless": True,
        }
        self._ide_button_values = [ide_button_value]

    def ide_button_value(self):
        if len(self._ide_button_values) > 1:
            return self._ide_button_values.pop(0)
        return self._ide_button_values[0]

    def set_ide_button_value(self, value):
        self._ide_button_values = [value]

    def queue_ide_button_values(self, *values):
        if values:
            self._ide_button_values = list(values)

    def set_hostname(self, hostname):
        self.hostname = hostname

    def station_interface(self):
        return self.station

    def access_point_interface(self):
        return self.access_point

    def configure_open_access_point(self, interface, name):
        interface.active(True)
        interface.config(essid=name, authmode="open")

    def create_ide_view(self):
        return self.ide_view

    def set_brightness(self, value):
        self.display.brightness = value
        self.ide_view.events.append(("brightness", value))

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def deinit(self):
        self.input.deinit()
        self.display.deinit()
