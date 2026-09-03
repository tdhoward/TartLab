"""Testris by Brad Barnett, adapted for the modern direct renderer."""

from random import choice
from time import sleep_ms, ticks_diff, ticks_ms
import ujson as json
from framebuf import FrameBuffer, RGB565

from tartlabutils.modern_app import (
    PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)


surface = game_surface()
canvas = PortraitCanvas(surface)

# Match the legacy touch keypad. The screen is divided into a 3x3 grid:
# START / unused / PAUSE, CW / DROP / CCW, LEFT / DOWN / RIGHT.
touch = PortraitTouchGrid((
    "start", None, "pause",
    "cw", "drop", "ccw",
    "left", "down", "right",
), 3, 3)

BLACK = rgb565(0, 0, 0)
WHITE = rgb565(255, 255, 255)
RED = rgb565(255, 0, 0)
GREEN = rgb565(0, 255, 0)
BLUE = rgb565(0, 0, 255)
CYAN = rgb565(0, 255, 255)
MAGENTA = rgb565(128, 0, 128)
YELLOW = rgb565(255, 255, 0)
ORANGE = rgb565(255, 164, 0)
GREY = rgb565(132, 130, 132)

# Black, the seven pieces, the border, and the touch targets.
COLORS = (
    BLACK, CYAN, YELLOW, MAGENTA, GREEN,
    BLUE, RED, ORANGE, GREY, WHITE,
)

PIECES = (
    ((1, 1, 1, 1),),
    ((2, 2), (2, 2)),
    ((0, 3, 0), (3, 3, 3)),
    ((4, 4, 0), (0, 4, 4)),
    ((0, 5, 5), (5, 5, 0)),
    ((6, 0, 0), (6, 6, 6)),
    ((0, 0, 7), (7, 7, 7)),
)

SPLASH = (
    (0, 0, 0, 3, 3, 0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 3, 4, 4, 4, 0, 0, 6, 0, 0),
    (1, 1, 1, 3, 3, 4, 5, 5, 0, 6, 0, 0),
    (0, 1, 2, 2, 3, 4, 5, 0, 5, 6, 7, 7),
    (0, 1, 2, 3, 3, 4, 5, 5, 0, 6, 7, 0),
    (0, 1, 2, 2, 0, 4, 5, 0, 5, 6, 7, 7),
    (0, 1, 2, 0, 0, 0, 5, 0, 5, 0, 0, 7),
    (0, 0, 2, 2, 0, 0, 0, 0, 0, 0, 7, 7),
)

GRID_WIDTH = 10
GRID_HEIGHT = 20
BORDER_INDEX = 8
TOUCH_TARGET_INDEX = 9
DELAY = 150
SPEEDUP = 25
BAG_SIZE = 7
HIGH_SCORE_FILE = "testris_high_score.json"

DISPLAY_WIDTH = canvas.width
DISPLAY_HEIGHT = canvas.height
BLOCK_SIZE = min(
    DISPLAY_WIDTH // (GRID_WIDTH + 2),
    DISPLAY_HEIGHT // (GRID_HEIGHT + 4))
BLOCK_BEVEL = max(1, BLOCK_SIZE // 5)
BORDER_WIDTH = (GRID_WIDTH + 2) * BLOCK_SIZE
BORDER_HEIGHT = (GRID_HEIGHT + 2) * BLOCK_SIZE
BORDER_X = (DISPLAY_WIDTH - BORDER_WIDTH) // 2
BORDER_Y = DISPLAY_HEIGHT - BORDER_HEIGHT
GRID_X = BORDER_X + BLOCK_SIZE
GRID_Y = BORDER_Y + BLOCK_SIZE
BANNER_WIDTH = BORDER_WIDTH - 4 * BLOCK_SIZE
BANNER_HEIGHT = 2 * BLOCK_SIZE
PREVIEW_X = GRID_X + 7 * BLOCK_SIZE
PREVIEW_Y = GRID_Y - 3 * BLOCK_SIZE
PREVIEW_WIDTH = 4 * BLOCK_SIZE
PREVIEW_HEIGHT = 2 * BLOCK_SIZE

def create_blocks():
    """Pre-render each block once in the canvas's native orientation."""
    blocks = []
    last_pixel = BLOCK_SIZE - 1
    dark_start = BLOCK_SIZE - BLOCK_BEVEL - 1
    for index, color in enumerate(COLORS):
        buffer = bytearray(BLOCK_SIZE * BLOCK_SIZE * 2)
        block = FrameBuffer(buffer, BLOCK_SIZE, BLOCK_SIZE, RGB565)
        block.fill(BLACK)
        if index and BLOCK_SIZE > 2:
            block.fill_rect(
                1, 1, BLOCK_SIZE - 2, BLOCK_SIZE - 2, color)
            for block_y in range(1, last_pixel):
                for block_x in range(1, last_pixel):
                    if ((block_x < BLOCK_BEVEL or
                         block_y < BLOCK_BEVEL) and
                            (block_x & 1) == (block_y & 1)):
                        block.pixel(block_x, block_y, WHITE)
                    elif ((block_x > dark_start or
                           block_y > dark_start) and
                          (block_x & 1) == (block_y & 1)):
                        block.pixel(block_x, block_y, BLACK)
        blocks.append(canvas.prepare_sprite(
            block, BLOCK_SIZE, BLOCK_SIZE))
    return blocks


BLOCKS = create_blocks()


def load_high_score():
    try:
        with open(HIGH_SCORE_FILE, "r") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return 0


def save_high_score(value):
    with open(HIGH_SCORE_FILE, "w") as stream:
        json.dump(value, stream)


def draw_block(x, y, index):
    """Copy one of the pre-rendered, dither-beveled blocks."""
    canvas.draw_sprite(BLOCKS[index], x, y)


def draw_piece(piece, position, index=-1, offset_x=GRID_X, offset_y=GRID_Y):
    for piece_y, row in enumerate(piece):
        for piece_x, block in enumerate(row):
            if block:
                draw_block(
                    offset_x + (position[0] + piece_x) * BLOCK_SIZE,
                    offset_y + (position[1] + piece_y) * BLOCK_SIZE,
                    index if index >= 0 else block)


def draw_banner(text, x=BORDER_X, y=0):
    canvas.fill_rect(x, y, BANNER_WIDTH, BANNER_HEIGHT, BLACK)
    text_y = y + 4
    for line in text.split("\n"):
        canvas.text(line, x, text_y, WHITE)
        text_y += 8


def score_text(score, lines, drop_time, message=""):
    return (
        f"{message}\nScore: {score:,}\nLines cleared: {lines:,}"
        f"\nDrop time: {drop_time} ms")


def draw_border():
    right = BORDER_X + BORDER_WIDTH - BLOCK_SIZE
    bottom = BORDER_Y + BORDER_HEIGHT - BLOCK_SIZE
    for x in range(BORDER_X, BORDER_X + BORDER_WIDTH, BLOCK_SIZE):
        draw_block(x, BORDER_Y, BORDER_INDEX)
        draw_block(x, bottom, BORDER_INDEX)
    for y in range(BORDER_Y, BORDER_Y + BORDER_HEIGHT, BLOCK_SIZE):
        draw_block(BORDER_X, y, BORDER_INDEX)
        draw_block(right, y, BORDER_INDEX)


def draw_touch_targets():
    draw_piece(
        ((TOUCH_TARGET_INDEX,) * 4,),
        (GRID_WIDTH // 2 - 2, GRID_HEIGHT))
    for x in (-1, GRID_WIDTH):
        for y in (-1, GRID_HEIGHT // 2 - 3, GRID_HEIGHT - 5):
            draw_piece(((TOUCH_TARGET_INDEX,),) * 4, (x, y))


def draw_grid(grid):
    canvas.fill_rect(
        GRID_X, GRID_Y,
        GRID_WIDTH * BLOCK_SIZE, GRID_HEIGHT * BLOCK_SIZE,
        BLACK)
    for y, row in enumerate(grid):
        for x, block in enumerate(row):
            if block:
                draw_block(GRID_X + x * BLOCK_SIZE,
                           GRID_Y + y * BLOCK_SIZE, block)


def draw_scene(grid, current_piece, current_position, next_piece,
               banner):
    canvas.fill(BLACK)
    draw_border()
    draw_touch_targets()
    draw_grid(grid)
    if current_piece is not None:
        draw_piece(current_piece, current_position)
    if next_piece is not None:
        draw_piece(next_piece, (7, -3))
    draw_banner(banner)
    canvas.show()


def update_banner(text):
    draw_banner(text)
    canvas.show((BORDER_X, 0, BANNER_WIDTH, BANNER_HEIGHT))


def update_preview(piece):
    canvas.fill_rect(
        PREVIEW_X, PREVIEW_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT, BLACK)
    if piece is not None:
        draw_piece(piece, (7, -3))
    canvas.show((PREVIEW_X, PREVIEW_Y, PREVIEW_WIDTH, PREVIEW_HEIGHT))


def piece_area(piece, position):
    left = len(piece[0])
    top = len(piece)
    right = 0
    bottom = 0
    for y, row in enumerate(piece):
        for x, block in enumerate(row):
            if block:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x + 1)
                bottom = max(bottom, y + 1)
    return (
        GRID_X + (position[0] + left) * BLOCK_SIZE,
        GRID_Y + (position[1] + top) * BLOCK_SIZE,
        (right - left) * BLOCK_SIZE,
        (bottom - top) * BLOCK_SIZE)


def combined_area(first, second):
    left = min(first[0], second[0])
    top = min(first[1], second[1])
    right = max(first[0] + first[2], second[0] + second[2])
    bottom = max(first[1] + first[3], second[1] + second[3])
    return left, top, right - left, bottom - top


def show_new_piece(piece, position):
    draw_piece(piece, position)
    canvas.show(piece_area(piece, position))


def update_active_piece(old_piece, old_position, piece, position):
    old_area = piece_area(old_piece, old_position)
    new_area = piece_area(piece, position)
    dirty_area = combined_area(old_area, new_area)
    draw_piece(old_piece, old_position, index=0)
    draw_piece(piece, position)
    separate_size = (
        old_area[2] * old_area[3] + new_area[2] * new_area[3])
    if dirty_area[2] * dirty_area[3] <= separate_size:
        canvas.show(dirty_area)
    else:
        # A hard drop can leave a large gap. Refresh its two ends instead of
        # transferring the untouched space between them.
        canvas.show(old_area)
        canvas.show(new_area)


def update_grid_rows(grid, rows):
    for y in rows:
        canvas.fill_rect(
            GRID_X, GRID_Y + y * BLOCK_SIZE,
            GRID_WIDTH * BLOCK_SIZE, BLOCK_SIZE, BLACK)
        for x, block in enumerate(grid[y]):
            if block:
                draw_block(
                    GRID_X + x * BLOCK_SIZE,
                    GRID_Y + y * BLOCK_SIZE, block)

    # Coalesce adjacent changed rows without transferring unchanged gaps.
    first = None
    previous = None
    for y in rows:
        if first is None:
            first = y
        elif y != previous + 1:
            canvas.show((
                GRID_X, GRID_Y + first * BLOCK_SIZE,
                GRID_WIDTH * BLOCK_SIZE,
                (previous - first + 1) * BLOCK_SIZE))
            first = y
        previous = y
    if first is not None:
        canvas.show((
            GRID_X, GRID_Y + first * BLOCK_SIZE,
            GRID_WIDTH * BLOCK_SIZE,
            (previous - first + 1) * BLOCK_SIZE))


def show_splash(high_score):
    canvas.fill(BLACK)
    splash_x = (DISPLAY_WIDTH - len(SPLASH[0]) * BLOCK_SIZE) // 2
    splash_y = (DISPLAY_HEIGHT - len(SPLASH) * BLOCK_SIZE) // 2
    draw_piece(SPLASH, (0, 0), offset_x=splash_x, offset_y=splash_y)
    draw_banner(
        f"High Score {high_score:,}\n\nPress any key\nto continue.",
        x=(DISPLAY_WIDTH - 5 * BLOCK_SIZE) // 2,
        y=DISPLAY_HEIGHT - 2 * BLOCK_SIZE)
    canvas.show()


def wait_for_key(required=None, excluded=()):
    while True:
        key = touch.read()
        if key is not None and key not in excluded:
            if required is None or key == required:
                return key
        sleep_ms(10)


def shuffled_bag():
    choices = list(PIECES)
    bag = []
    for unused in range(BAG_SIZE):
        piece = choice(choices)
        bag.append(piece)
        choices.remove(piece)
    return bag


def rotate(piece, direction):
    transposed = list(zip(*piece))
    if direction > 0:
        return tuple(tuple(reversed(row)) for row in transposed)
    return tuple(tuple(row) for row in reversed(transposed))


def collision(grid, piece, position, dx=0, dy=0, rotation=0):
    candidate = rotate(piece, rotation) if rotation else piece
    for y, row in enumerate(candidate):
        for x, block in enumerate(row):
            if not block:
                continue
            grid_x = position[0] + x + dx
            grid_y = position[1] + y + dy
            if (grid_x < 0 or grid_x >= GRID_WIDTH or
                    grid_y < 0 or grid_y >= GRID_HEIGHT or
                    grid[grid_y][grid_x]):
                return True
    return False


def lock_piece(grid, piece, position):
    for y, row in enumerate(piece):
        for x, block in enumerate(row):
            if block:
                grid[position[1] + y][position[0] + x] = block


def clear_lines(grid):
    full_lines = [y for y, row in enumerate(grid) if all(row)]
    for full_line in full_lines:
        for y in range(full_line, 0, -1):
            grid[y] = list(grid[y - 1])
        grid[0] = [0 for unused in range(GRID_WIDTH)]
    return len(full_lines)


high_score = load_high_score()
show_splash(high_score)
wait_for_key()

while True:
    grid = [[0 for unused_x in range(GRID_WIDTH)]
            for unused_y in range(GRID_HEIGHT)]
    bag = []
    next_piece = choice(PIECES)
    score = 0
    lines = 0
    drop_time = 1000
    restart_requested = False

    draw_scene(
        grid, None, (0, 0), None,
        f"High Score {high_score:,}\n\nPress START\nto play.")
    wait_for_key("start")
    banner = score_text(score, lines, drop_time)
    update_banner(banner)

    while not restart_requested:
        current_piece = next_piece
        current_position = [
            GRID_WIDTH // 2 - len(current_piece[0]) // 2, 0]
        if collision(grid, current_piece, current_position):
            break

        if not bag:
            bag = shuffled_bag()
        next_piece = bag.pop()
        last_drop = ticks_ms()
        last_read = 0
        piece_landed = False
        show_new_piece(current_piece, current_position)
        update_preview(next_piece)

        while not piece_landed and not restart_requested:
            changed = False
            old_piece = current_piece
            old_position = list(current_position)
            key = touch.read()
            now = ticks_ms()
            if key is not None and ticks_diff(now, last_read) >= DELAY:
                last_read = now
                if key == "left" and not collision(
                        grid, current_piece, current_position, dx=-1):
                    current_position[0] -= 1
                    changed = True
                elif key == "right" and not collision(
                        grid, current_piece, current_position, dx=1):
                    current_position[0] += 1
                    changed = True
                elif key == "down" and not collision(
                        grid, current_piece, current_position, dy=1):
                    current_position[1] += 1
                    last_drop = now
                    changed = True
                elif key == "drop":
                    while not collision(
                            grid, current_piece, current_position, dy=1):
                        current_position[1] += 1
                    piece_landed = True
                    changed = True
                elif key == "ccw" and not collision(
                        grid, current_piece, current_position, rotation=-1):
                    current_piece = rotate(current_piece, -1)
                    changed = True
                elif key == "cw" and not collision(
                        grid, current_piece, current_position, rotation=1):
                    current_piece = rotate(current_piece, 1)
                    changed = True
                elif key == "pause":
                    update_banner(
                        "Paused.\n\nPress START to reset.\nAny key to resume.")
                    if wait_for_key(excluded=("pause",)) == "start":
                        restart_requested = True
                    else:
                        last_drop = ticks_ms()
                        update_banner(banner)

            if (not piece_landed and
                    ticks_diff(ticks_ms(), last_drop) >= drop_time):
                if collision(
                        grid, current_piece, current_position, dy=1):
                    piece_landed = True
                else:
                    current_position[1] += 1
                    last_drop = ticks_ms()
                    changed = True

            if changed and not restart_requested:
                update_active_piece(
                    old_piece, old_position,
                    current_piece, current_position)
            if not piece_landed and not restart_requested:
                sleep_ms(10)

        if restart_requested:
            continue

        lock_piece(grid, current_piece, current_position)
        if any(all(row) for row in grid):
            old_grid = [row[:] for row in grid]
            cleared = clear_lines(grid)
        else:
            cleared = 0
        if cleared:
            score += (100, 200, 400, 800)[cleared - 1]
            lines += cleared
            drop_time = max(DELAY, drop_time - SPEEDUP)
            banner = score_text(score, lines, drop_time)
            changed_rows = [
                y for y in range(GRID_HEIGHT)
                if grid[y] != old_grid[y]]
            update_grid_rows(grid, changed_rows)
            update_banner(banner)

    if restart_requested:
        continue

    if score > high_score:
        high_score = score
        save_high_score(high_score)
        message = "New high score!"
    else:
        message = "Game over!"
    update_preview(None)
    update_banner(score_text(score, lines, drop_time, message))
    wait_for_key("start")
