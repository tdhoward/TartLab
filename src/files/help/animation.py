"""Animate a primitive shape with direct dirty-rectangle updates."""

from time import sleep_ms

from tartlabutils.modern_app import DirectCanvas, game_surface, rgb565


surface = game_surface()
canvas = DirectCanvas(surface)

BACKGROUND = rgb565(16, 24, 32)
RED = rgb565(244, 67, 54)
WHITE = rgb565(255, 255, 255)

size = 42
x = 0
y = 0
dx = 5
dy = 4

canvas.fill(BACKGROUND)
canvas.show()

for unused in range(180):
    old_x = x
    old_y = y
    x += dx
    y += dy
    if x <= 0 or x + size >= surface.width:
        dx = -dx
        x += dx
    if y <= 0 or y + size >= surface.height:
        dy = -dy
        y += dy

    # Erase the old position, draw the new one, then transfer only the union.
    left = min(old_x, x)
    top = min(old_y, y)
    right = max(old_x, x) + size
    bottom = max(old_y, y) + size
    canvas.fill_rect(left, top, right - left, bottom - top, BACKGROUND)
    canvas.fill_rect(x, y, size, size, RED)
    canvas.rect(x, y, size, size, WHITE)
    canvas.show((left, top, right - left, bottom - top))
    sleep_ms(16)
