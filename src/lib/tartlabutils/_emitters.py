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


@micropython.viper
def copy_rgb565_rows(buffer, source_start: int, target_start: int,
                     row_bytes: int, row_count: int, stride: int,
                     reverse_rows: int):
    """Copy overlapping RGB565 rows within one validated byte buffer.

    The caller guarantees byte-aligned offsets, complete in-bounds rows, and
    positive byte counts. Byte-wise copies preserve the framebuffer's stored
    endianness and avoid assumptions about native 16-bit alignment. Rows and
    bytes are traversed in memmove order so source and target may overlap.
    """
    data = ptr8(buffer)  # noqa: F821
    if reverse_rows:
        source_start += (row_count - 1) * stride
        target_start += (row_count - 1) * stride
        stride = -stride

    for unused_row in range(row_count):
        if target_start > source_start:
            offset = row_bytes
            while offset:
                offset -= 1
                data[target_start + offset] = data[source_start + offset]
        else:
            for offset in range(row_bytes):
                data[target_start + offset] = data[source_start + offset]
        source_start += stride
        target_start += stride


@micropython.viper
def copy_rgb565_rows_between(source_buffer, target_buffer,
                             source_start: int, target_start: int,
                             row_bytes: int, row_count: int,
                             source_stride: int, target_stride: int):
    """Copy RGB565 rows between two validated, non-overlapping buffers."""
    source = ptr8(source_buffer)  # noqa: F821
    target = ptr8(target_buffer)  # noqa: F821
    for unused_row in range(row_count):
        for offset in range(row_bytes):
            target[target_start + offset] = source[source_start + offset]
        source_start += source_stride
        target_start += target_stride
