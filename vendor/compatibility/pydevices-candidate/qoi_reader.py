# SPDX-License-Identifier: MIT
"""Small MicroPython-friendly decoder for the Quite OK Image format."""

import struct

__all__ = ("QOIImage",)

_QOI_MAGIC = b"qoif"
_QOI_HEADER_SIZE = 14
_QOI_END_MARKER = b"\x00" * 7 + b"\x01"
_QOI_OP_INDEX = 0x00
_QOI_OP_DIFF = 0x40
_QOI_OP_LUMA = 0x80
_QOI_OP_RUN = 0xC0
_QOI_OP_RGB = 0xFE
_QOI_OP_RGBA = 0xFF


def _index_pos(r, g, b, a):
    return (r * 3 + g * 5 + b * 7 + a * 11) & 0x3F


class QOIImage:
    def __init__(self, width, height, channels, colorspace, pixels):
        self.width = width
        self.height = height
        self.channels = channels
        self.colorspace = colorspace
        self.pixels = pixels

    @classmethod
    def open(cls, path):
        with open(path, "rb") as source:
            return cls._decode(source.read())

    @classmethod
    def loads(cls, data):
        return cls._decode(data)

    def as_rgb565(self):
        output = bytearray(self.width * self.height * 2)
        output_at = 0
        step = self.channels
        for at in range(0, len(self.pixels), step):
            r = self.pixels[at]
            g = self.pixels[at + 1]
            b = self.pixels[at + 2]
            if step == 4 and self.pixels[at + 3] == 0:
                rgb = 0
            else:
                rgb = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            output[output_at] = rgb >> 8
            output[output_at + 1] = rgb & 0xFF
            output_at += 2
        return bytes(output)

    @classmethod
    def _decode(cls, data):
        if len(data) < _QOI_HEADER_SIZE + len(_QOI_END_MARKER):
            raise ValueError("Truncated QOI stream")
        if data[0:4] != _QOI_MAGIC:
            raise ValueError("Missing QOI magic")
        width, height, channels, colorspace = struct.unpack(
            ">IIbb", data[4:14])
        if channels not in (3, 4):
            raise ValueError("Channels must be 3 (RGB) or 4 (RGBA)")
        if width == 0 or height == 0:
            raise ValueError("Invalid image dimensions")

        output = bytearray(width * height * channels)
        index = [[0, 0, 0, 0] for _ in range(64)]
        r = g = b = 0
        a = 255
        input_at = 14
        pixel_at = 0
        pixel_count = width * height
        while pixel_at < pixel_count:
            if input_at >= len(data) - len(_QOI_END_MARKER):
                raise ValueError("Truncated QOI pixel data")
            byte = data[input_at]
            input_at += 1
            if byte == _QOI_OP_RGB:
                if input_at + 3 > len(data):
                    raise ValueError("Truncated QOI RGB operation")
                r, g, b = data[input_at:input_at + 3]
                input_at += 3
            elif byte == _QOI_OP_RGBA:
                if input_at + 4 > len(data):
                    raise ValueError("Truncated QOI RGBA operation")
                r, g, b, a = data[input_at:input_at + 4]
                input_at += 4
            else:
                tag = byte & 0xC0
                if tag == _QOI_OP_INDEX:
                    r, g, b, a = index[byte & 0x3F]
                elif tag == _QOI_OP_DIFF:
                    r = (r + ((byte >> 4) & 0x03) - 2) & 0xFF
                    g = (g + ((byte >> 2) & 0x03) - 2) & 0xFF
                    b = (b + (byte & 0x03) - 2) & 0xFF
                elif tag == _QOI_OP_LUMA:
                    if input_at >= len(data):
                        raise ValueError("Truncated QOI luma operation")
                    byte2 = data[input_at]
                    input_at += 1
                    delta_g = (byte & 0x3F) - 32
                    r = (r + ((byte2 >> 4) & 0x0F) - 8 + delta_g) & 0xFF
                    g = (g + delta_g) & 0xFF
                    b = (b + (byte2 & 0x0F) - 8 + delta_g) & 0xFF
                elif tag == _QOI_OP_RUN:
                    run = (byte & 0x3F) + 1
                    if pixel_at + run > pixel_count:
                        raise ValueError("QOI run exceeds image dimensions")
                    for _ in range(run):
                        cls._write_pixel(output, pixel_at, channels, r, g, b, a)
                        pixel_at += 1
                    continue
            index[_index_pos(r, g, b, a)] = [r, g, b, a]
            cls._write_pixel(output, pixel_at, channels, r, g, b, a)
            pixel_at += 1
        if data[-len(_QOI_END_MARKER):] != _QOI_END_MARKER:
            raise ValueError("Missing QOI end marker")
        return cls(width, height, channels, colorspace, bytes(output))

    @staticmethod
    def _write_pixel(output, at, channels, r, g, b, a):
        target = at * channels
        output[target] = r
        output[target + 1] = g
        output[target + 2] = b
        if channels == 4:
            output[target + 3] = a
