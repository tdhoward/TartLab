"""A portrait touch racer using accelerated region scrolling when available."""

from random import choice, randint
from time import sleep_ms

from tartlabutils.modern_app import (
    PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)


surface = game_surface()
canvas = PortraitCanvas(surface)

# Tapping either half of the portrait screen steers the car one step.
touch = PortraitTouchGrid(("left", "right"), 2, 1)

BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
GREEN = rgb565(34, 139, 34)
YELLOW = rgb565(255, 214, 0)
OBSTACLE_COLORS = (
    rgb565(244, 67, 54),
    rgb565(33, 150, 243),
    rgb565(156, 39, 176),
    rgb565(255, 152, 0),
)

WIDTH = canvas.width
HEIGHT = canvas.height
HEADER_HEIGHT = 24
TRACK_TOP = HEADER_HEIGHT
TRACK_HEIGHT = HEIGHT - TRACK_TOP
ROAD_MARGIN = WIDTH // 6
ROAD_LEFT = ROAD_MARGIN
ROAD_RIGHT = WIDTH - ROAD_MARGIN
ROAD_WIDTH = ROAD_RIGHT - ROAD_LEFT

SCROLL_STEP = 4
FRAME_DELAY = 32
CENTER_PERIOD = 48
CENTER_RADIUS = 3
CAR_RADIUS = 11
CAR_Y = HEIGHT - 54
STEER_STEP = 18
OBSTACLE_GAP = 92

center_phase = 0
spawn_distance = 0
car_x = WIDTH // 2
obstacles = []


def filled_circle(x, y, radius, color):
    """Draw a filled circle from horizontal runs."""
    radius_squared = radius * radius
    for offset_y in range(-radius, radius + 1):
        half_width = int((radius_squared - offset_y * offset_y) ** 0.5)
        canvas.hline(
            x - half_width, y + offset_y,
            half_width * 2 + 1, color)


def draw_centerline(top, bottom):
    """Draw only the part of each center dot inside a vertical interval."""
    center_y = TRACK_TOP + center_phase - CENTER_PERIOD
    while center_y - CENTER_RADIUS < bottom:
        if center_y + CENTER_RADIUS >= top:
            radius_squared = CENTER_RADIUS * CENTER_RADIUS
            first_y = max(top, center_y - CENTER_RADIUS)
            last_y = min(bottom - 1, center_y + CENTER_RADIUS)
            for y in range(first_y, last_y + 1):
                offset_y = y - center_y
                half_width = int(
                    (radius_squared - offset_y * offset_y) ** 0.5)
                canvas.hline(
                    WIDTH // 2 - half_width, y,
                    half_width * 2 + 1, WHITE)
        center_y += CENTER_PERIOD


def draw_track_band(top, height):
    """Rebuild a horizontal slice of grass, road, and center dots."""
    canvas.fill_rect(0, top, WIDTH, height, GREEN)
    canvas.fill_rect(ROAD_LEFT, top, ROAD_WIDTH, height, BLACK)
    draw_centerline(top, top + height)


def draw_header():
    """Redraw the header so it appears fixed over the scrolling canvas."""
    canvas.fill_rect(0, 0, WIDTH, HEADER_HEIGHT, BLACK)
    canvas.text("RACER  TAP LEFT / RIGHT", 8, 8, WHITE)


def draw_obstacle(obstacle):
    filled_circle(
        obstacle[0], obstacle[1], obstacle[2], obstacle[3])


def obstacle_intersects(obstacle, area):
    x, y, radius, unused_color = obstacle
    left, top, width, height = area
    return not (
        x + radius < left or x - radius >= left + width or
        y + radius < top or y - radius >= top + height)


def spawn_obstacle(y=None):
    radius = randint(7, 12)
    x = randint(
        ROAD_LEFT + radius + 3,
        ROAD_RIGHT - radius - 4)
    obstacle = [
        x,
        TRACK_TOP + radius if y is None else y,
        radius,
        choice(OBSTACLE_COLORS),
    ]
    obstacles.append(obstacle)
    return obstacle


def car_area(x, y):
    padding = 1
    return (
        x - CAR_RADIUS - padding,
        y - CAR_RADIUS - padding,
        (CAR_RADIUS + padding) * 2 + 1,
        (CAR_RADIUS + padding) * 2 + 1,
    )


def combined_area(first, second):
    left = min(first[0], second[0])
    top = min(first[1], second[1])
    right = max(first[0] + first[2], second[0] + second[2])
    bottom = max(first[1] + first[3], second[1] + second[3])
    return left, top, right - left, bottom - top


def redraw_car(old_x):
    """Erase the car copy moved by scrolling, then redraw it in place."""
    dirty = combined_area(
        car_area(old_x, CAR_Y + SCROLL_STEP),
        car_area(car_x, CAR_Y))
    left, top, width, height = dirty

    # The car stays inside the road, so this patch starts with black asphalt.
    canvas.fill_rect(left, top, width, height, BLACK)
    draw_centerline(top, top + height)
    changed_rows = (0, top, WIDTH, height)
    for obstacle in obstacles:
        # draw_centerline may touch pixels outside the car's horizontal dirty
        # bounds.  Restore every obstacle in those rows so RAM remains the
        # canonical copy for the next scroll.
        if obstacle_intersects(obstacle, changed_rows):
            draw_obstacle(obstacle)
    filled_circle(car_x, CAR_Y, CAR_RADIUS, YELLOW)
    canvas.show(dirty)


canvas.fill(BLACK)
draw_track_band(TRACK_TOP, TRACK_HEIGHT)
for initial_y in (TRACK_TOP + 75, TRACK_TOP + 185, TRACK_TOP + 300):
    draw_obstacle(spawn_obstacle(initial_y))
filled_circle(car_x, CAR_Y, CAR_RADIUS, YELLOW)
draw_header()
canvas.show()

while True:
    old_car_x = car_x
    key = touch.read()
    if key == "left":
        car_x = max(ROAD_LEFT + CAR_RADIUS + 2, car_x - STEER_STEP)
    elif key == "right":
        car_x = min(ROAD_RIGHT - CAR_RADIUS - 3, car_x + STEER_STEP)

    # Keep the header fixed and scroll only the track. The canvas uses its
    # compiled strided-copy path for this partial framebuffer region. Qualified
    # hardware also moves panel scanout and uploads only the exposed band;
    # other displays use the portable software fallback.
    canvas.scroll_region(
        (0, TRACK_TOP, WIDTH, TRACK_HEIGHT),
        dy=SCROLL_STEP,
        fill=GREEN)

    center_phase = (center_phase + SCROLL_STEP) % CENTER_PERIOD
    for obstacle in obstacles:
        obstacle[1] += SCROLL_STEP
    obstacles[:] = [
        obstacle for obstacle in obstacles
        if obstacle[1] - obstacle[2] < HEIGHT]

    # Rebuild the newly exposed track band with the road and centerline.
    draw_track_band(TRACK_TOP, SCROLL_STEP)
    canvas.show((0, TRACK_TOP, WIDTH, SCROLL_STEP))

    spawn_distance += SCROLL_STEP
    if spawn_distance >= OBSTACLE_GAP:
        spawn_distance -= OBSTACLE_GAP
        new_obstacle = spawn_obstacle()
        draw_obstacle(new_obstacle)
        radius = new_obstacle[2]
        canvas.show((
            new_obstacle[0] - radius,
            new_obstacle[1] - radius,
            radius * 2 + 1,
            radius * 2 + 1))

    redraw_car(old_car_x)
    sleep_ms(FRAME_DELAY)
