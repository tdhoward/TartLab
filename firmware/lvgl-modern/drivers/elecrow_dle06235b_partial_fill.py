"""Variable-length blocking QSPI diagnostic for the Elecrow DLE06235B."""

import lcd_bus
import machine
import time

from _st77922_init import _INIT


def _command(value):
    return 0x02000000 | ((value & 0xFF) << 8)


spi = machine.SPI.Bus(
    host=2,
    sck=12,
    quad_pins=(11, 13, 14, 9),
)
bus = lcd_bus.SPIBus(
    spi_bus=spi,
    dc=-1,
    freq=40_000_000,
    cs=10,
    quad=True,
)

buffer_size = 320 * 24 * 2
buffer = bus.allocate_framebuffer(
    buffer_size,
    lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA,
)
bus.init(320, 480, 16, buffer_size, False, 32, 8)

reset = machine.Pin(48, machine.Pin.OUT, value=1)
reset.value(0)
time.sleep_ms(100)
reset.value(1)
time.sleep_ms(100)

for register, params, delay_ms in _INIT:
    bus.tx_param(_command(register), params if params else None)
    if delay_ms:
        time.sleep_ms(delay_ms)

machine.Pin(41, machine.Pin.OUT, value=1)
pixel_command = 0x32000000 | (0x2C << 8)


def _fill_rect(x, y, width, height, pixel):
    size = width * height * 2
    data = memoryview(buffer)[:size]
    data[:] = pixel * (size // 2)
    x2 = x + width - 1
    y2 = y + height - 1
    bus.tx_param(
        _command(0x2A),
        bytes((x >> 8, x & 0xFF, x2 >> 8, x2 & 0xFF)),
    )
    bus.tx_param(
        _command(0x2B),
        bytes((y >> 8, y & 0xFF, y2 >> 8, y2 & 0xFF)),
    )
    bus.tx_color(pixel_command, data, x, y, x2, y2, 0, True)
    print(
        "PARTIAL_FILL x={} y={} width={} height={} bytes={}".format(
            x, y, width, height, size
        )
    )


# Proven transfer size: 20 full-width chunks cover the portrait screen.
for y in range(0, 480, 24):
    _fill_rect(0, y, 320, 24, b"\x00\x1F")

# A full-width control followed by a 128-through-132-pixel width sweep.
# All sweep rectangles have the same height, start X, color, and transport.
_fill_rect(0, 20, 320, 24, b"\x07\xE0")        # control
_fill_rect(20, 90, 128, 24, b"\x07\xE0")       # width mod 4 = 0
_fill_rect(20, 150, 129, 24, b"\x07\xE0")      # width mod 4 = 1
_fill_rect(20, 210, 130, 24, b"\x07\xE0")      # width mod 4 = 2
_fill_rect(20, 270, 131, 24, b"\x07\xE0")      # width mod 4 = 3
_fill_rect(20, 330, 132, 24, b"\x07\xE0")      # width mod 4 = 0

print("ELECROW_PARTIAL_FILL_READY")
