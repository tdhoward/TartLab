"""Build a cheerful face from direct framebuffer drawing primitives."""

from tartlabutils.modern_app import DirectCanvas, game_surface, rgb565


surface = game_surface()
canvas = DirectCanvas(surface)

BACKGROUND = rgb565(16, 24, 32)
ORANGE = rgb565(255, 152, 0)
DARK = rgb565(32, 32, 32)
WHITE = rgb565(255, 255, 255)


def fill_circle(center_x, center_y, radius, color):
    """Fill a circle one horizontal run of pixels at a time."""
    radius_squared = radius * radius
    for y in range(-radius, radius + 1):
        half_width = int((radius_squared - y * y) ** 0.5)
        canvas.hline(
            center_x - half_width, center_y + y,
            half_width * 2 + 1, color)


canvas.fill(BACKGROUND)
radius = min(surface.height // 2 - 10, surface.width // 4 - 10)
center_x = radius + 10
center_y = surface.height // 2
fill_circle(center_x, center_y, radius, ORANGE)

eye_radius = max(6, radius // 10)
eye_y = center_y - radius // 3
fill_circle(center_x - radius // 3, eye_y, eye_radius, DARK)
fill_circle(center_x + radius // 3, eye_y, eye_radius, DARK)

# Approximate a smile by connecting points along an upside-down parabola.
mouth_half = radius // 2
mouth_top = center_y + radius // 5
previous = None
for offset in range(-mouth_half, mouth_half + 1, 2):
    drop = (mouth_half * mouth_half - offset * offset) // (mouth_half * 3)
    point = center_x + offset, mouth_top + drop
    if previous is not None:
        for thickness in range(4):
            canvas.line(
                previous[0], previous[1] + thickness,
                point[0], point[1] + thickness, DARK)
    previous = point

message_x = center_x + radius + 24
canvas.text("HELLO!", message_x, center_y - 12, WHITE)
canvas.text("DRAWN PIXEL BY PIXEL", message_x, center_y + 8, WHITE)
canvas.show()
