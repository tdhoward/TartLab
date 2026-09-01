# Example of simple animation (movement) with a bouncing ball

from hdwconfig import display_drv    # Get the display ready
import graphics                         # Bring in the drawing functions
from displaybuf import DisplayBuffer as SSD     # Get display buffer stuff
from graphics import FrameBuffer,RGB565
from graphics import Area
from time import ticks_ms, sleep_ms   # Helps us keep time to smooth out the movement

# Set the display orientation to horizontal
display_drv.rotation = 90

# Get the size of the display
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


# Set up a canvas representing the whole screen.
canvas = SSD(display_drv, SSD.RGB565)

background = pal.BLACK  # set a variable to hold the background color

# Then, we can draw things on the canvas before showing it on the screen.
canvas.fill(background)
canvas.show()

# Also, we can create a buffer in memory, which is like another piece of canvas
size = 50  # how big do we want the "ball" buffer to be?  (In pixels)
ball = FrameBuffer(memoryview(bytearray(size*size*2)), size, size, RGB565)  # sets up the ball buffer

# draw the ball on its buffer first
ball.fill(background)
graphics.circle(ball, size // 2, size // 2, size // 2, pal.RED, True)
graphics.arc(ball, size // 2, size // 2, (size // 2) - 4, 210, 260, pal.WHITE)


TICKS = 8  # how many milliseconds should we wait between frames?

# x and y hold the position of the ball (top left corner)
x = 0
y = 0
speed = 5  # how big of steps is the ball taking between frames?

dx = speed  # variables to keep track of the direction that the ball is travelling
dy = speed

a_new = None  # variables to keep track of what areas on the screen needs updates
a_old = None

last = ticks_ms()  # take a snapshot of the current time

count = 0  # loop variable
while count < 100:  # we don't want it to run forever, otherwise we'll have to reset
	x = x + dx  # move the ball's x and y position based on what direction it's going
	y = y + dy
	
	# If we hit any walls, change the direction
	if x <= 0:
		dx = speed
	elif x + size > WIDTH:
		dx = -speed
	if y <= 0:
		dy = speed
	elif y + size > HEIGHT:
		dy = -speed
	
	# store the screen area that is changing for the new ball
	a_new = Area(x, y, size, size)
	if a_old is not None:
		canvas.fill_rect(a_old.x, a_old.y, a_old.w, a_old.h, background)  # blank out the old ball
		a_dirty = a_new + a_old   # store the whole dirty area (that needs a screen update)
	else:
		a_dirty = a_new
	canvas.blit(ball, x, y)  # draw the new ball on the canvas
	
	# figure out how long we need to wait before drawing the frame
	delta = ticks_ms() - last
	if delta < TICKS:
		sleep_ms(TICKS - delta)
	
	canvas.show(a_dirty)  # okay, update the screen in the dirty area!
	last = ticks_ms()  # store the snapshot of current time
	
	a_old = a_new  # the area of the new ball we just drew will need to be erased next time through the loop
	
	count = count + 1  # increment the loop variable
