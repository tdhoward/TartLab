"""A touch-controlled snake game for the modern direct renderer."""

from random import randint
from time import sleep_ms, ticks_diff, ticks_ms
import ujson as json

from tartlabutils.modern_app import (
    PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)


surface = game_surface()
canvas = PortraitCanvas(surface)
touch = PortraitTouchGrid((
    None, "up", None,
    "left", "pause", "right",
    "quit", "down", "restart",
), 3, 3)

BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
GREEN = rgb565(0, 180, 70)
HEAD = rgb565(120, 255, 120)
RED = rgb565(244, 67, 54)
GREY = rgb565(110, 120, 130)

WIDTH = canvas.width
HEIGHT = canvas.height
COLS = 14
ROWS = 28
HEADER = 34
CELL = min((WIDTH - 4) // COLS, (HEIGHT - HEADER - 4) // ROWS)
FIELD_WIDTH = COLS * CELL
FIELD_HEIGHT = ROWS * CELL
FIELD_X = (WIDTH - FIELD_WIDTH) // 2
FIELD_Y = HEADER + (HEIGHT - HEADER - FIELD_HEIGHT) // 2
HIGH_SCORE_FILE = "snake_high_score.json"


def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, "r") as stream:
            return json.load(stream).get("high_score", 0)
    except (OSError, ValueError):
        return 0


def save_high_score(value):
    with open(HIGH_SCORE_FILE, "w") as stream:
        json.dump({"high_score": value}, stream)


def random_apple(snake):
    while True:
        apple = randint(0, COLS - 1), randint(0, ROWS - 1)
        if apple not in snake:
            return apple


def cell(position, color, inset=1):
    x, y = position
    canvas.fill_rect(
        FIELD_X + x * CELL + inset,
        FIELD_Y + y * CELL + inset,
        CELL - inset * 2,
        CELL - inset * 2,
        color)


def draw(snake, apple, score, message=""):
    canvas.fill(BLACK)
    canvas.text("SNAKE  Score %s" % score, 8, 8, WHITE)
    if message:
        canvas.text(message, max(0, WIDTH - len(message) * 8 - 8), 20, WHITE)
    canvas.rect(
        FIELD_X - 1, FIELD_Y - 1,
        FIELD_WIDTH + 2, FIELD_HEIGHT + 2, GREY)
    cell(apple, RED)
    for segment in snake[:-1]:
        cell(segment, GREEN)
    cell(snake[-1], HEAD)
    canvas.show()


def wait_for_touch(message):
    canvas.fill(BLACK)
    x = max(4, (WIDTH - len(message) * 8) // 2)
    canvas.text(message, x, HEIGHT // 2 - 12, WHITE)
    canvas.text("Use the 3x3 touch grid", 20, HEIGHT // 2 + 8, GREY)
    canvas.show()
    while touch.read() is None:
        sleep_ms(20)


high_score = load_high_score()
wait_for_touch("Touch to start Snake")

running = True
while running:
    snake = [(COLS // 2 - 2, ROWS // 2),
             (COLS // 2 - 1, ROWS // 2),
             (COLS // 2, ROWS // 2)]
    apple = random_apple(snake)
    direction = (1, 0)
    score = 0
    move_delay = 190
    last_move = ticks_ms()
    alive = True

    while alive:
        key = touch.read()
        if key == "up" and direction != (0, 1):
            direction = (0, -1)
        elif key == "down" and direction != (0, -1):
            direction = (0, 1)
        elif key == "left" and direction != (1, 0):
            direction = (-1, 0)
        elif key == "right" and direction != (-1, 0):
            direction = (1, 0)
        elif key == "quit":
            running = False
            break
        elif key == "pause":
            draw(snake, apple, score, "Paused")
            while touch.read() is None:
                sleep_ms(20)
            last_move = ticks_ms()

        if ticks_diff(ticks_ms(), last_move) < move_delay:
            sleep_ms(10)
            continue
        last_move = ticks_ms()
        head_x, head_y = snake[-1]
        next_head = (
            (head_x + direction[0]) % COLS,
            (head_y + direction[1]) % ROWS)
        if next_head in snake:
            alive = False
            break
        snake.append(next_head)
        if next_head == apple:
            score += 1
            move_delay = max(75, move_delay - 5)
            apple = random_apple(snake)
        else:
            snake.pop(0)
        draw(snake, apple, score)

    if not running:
        break
    if score > high_score:
        high_score = score
        save_high_score(high_score)
    draw(snake, apple, score, "High %s" % high_score)
    wait_for_touch("Game over - touch to replay")

canvas.fill(BLACK)
canvas.show()
