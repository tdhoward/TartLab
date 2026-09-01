"""A compact falling-block game for the modern direct renderer."""

from random import choice
from time import sleep_ms, ticks_diff, ticks_ms
import ujson as json

from tartlabutils.modern_app import (
    PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)


surface = game_surface()
canvas = PortraitCanvas(surface)
touch = PortraitTouchGrid((
    "rotate", "rotate", "rotate",
    "left", "pause", "right",
    "drop", "down", "drop",
), 3, 3)

BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
GREY = rgb565(90, 100, 110)
COLORS = (
    BLACK,
    rgb565(0, 188, 212),
    rgb565(255, 214, 0),
    rgb565(156, 39, 176),
    rgb565(76, 175, 80),
    rgb565(33, 150, 243),
    rgb565(244, 67, 54),
    rgb565(255, 152, 0),
)

SHAPES = (
    ((1, 1, 1, 1),),
    ((2, 2), (2, 2)),
    ((0, 3, 0), (3, 3, 3)),
    ((4, 4, 0), (0, 4, 4)),
    ((0, 5, 5), (5, 5, 0)),
    ((6, 0, 0), (6, 6, 6)),
    ((0, 0, 7), (7, 7, 7)),
)

COLS = 10
ROWS = 18
WIDTH = canvas.width
HEIGHT = canvas.height
CELL = min((WIDTH - 24) // COLS, (HEIGHT - 170) // ROWS)
FIELD_WIDTH = COLS * CELL
FIELD_HEIGHT = ROWS * CELL
FIELD_X = (WIDTH - FIELD_WIDTH) // 2
FIELD_Y = 58
CONTROLS_Y = FIELD_Y + FIELD_HEIGHT + 12
HIGH_SCORE_FILE = "testris_high_score.json"


def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, "r") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return 0


def save_high_score(value):
    with open(HIGH_SCORE_FILE, "w") as stream:
        json.dump(value, stream)


def rotate(piece):
    return tuple(tuple(row) for row in zip(*piece[::-1]))


def collision(grid, piece, piece_x, piece_y):
    for y, row in enumerate(piece):
        for x, value in enumerate(row):
            if not value:
                continue
            grid_x = piece_x + x
            grid_y = piece_y + y
            if grid_x < 0 or grid_x >= COLS or grid_y >= ROWS:
                return True
            if grid_y >= 0 and grid[grid_y][grid_x]:
                return True
    return False


def draw_cell(x, y, value):
    left = FIELD_X + x * CELL
    top = FIELD_Y + y * CELL
    canvas.fill_rect(left + 1, top + 1, CELL - 2, CELL - 2, COLORS[value])


def draw(grid, piece, piece_x, piece_y, score, high_score, message=""):
    canvas.fill(BLACK)
    canvas.text("TESTRIS", 8, 8, WHITE)
    canvas.text("Score %s" % score, 8, 28, WHITE)
    canvas.text("High %s" % high_score, WIDTH // 2, 28, GREY)
    if message:
        canvas.text(message, 8, HEIGHT - 18, WHITE)
    canvas.rect(
        FIELD_X - 2, FIELD_Y - 2,
        FIELD_WIDTH + 4, FIELD_HEIGHT + 4, GREY)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                draw_cell(x, y, value)
    for y, row in enumerate(piece):
        for x, value in enumerate(row):
            if value and piece_y + y >= 0:
                draw_cell(piece_x + x, piece_y + y, value)
    canvas.text("TOP: ROTATE", 8, CONTROLS_Y, GREY)
    canvas.text("SIDES: MOVE", 8, CONTROLS_Y + 16, GREY)
    canvas.text("BOTTOM: DROP", 8, CONTROLS_Y + 32, GREY)
    canvas.show()


def wait_for_touch(message):
    canvas.fill(BLACK)
    x = max(4, (WIDTH - len(message) * 8) // 2)
    canvas.text(message, x, HEIGHT // 2 - 6, WHITE)
    canvas.show()
    while touch.read() is None:
        sleep_ms(20)


high_score = load_high_score()
wait_for_touch("Touch to start Testris")

while True:
    grid = [[0 for unused_x in range(COLS)] for unused_y in range(ROWS)]
    score = 0
    drop_delay = 650
    game_over = False

    while not game_over:
        piece = choice(SHAPES)
        piece_x = COLS // 2 - len(piece[0]) // 2
        piece_y = -len(piece)
        if collision(grid, piece, piece_x, piece_y):
            break
        last_drop = ticks_ms()
        landed = False

        while not landed:
            key = touch.read()
            if key == "left" and not collision(
                    grid, piece, piece_x - 1, piece_y):
                piece_x -= 1
            elif key == "right" and not collision(
                    grid, piece, piece_x + 1, piece_y):
                piece_x += 1
            elif key == "rotate":
                rotated = rotate(piece)
                if not collision(grid, rotated, piece_x, piece_y):
                    piece = rotated
            elif key == "down" and not collision(
                    grid, piece, piece_x, piece_y + 1):
                piece_y += 1
            elif key == "drop":
                while not collision(grid, piece, piece_x, piece_y + 1):
                    piece_y += 1
                last_drop = 0
            elif key == "pause":
                draw(grid, piece, piece_x, piece_y, score, high_score, "Paused")
                while touch.read() is None:
                    sleep_ms(20)
                last_drop = ticks_ms()

            if ticks_diff(ticks_ms(), last_drop) >= drop_delay:
                if collision(grid, piece, piece_x, piece_y + 1):
                    landed = True
                else:
                    piece_y += 1
                    last_drop = ticks_ms()

            draw(grid, piece, piece_x, piece_y, score, high_score)
            sleep_ms(15)

        for y, row in enumerate(piece):
            for x, value in enumerate(row):
                if value:
                    target_y = piece_y + y
                    if target_y < 0:
                        game_over = True
                    else:
                        grid[target_y][piece_x + x] = value
        if game_over:
            break

        old_rows = len(grid)
        grid = [row for row in grid if not all(row)]
        cleared = old_rows - len(grid)
        if cleared:
            grid = [[0] * COLS for unused in range(cleared)] + grid
            score += (100, 250, 500, 900)[cleared - 1]
            drop_delay = max(180, drop_delay - cleared * 25)

    if score > high_score:
        high_score = score
        save_high_score(high_score)
    draw(grid, ((0,),), 0, 0, score, high_score, "Game over")
    wait_for_touch("Game over - touch to replay")
