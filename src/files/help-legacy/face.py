# Uses basic drawing functions to draw a face!

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


# Figure out the center location that we can use later
CENTER_X = display_drv.width // 2
CENTER_Y = display_drv.height // 2
BASE_UNIT = min([display_drv.width, display_drv.height]) // 2

# Fill the screen with a solid color
display_drv.fill(pal.BLACK)

# Draw a filled circle for the face
graphics.circle(display_drv, CENTER_X, CENTER_Y, BASE_UNIT, pal.ORANGE, True)

# The mouth is made from 3 different shapes:
graphics.circle(display_drv, CENTER_X, CENTER_Y, (BASE_UNIT // 3) * 2, pal.BLACK, True)
graphics.round_rect(display_drv, CENTER_X - 70, CENTER_Y, 140, 40, BASE_UNIT // 7, pal.ORANGE, True)
graphics.fill_rect(display_drv, CENTER_X - 80, 35, 160, 100, pal.ORANGE)

# The eyes are simple
graphics.circle(display_drv, CENTER_X - 25, CENTER_Y - 30, BASE_UNIT // 7, pal.BLACK, True)
graphics.circle(display_drv, CENTER_X + 25, CENTER_Y - 30, BASE_UNIT // 7, pal.BLACK, True)

# Eyebrows are trickier. We have to use more lines, because they are so thin.
graphics.arc(display_drv, CENTER_X - 25, CENTER_Y - 30, BASE_UNIT // 4, 240, 300, pal.BLACK)
graphics.arc(display_drv, CENTER_X + 25, CENTER_Y - 30, BASE_UNIT // 4, 240, 300, pal.BLACK)
graphics.arc(display_drv, CENTER_X - 25, CENTER_Y - 30, (BASE_UNIT // 4) + 1, 240, 300, pal.BLACK)
graphics.arc(display_drv, CENTER_X + 25, CENTER_Y - 30, (BASE_UNIT // 4) + 1, 240, 300, pal.BLACK)
graphics.arc(display_drv, CENTER_X - 25, CENTER_Y - 30, (BASE_UNIT // 4) + 2, 280, 300, pal.BLACK)
graphics.arc(display_drv, CENTER_X + 25, CENTER_Y - 30, (BASE_UNIT // 4) + 2, 240, 260, pal.BLACK)

# Bags under the eyes, for realism  :-)
graphics.arc(display_drv, CENTER_X - 25, CENTER_Y - 30, BASE_UNIT // 6, 45, 125, pal.GREY)
graphics.arc(display_drv, CENTER_X + 25, CENTER_Y - 30, BASE_UNIT // 6, 55, 135, pal.GREY)

# The nose
graphics.line(display_drv, CENTER_X, CENTER_Y - 20, CENTER_X + 15, CENTER_Y + 10, pal.BLACK)
graphics.line(display_drv, CENTER_X + 15, CENTER_Y + 10, CENTER_X - 5, CENTER_Y + 15, pal.BLACK)

# Now, write some text
graphics.text(display_drv, "Hi, I'm Tim!", 270, 130, pal.WHITE, 2)
