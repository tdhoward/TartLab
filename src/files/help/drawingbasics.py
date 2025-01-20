# Example of basic drawing functions.

from hdwconfig import display_drv    # Get the display ready
import graphics                         # Bring in the drawing functions

# Set the display orientation to horizontal
display_drv.rotation = 90

HEIGHT = display_drv.height
WIDTH = display_drv.width

if display_drv.requires_byteswap:
    needs_swap = display_drv.disable_auto_byteswap(True)
else:
    needs_swap = False

# define the palette of colors
class pal:
    BLACK = 0x0000
    WHITE = 0xFFFF
    RED = 0xF800 if not needs_swap else 0x00F8
    GREEN = 0x07E0 if not needs_swap else 0xE007
    BLUE = 0x001F if not needs_swap else 0xF800
    CYAN = 0x07FF if not needs_swap else 0xFF07
    MAGENTA = 0xF81F if not needs_swap else 0x1FF8
    YELLOW = 0xFFE0 if not needs_swap else 0xE0FF
    ORANGE = 0xFD20 if not needs_swap else 0x20FD
    PURPLE = 0x8010 if not needs_swap else 0x1080
    GREY = 0x8410 if not needs_swap else 0x1084


# Figure out some reference points
CENTER_X = display_drv.width // 2
CENTER_Y = display_drv.height // 2
BASE_UNIT = min([display_drv.width, display_drv.height]) // 2

# Fill the screen with a solid color
display_drv.fill(pal.BLACK)

# Draw a filled circle
# graphics.circle(canvas, x, y, radius, color, is_it_filled)
graphics.circle(display_drv, CENTER_X, CENTER_Y, BASE_UNIT, pal.BLUE, True)

# Draw a rounded rectangle
# graphics.round_rect(canvas, x, y, w, h, corner_radius, color, is_it_filled)
graphics.round_rect(display_drv, 20, 20, 75, 150, BASE_UNIT//7, pal.RED, True)

# Draw a square
# graphics.rect(canvas, x, y, w, h, color)
graphics.rect(display_drv, 300, 50, 120, 120, pal.YELLOW)

# Write some text
# graphics.text(canvas, text_string, x, y, color, scale)
graphics.text(display_drv, "Drawing demo!", 100, 110, pal.WHITE, 2)

# Other drawing functions to try:
# graphics.line(canvas, x0, y0, x1, y1, color)
# graphics.pixel(canvas, x, y, color)
# graphics.fill_rect(canvas, x, y, w, h, color)
# graphics.gradient_rect(canvas, x, y, w, h, color1, color2, vertical=True):
# graphics.arc(canvas, x, y, radius, angle0, angle1, color)
# graphics.ellipse(canvas, x0, y0, radius1, radius2, color, is_it_filled)
