"""Draw a moire pattern, flushing each pair of direct-canvas lines."""

from time import sleep_ms

from tartlabutils.modern_app import DirectCanvas, game_surface, rgb565


surface = game_surface()
canvas = DirectCanvas(surface)

BLACK = rgb565(0, 0, 0)
GREEN = rgb565(0, 200, 83)
YELLOW = rgb565(255, 214, 0)
ORANGE = rgb565(255, 109, 0)
RED = rgb565(213, 0, 0)

width = surface.width
height = surface.height
center = width // 2
canvas.fill(BLACK)
canvas.show()

for x in range(0, width, 8):
    if x < center:
        canvas.line(0, 0, x, height - 1, GREEN)
        canvas.line(center, height - 1, x, 0, YELLOW)
    else:
        canvas.line(center, height - 1, x, 0, ORANGE)
        canvas.line(width - 1, 0, x, height - 1, RED)

    # This intentionally sends the framebuffer after every two lines.
    canvas.show()
    sleep_ms(18)
