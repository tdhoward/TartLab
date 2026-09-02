"""Draw pixels and primitive shapes on the modern direct canvas."""

from tartlabutils.modern_app import DirectCanvas, game_surface, rgb565


surface = game_surface()
canvas = DirectCanvas(surface)

BACKGROUND = rgb565(16, 24, 32)
BLUE = rgb565(21, 101, 192)
RED = rgb565(211, 47, 47)
YELLOW = rgb565(253, 216, 53)
WHITE = rgb565(255, 255, 255)

# FrameBuffer drawing changes RAM only. Nothing reaches the LCD until show().
canvas.fill(BACKGROUND)
canvas.fill_rect(20, 28, 76, 150, RED)
canvas.rect(surface.width - 140, 48, 120, 120, YELLOW)
canvas.line(0, 0, surface.width - 1, surface.height - 1, WHITE)
for x in range(108, 148, 3):
    canvas.pixel(x, 24, WHITE)

# A filled circle is just a set of horizontal pixel runs.
center_x = surface.width // 2
center_y = surface.height // 2
radius = min(surface.width, surface.height) // 3
radius_squared = radius * radius
for y in range(-radius, radius + 1):
    half_width = int((radius_squared - y * y) ** 0.5)
    canvas.hline(
        center_x - half_width, center_y + y,
        half_width * 2 + 1, BLUE)

canvas.text("DIRECT RGB565 DRAWING", 132, center_y - 4, WHITE)
canvas.show()
