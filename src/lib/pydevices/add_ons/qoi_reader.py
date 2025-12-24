"""
qoi_reader.py — MicroPython-friendly decoder for the Quite OK Image format (QOI).

Add-on (2025-07-29): `QOIImage.as_rgb565()` helper converts the decoded
pixels into big-endian RGB565 so they can be blitted straight to common
ILI9xxx / ST77xx display drivers.

Typical use on PyDevices-style display:

    from qoi_reader import QOIImage

    img = QOIImage.open("/flash/logo.qoi")
    buf = img.as_rgb565()
    display.blit_buffer(buf, 0, 0, img.width, img.height)
"""

import struct

__all__ = ("QOIImage",)

# ---------------------------------------------------------------------------
# QOI constants and helpers
# ---------------------------------------------------------------------------
_QOI_MAGIC = b"qoif"
_QOI_HEADER_SIZE = 14
_QOI_END_MARKER = b"\x00" * 8 + b"\x01"

_QOI_OP_INDEX = 0x00  # 00xxxxxx
_QOI_OP_DIFF  = 0x40  # 01xxxxxx
_QOI_OP_LUMA  = 0x80  # 10xxxxxx
_QOI_OP_RUN   = 0xC0  # 11xxxxxx
_QOI_OP_RGB   = 0xFE
_QOI_OP_RGBA  = 0xFF


def _index_pos(r, g, b, a):
    """Hash function for the 64-slot pixel index (spec-compliant)."""
    return (r * 3 + g * 5 + b * 7 + a * 11) & 0x3F


class QOIImage:
    """Minimal QOI decoder yielding raw RGB / RGBA bytes.

    Attributes
    ----------
    width, height : int        Image dimensions (px)
    channels       : int        3 = RGB, 4 = RGBA
    colorspace     : int        0 = sRGB w/ linear alpha, 1 = all linear
    pixels         : bytes      Packed pixel data (row-major)
    """

    def __init__(self, w, h, channels, colorspace, pixels):
        self.width = w
        self.height = h
        self.channels = channels
        self.colorspace = colorspace
        self.pixels = pixels  # immutable bytes keeps RAM low

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    @classmethod
    def open(cls, path):
        """Decode *path* (str) and return a QOIImage instance."""
        with open(path, "rb") as f:
            buf = f.read()
        return cls._decode(buf)

    @classmethod
    def loads(cls, buf):
        """Decode from an in-memory *bytes / bytearray* buffer."""
        return cls._decode(buf)

    def as_rgb565(self):
        """Return packed RGB565 bytes (MSB first) suitable for `blit_buffer()`.

        Alpha (if present) is discarded — fully transparent pixels become 0x0000.
        """
        out = bytearray(self.width * self.height * 2)
        p_out = 0
        pix = self.pixels
        if self.channels == 3:
            step = 3
            for i in range(0, len(pix), step):
                r, g, b = pix[i], pix[i + 1], pix[i + 2]
                rgb = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                out[p_out] = rgb >> 8
                out[p_out + 1] = rgb & 0xFF
                p_out += 2
        else:
            step = 4
            for i in range(0, len(pix), step):
                r, g, b, a = pix[i], pix[i + 1], pix[i + 2], pix[i + 3]
                if a == 0:
                    rgb = 0  # treat fully transparent as black
                else:
                    rgb = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                out[p_out] = rgb >> 8
                out[p_out + 1] = rgb & 0xFF
                p_out += 2
        return bytes(out)

    # ---------------------------------------------------------------------
    # Core decoder (spec-compliant, no external deps)
    # ---------------------------------------------------------------------
    @classmethod
    def _decode(cls, buf):
        if len(buf) < _QOI_HEADER_SIZE + len(_QOI_END_MARKER):
            raise ValueError("Truncated QOI stream")
        if buf[0:4] != _QOI_MAGIC:
            raise ValueError("Missing QOI magic")

        w, h, channels, colorspace = struct.unpack(">IIbb", buf[4:14])
        if channels not in (3, 4):
            raise ValueError("Channels must be 3 (RGB) or 4 (RGBA)")
        if w == 0 or h == 0:
            raise ValueError("Invalid image dimensions")

        out = bytearray(w * h * channels)
        index = [[0, 0, 0, 0] for _ in range(64)]

        r = g = b = 0
        a = 255
        p_in = 14  # read pointer (after header)
        p_px = 0   # pixel index (0 .. w*h-1)

        while p_px < w * h:
            byte = buf[p_in]
            p_in += 1

            if byte == _QOI_OP_RGB:
                r, g, b = buf[p_in:p_in + 3]
                p_in += 3
            elif byte == _QOI_OP_RGBA:
                r, g, b, a = buf[p_in:p_in + 4]
                p_in += 4
            else:
                tag = byte & 0xC0
                if tag == _QOI_OP_INDEX:
                    r, g, b, a = index[byte & 0x3F]
                elif tag == _QOI_OP_DIFF:
                    r = (r + ((byte >> 4) & 0x03) - 2) & 0xFF
                    g = (g + ((byte >> 2) & 0x03) - 2) & 0xFF
                    b = (b + (byte & 0x03) - 2) & 0xFF
                elif tag == _QOI_OP_LUMA:
                    byte2 = buf[p_in]
                    p_in += 1
                    dg = (byte & 0x3F) - 32
                    dr = ((byte2 >> 4) & 0x0F) - 8 + dg
                    db = (byte2 & 0x0F) - 8 + dg
                    r = (r + dr) & 0xFF
                    g = (g + dg) & 0xFF
                    b = (b + db) & 0xFF
                elif tag == _QOI_OP_RUN:
                    run = (byte & 0x3F) + 1
                    for _ in range(run):
                        cls._write_pixel(out, p_px, channels, r, g, b, a)
                        p_px += 1
                    continue  # next opcode

            # Regular pixel path ↓
            idx = _index_pos(r, g, b, a)
            index[idx] = [r, g, b, a]
            cls._write_pixel(out, p_px, channels, r, g, b, a)
            p_px += 1

        return cls(w, h, channels, colorspace, bytes(out))

    # ------------------------------------------------------------------
    # Utility — inlined for speed under MicroPython
    # ------------------------------------------------------------------
    @staticmethod
    def _write_pixel(buf, idx, ch, r, g, b, a):
        if ch == 3:
            pos = idx * 3
            buf[pos] = r
            buf[pos + 1] = g
            buf[pos + 2] = b
        else:
            pos = idx * 4
            buf[pos] = r
            buf[pos + 1] = g
            buf[pos + 2] = b
            buf[pos + 3] = a
