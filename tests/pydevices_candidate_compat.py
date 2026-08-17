"""Platform-independent probe for the generated Phase 4 PyDevices candidate."""

import struct
import sys


CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(message)


def probe_graphics():
    import graphics
    from displaybuf import DisplayBuffer

    buffer = bytearray(2 * 2 * 2)
    framebuffer = graphics.FrameBuffer(buffer, 2, 2, graphics.RGB565)
    framebuffer.fill(0)
    graphics.pixel(framebuffer, 1, 1, 0xFFFF)
    check(framebuffer.pixel(1, 1) == 0xFFFF,
          "legacy graphics facade did not delegate drawing")
    check(DisplayBuffer.RGB565 == graphics.RGB565,
          "legacy display buffer format changed")


def probe_palettes():
    from palettes import get_palette

    palette = get_palette(name="material_design")
    check(palette.BLACK == 0, "legacy material palette changed")


def probe_keys():
    from eventsys.keys import Keys

    check(Keys.K_RETURN == 13, "legacy Keys constants changed")
    check(Keys.keyname(Keys.K_RETURN) == "Return",
          "legacy Keys name lookup changed")


def probe_images(qoi_fixture=None):
    from bmp565 import BMP565
    from qoi_reader import QOIImage

    check(BMP565 is not None, "legacy BMP565 import is unavailable")
    encoded = (
        b"qoif" + struct.pack(">IIbb", 1, 1, 3, 0)
        + b"\xfe\xff\x00\x00" + b"\x00" * 7 + b"\x01")
    image = QOIImage.loads(encoded)
    check(image.pixels == b"\xff\x00\x00", "QOI decode changed")
    check(image.as_rgb565() == b"\xf8\x00", "QOI RGB565 conversion changed")
    if qoi_fixture is not None:
        shipped = QOIImage.open(qoi_fixture)
        check((shipped.width, shipped.height, shipped.channels) == (144, 256, 3),
              "shipped QOI metadata changed")
        check(len(shipped.pixels) == 144 * 256 * 3,
              "shipped QOI pixel decode was incomplete")
        check(len(shipped.as_rgb565()) == 144 * 256 * 2,
              "shipped QOI RGB565 conversion was incomplete")


def probe_touch_keypad():
    import events
    from touch_keypad import Keypad

    event = events.Button(
        events.MOUSEBUTTONDOWN, (5, 5), 1, False, None)
    keypad = Keypad(
        lambda: event, 0, 0, 10, 10, cols=1, rows=1, keys=["pressed"])
    check(keypad.read() == "pressed",
          "legacy touch keypad did not return a scalar key")


class FakeDisplay:
    width = 222
    height = 480
    rotation = 0


class FakeRuntime:
    def __init__(self, event):
        self.devices = ["touch"]
        self.touch_dev = "touch"
        self._pending = [event]
        self.calls = []

    def poll(self):
        pending = self._pending
        self._pending = []
        return pending

    def subscribe(self, callback, event_types=None, device_types=None):
        self.calls.append(("subscribe", callback, event_types, device_types))

    def unsubscribe(self, callback, event_types=None, device_types=None):
        self.calls.append(("unsubscribe", callback, event_types, device_types))

    def register(self, device):
        self.devices.append(device)

    def unregister(self, device):
        self.devices.remove(device)

    def request_quit(self):
        self.calls.append(("quit",))


def probe_board_adapter():
    import events
    import eventsys

    event = events.Button(
        events.MOUSEBUTTONDOWN, (7, 9), 1, False, None)
    fake_runtime = FakeRuntime(event)

    class RuntimeFactory:
        @classmethod
        def from_board_config(cls, board):
            check(board is fake_board,
                  "board adapter did not pass the current board to Runtime")
            return fake_runtime

    class Board:
        pass

    fake_board = Board()
    fake_board.display_bus = object()
    fake_board.display_drv = FakeDisplay()
    fake_board.i2c = object()
    fake_board.touch = object()
    fake_board.touch_read = lambda: None
    fake_board.touch_rotation_table = (0, 5, 6, 3)

    previous_board = sys.modules.get("board_config")
    previous_runtime = eventsys.Runtime
    sys.modules["board_config"] = fake_board
    eventsys.Runtime = RuntimeFactory
    try:
        from board_configs.t_display_s3_pro import board_config as legacy
    finally:
        eventsys.Runtime = previous_runtime
        if previous_board is None:
            del sys.modules["board_config"]
        else:
            sys.modules["board_config"] = previous_board

    check(legacy.display_drv is fake_board.display_drv,
          "legacy display export did not use the current board")
    check(legacy.touch_drv is fake_board.touch,
          "legacy touch export did not use the current board")
    check(legacy.touch_dev == "touch",
          "legacy touch device export did not use the current runtime")
    check(legacy.broker.poll() is event,
          "legacy broker did not convert runtime lists to scalar events")
    legacy.broker.quit()
    check(fake_runtime.calls[-1] == ("quit",),
          "legacy broker did not delegate quit")


def main():
    if len(sys.argv) not in (2, 3):
        raise ValueError(
            "usage: micropython pydevices_candidate_compat.py "
            "RUNTIME_ROOT [QOI_FIXTURE]")
    runtime_root = sys.argv[1].replace("\\", "/").rstrip("/")
    sys.path.insert(0, runtime_root)
    qoi_fixture = sys.argv[2] if len(sys.argv) == 3 else None

    probe_graphics()
    probe_palettes()
    probe_keys()
    probe_images(qoi_fixture)
    probe_touch_keypad()
    probe_board_adapter()
    print("PYDEVICES_CANDIDATE_COMPAT_OK checks=%s" % CHECKS)


main()
