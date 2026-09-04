"""A portrait touch-controlled scrolling racer for legacy firmware."""

from random import choice, randint
from time import sleep_ms

from displaybuf import DisplayBuffer as SSD
from eventsys.keys import Keys
import graphics
from hdwconfig import broker, display_drv
from touch_keypad import Keypad


display_drv.rotation = 0
if display_drv.width > display_drv.height:
    display_drv.rotation = 90

WIDTH = display_drv.width
HEIGHT = display_drv.height

if display_drv.requires_byteswap:
    needs_swap = display_drv.disable_auto_byteswap(True)
else:
    needs_swap = False


def color(native):
    if not needs_swap:
        return native
    return ((native & 0xFF) << 8) | ((native >> 8) & 0xFF)


BLACK = color(0x0000)
WHITE = color(0xFFFF)
GREEN = color(0x2444)
YELLOW = color(0xFEC0)
OBSTACLE_COLORS = (
    color(0xFBA7), color(0x24BF), color(0x9913), color(0xFCC0))

HEADER_HEIGHT = 24
TRACK_TOP = HEADER_HEIGHT
ROAD_MARGIN = WIDTH // 6
ROAD_LEFT = ROAD_MARGIN
ROAD_RIGHT = WIDTH - ROAD_MARGIN
ROAD_WIDTH = ROAD_RIGHT - ROAD_LEFT
SCROLL_STEP = 4
CENTER_PERIOD = 48
CAR_RADIUS = 11
CAR_Y = HEIGHT - 54
STEER_STEP = 18
OBSTACLE_GAP = 92

LEFT = Keys.K_LEFT
RIGHT = Keys.K_RIGHT
keypad = Keypad(
    broker.poll, 0, 0, WIDTH, HEIGHT,
    cols=2, rows=1, keys=(LEFT, RIGHT))
canvas = SSD(display_drv, SSD.RGB565)

center_phase = 0
spawn_distance = 0
car_x = WIDTH // 2
obstacles = []


def spawn_obstacle(y=None):
    radius = randint(7, 12)
    obstacle = [
        randint(
            ROAD_LEFT + radius + 3,
            ROAD_RIGHT - radius - 4),
        TRACK_TOP + radius if y is None else y,
        radius,
        choice(OBSTACLE_COLORS),
    ]
    obstacles.append(obstacle)


def draw_scene():
    canvas.fill(GREEN)
    canvas.fill_rect(
        ROAD_LEFT, TRACK_TOP,
        ROAD_WIDTH, HEIGHT - TRACK_TOP, BLACK)

    center_y = TRACK_TOP + center_phase
    while center_y < HEIGHT:
        graphics.circle(
            canvas, WIDTH // 2, center_y, 3, WHITE, True)
        center_y += CENTER_PERIOD

    for x, y, radius, obstacle_color in obstacles:
        graphics.circle(
            canvas, x, y, radius, obstacle_color, True)
    graphics.circle(
        canvas, car_x, CAR_Y, CAR_RADIUS, YELLOW, True)

    canvas.fill_rect(0, 0, WIDTH, HEADER_HEIGHT, BLACK)
    canvas.text("RACER  TAP LEFT / RIGHT", 8, 8, WHITE)
    canvas.show()


for initial_y in (TRACK_TOP + 75, TRACK_TOP + 185, TRACK_TOP + 300):
    spawn_obstacle(initial_y)

draw_scene()
while True:
    key = keypad.read()
    if key == LEFT:
        car_x = max(ROAD_LEFT + CAR_RADIUS + 2, car_x - STEER_STEP)
    elif key == RIGHT:
        car_x = min(ROAD_RIGHT - CAR_RADIUS - 3, car_x + STEER_STEP)

    center_phase = (center_phase + SCROLL_STEP) % CENTER_PERIOD
    for obstacle in obstacles:
        obstacle[1] += SCROLL_STEP
    obstacles[:] = [
        obstacle for obstacle in obstacles
        if obstacle[1] - obstacle[2] < HEIGHT]

    spawn_distance += SCROLL_STEP
    if spawn_distance >= OBSTACLE_GAP:
        spawn_distance -= OBSTACLE_GAP
        spawn_obstacle()

    # Legacy displays redraw the scene.  The modern help version uses the
    # same game with capability-driven panel scrolling where supported.
    draw_scene()
    sleep_ms(32)
