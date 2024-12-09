# Same as "moire slow", but uses a buffer to make things faster

from pygfx.displaybuf import DisplayBuffer as SSD
from hdwconfig import display_drv
from pygfx.framebuf_plus import FrameBuffer, RGB565
import pygfx                         # Bring in the drawing functions

# Set the display orientation to horizontal
display_drv.rotation = 90

HEIGHT = display_drv.height
WIDTH = display_drv.width

if display_drv.requires_byte_swap:
    needs_swap = display_drv.disable_auto_byte_swap(True)
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


# Set up a buffer representing the whole screen.
canvas = SSD(display_drv, SSD.RGB565)

# Then, we can draw things on the canvas before showing it on the screen.
canvas.fill(pal.BLACK)
canvas.show()

# Use loops to draw one line at a time to the canvas, then display on the screen
x = 0
while x < CENTER_X:
	# Draw lines from the top left corner to along the bottom of the screen
	pygfx.line(canvas, 0, 0, x, HEIGHT - 1, pal.GREEN)
	x = x + 4
canvas.show()  # this updates the screen with the whole canvas

x = 0
while x < CENTER_X:
	# Draw lines from the bottom center point to along the top of the screen
	pygfx.line(canvas, CENTER_X, HEIGHT - 1, x, 0, pal.YELLOW)
	x = x + 4
canvas.show()
	
while x < WIDTH:
	# Draw lines from the bottom center point to along the top of the screen
	pygfx.line(canvas, CENTER_X, HEIGHT - 1, x, 0, pal.ORANGE)
	x = x + 4
canvas.show()
	
x = CENTER_X
while x < WIDTH:
	# Draw lines from the top right corner to along the bottom of the screen
	pygfx.line(canvas, WIDTH - 1, 0, x, HEIGHT - 1, pal.RED)
	x = x + 4
canvas.show()
