# Example of basic drawing functions.

from hdwconfig import display_drv    # Get the display ready
import pygfx                         # Bring in the drawing functions
from pygfx.palettes import get_palette   # ...and the ability to set up palettes of colors

# Set up the display orientation (horizontal or vertical)
HEIGHT = display_drv.height
WIDTH = display_drv.width
if HEIGHT > WIDTH:
    TALL = display_drv.rotation
    WIDE = display_drv.rotation + 90
else:
    WIDE = display_drv.rotation
    TALL = display_drv.rotation + 90
display_drv.rotation = WIDE   # We want horizontal

pal = get_palette("material_design")  # Set up the palette of colors that we want

# Figure out some reference points
CENTER_X = display_drv.width // 2
CENTER_Y = display_drv.height // 2
BASE_UNIT = min([display_drv.width, display_drv.height]) // 2

# Fill the screen with a solid color
display_drv.fill(pal.BLACK)

# Draw a filled circle
# pygfx.circle(canvas, x, y, radius, color, is_it_filled)
pygfx.circle(display_drv, CENTER_X, CENTER_Y, BASE_UNIT, pal.BLUE, True)

# Draw a rounded rectangle
# pygfx.round_rect(canvas, x, y, w, h, corner_radius, color, is_it_filled)
pygfx.round_rect(display_drv, 20, 20, 75, 150, BASE_UNIT//7, pal.RED, True)

# Draw a square
# pygfx.rect(canvas, x, y, w, h, color)
pygfx.rect(display_drv, 300, 50, 120, 120, pal.YELLOW)

# Write some text
# pygfx.text(canvas, text_string, x, y, color, scale)
pygfx.text(display_drv, "Drawing demo!", 100, 110, pal.WHITE, 2)

# Other drawing functions to try:
# pygfx.line(canvas, x0, y0, x1, y1, color)
# pygfx.pixel(canvas, x, y, color)
# pygfx.fill_rect(canvas, x, y, w, h, color)
# pygfx.gradient_rect(canvas, x, y, w, h, color1, color2, vertical=True):
# pygfx.arc(canvas, x, y, radius, angle0, angle1, color)
# pygfx.ellipse(canvas, x0, y0, radius1, radius2, color, is_it_filled)
