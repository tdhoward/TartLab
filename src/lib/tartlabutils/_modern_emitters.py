"""Private MicroPython emitters for modern direct drawing."""

import micropython


@micropython.viper
def swap565(buffer, size: int):
    """Swap byte pairs in one validated, writable RGB565 byte buffer."""
    # The public wrapper validates writability and an even byte count. A ptr8
    # is safe here because byte order, rather than 16-bit host alignment, is
    # the operation being changed. Cast once before entering the tight loop.
    data = ptr8(buffer)  # noqa: F821
    for offset in range(0, size, 2):
        first = data[offset]
        data[offset] = data[offset + 1]
        data[offset + 1] = first
