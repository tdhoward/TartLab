# SPDX-FileCopyrightText: Tony DiCola, 2024 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""
PyDevices pygfx.binfont

A module to draw text to a canvas using fonts from
https://github.com/spacerace/romfont
"""

import os
import struct
from area import Area


if hasattr(os, "sep"):
    sep = os.sep  # PyScipt doesn't have os.sep
else:
    sep = "/"

# get the path this module is in
font_dir = __file__.split(sep)[0:-1]
font_dir = sep.join(font_dir) + sep

# Default font file to use if none is specified.
# Should be 8 pixels wide to keep framebuf.py compatible with MicroPython framebuf module
_FONTS = {
    8: f"{font_dir}binfont_8x8.bin",
    14: f"{font_dir}binfont_8x14.bin",
    16: f"{font_dir}binfont_8x16.bin",
}
_DEFAULT_FONT = _FONTS[8]


def text(*args, height=8, **kwargs):
    if height == 8:
        return text8(*args, **kwargs)
    if height == 14:
        return text14(*args, **kwargs)
    if height == 16:
        return text16(*args, **kwargs)
    raise ValueError("Unsupported font height: %d" % height)


def text8(canvas, s, x, y, c=1, scale=1, inverted=False, font_file=None):
    """Place text on the canvas.  Breaks on \n to next line.

    Does not break on line going off canvas.
    """
    height=8
    if (
        not hasattr(BinFont, "_text8font")
        or (font_file is not None and BinFont._text8font.font_file != font_file)
        or (height is not None and BinFont._text8font.height != height)
    ):
        # load the font!
        BinFont._text8font = BinFont(font_file, height)

    return BinFont._text8font.text(canvas, s, x, y, c, scale, inverted)


def text14(canvas, s, x, y, c=1, scale=1, inverted=False, font_file=None):
    """Place text on the screen.  Breaks on \n to next line.

    Does not break on line going off screen.
    """
    height=14
    if (
        not hasattr(BinFont, "_text14font")
        or (font_file is not None and BinFont._text14font.font_file != font_file)
        or (height is not None and BinFont._text14font.height != height)
    ):
        # load the font!
        BinFont._text14font = BinFont(font_file, height)

    return BinFont._text14font.text(canvas, s, x, y, c, scale, inverted)


def text16(canvas, s, x, y, c=1, scale=1, inverted=False, font_file=None):
    """Place text on the screen.  Breaks on \n to next line.

    Does not break on line going off screen.
    """
    height = 16
    if (
        not hasattr(BinFont, "_text16font")
        or (font_file is not None and BinFont._text16font.font_file != font_file)
        or (height is not None and BinFont._text16font.height != height)
    ):
        # load the font!
        BinFont._text16font = BinFont(font_file, height)

    return BinFont._text16font.text(canvas, s, x, y, c, scale, inverted)


class BinFont:
    """A helper class to read binary font tiles and 'seek' through them as a
    file to display in a canvas or directly on screen. We use file access
    so we dont waste 1KB of RAM on a font!"""

    def __init__(self, font_file=None, height=None, cached=True):
        # Specify the drawing area width and height, and the pixel function to
        # call when drawing pixels (should take an x and y param at least).
        # Optionally specify font_file to override the font file to use (default
        # is vga_8x8.bin).  The font format is a binary file with the following
        # format:
        # - x bytes: font data, in ASCII order covering 128 or all 256 characters.
        #            Each character should have a byte for each pixel row of
        #            data (i.e. a 8x8 font has 8 bytes per character).
        self.font_file = (
            font_file if font_file else _FONTS.get(height, _DEFAULT_FONT)
        )
        self.font_name = self.font_file.split(sep)[-1].split(".")[0]
        self._font_height = height or int(self.font_name.split("x")[-1])
        # Note that only fonts up to 8 pixels wide are currently supported.
        self._font_width = 8

        # Open the font file.
        try:
            font_path = self.font_file
            self._font = open(font_path, "rb")
            # simple font file validation check based on expected file size
            filesize = os.stat(font_path)[6]
            if (
                filesize != 256 * self.height
                and filesize != 128 * self.height
            ):
                raise RuntimeError(
                    f"Invalid font file: {self.font_file} is {filesize} bytes, expected {256 * self.height}"
                )
        except OSError:
            print("Could not find font file", self.font_file)
            raise
        except OverflowError:
            # os.stat can throw this on boards without long int support
            # just hope the font file is valid and press on
            pass

        if cached:
            self._cache = self._font.read()
            self._font.close()
        else:
            self._cache = None

    @property
    def width(self):
        """Return the width of the font in pixels."""
        return self._font_width

    @property
    def height(self):
        """Return the height of the font in pixels."""
        return self._font_height

    def deinit(self):
        """Close the font file as cleanup."""
        if not self._cache:
            self._font.close()

    def __enter__(self):
        """Initialize/open the font file"""
        self.__init__()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """cleanup on exit"""
        self.deinit()

    def draw_char(self, char, x, y, canvas, color, scale=1, inverted=False):
        """Draw one character at position (x,y) to a canvas in a given color"""
        scale = max(scale, 1)
        # Don't draw the character if it will be clipped off the visible area.
        # if x < -self.width or x >= canvas.width or \
        #   y < -self.height or y >= canvas.height:
        #    return
        # Go through each row of the character.
        for char_y in range(self._font_height):
            # Grab the byte for the current row of font data.
            if not (line := self._read_line(char, char_y)):
                continue  # maybe character isnt there? go to next
            # Go through each column in the row byte.
            for char_x in range(self.width):
                # Draw a pixel for each bit that's flipped on.
                if (line >> (self.width - char_x - 1)) & 0x1:
                    canvas.fill_rect(
                        (
                            x + char_x * scale
                            if not inverted
                            else x + (self._font_width - char_x - 1) * scale
                        ),
                        (
                            y + char_y * scale
                            if not inverted
                            else y + (self._font_height - char_y - 1) * scale
                        ),
                        scale,
                        scale,
                        color,
                    )
        return Area(x, y, self._font_width * scale, self._font_height * scale)

    def text(self, canvas, string, x, y, color, scale=1, inverted=False):
        """Write text to the canvas at the specified position in the specified color."""
        if inverted:
            string = "".join(reversed(string))

        char_y = y
        largest_x = 0  # the last x position reached on the longest line
        for chunk in string.split("\n"):
            last_x = x  # the last x position reached on the current line
            for i, char in enumerate(chunk):
                char_x = x + (i * self.width * scale)
                if char_x < canvas.width if hasattr(canvas, "width") else True:
                    if char_y < canvas.height if hasattr(canvas, "height") else True:
                        if char_x + (self.width * scale) > 0:
                            if char_y + (self.height * scale) > 0:
                                self.draw_char(
                                    char,
                                    char_x,
                                    char_y,
                                    canvas,
                                    color,
                                    scale=scale,
                                    inverted=inverted,
                                )
                                last_x = char_x + (self.width * scale)
            largest_x = max([largest_x, last_x])  # update the largest x position
            char_y += self.height * scale
        return Area(x, y, largest_x - x, char_y - y)

    def text_width(self, text, scale=1):
        """Return the pixel width of the specified text message."""
        return len(text) * self._font_width * scale

    def _read_line(self, char, line):
        """Read a line of font data for a character."""
        if self._cache:
            return self._cache[(ord(char) * self.height) + line]
        self._font.seek((ord(char) * self.height) + line)
        try:
            return struct.unpack("B", self._font.read(1))[0]
        except RuntimeError:  # maybe character isnt there? go to next
            return None