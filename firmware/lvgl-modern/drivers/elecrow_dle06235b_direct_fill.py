"""Low-level blocking QSPI fill diagnostic for the Elecrow DLE06235B."""

import machine
import lcd_bus
import time

from _st77922_init import _INIT


def command(value):
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

chunk_rows = 16
buffer_size = 320 * chunk_rows * 2
buffer = bus.allocate_framebuffer(
    buffer_size, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
)
bus.init(320, 480, 16, buffer_size, False, 32, 8)

for register, params, delay_ms in _INIT:
    bus.tx_param(command(register), params if params else None)
    if delay_ms:
        time.sleep_ms(delay_ms)

machine.Pin(41, machine.Pin.OUT, value=1)

colors = (
    (0, 160, b"\xF8\x00"),
    (160, 320, b"\x07\xE0"),
    (320, 480, b"\x00\x1F"),
)
pixel_command = 0x32000000 | (0x2C << 8)

for band_start, band_end, pixel in colors:
    buffer[:] = pixel * (len(buffer) // 2)
    for y_start in range(band_start, band_end, chunk_rows):
        y_end = min(y_start + chunk_rows, band_end) - 1
        bus.tx_param(command(0x2A), b"\x00\x00\x01\x3F")
        bus.tx_param(
            command(0x2B),
            bytes((y_start >> 8, y_start & 0xFF, y_end >> 8, y_end & 0xFF)),
        )
        bus.tx_color(
            pixel_command,
            buffer,
            0,
            y_start,
            319,
            y_end,
            0,
            True,
        )

print("ELECROW_DIRECT_FILL_OK")
