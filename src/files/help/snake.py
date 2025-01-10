from hdwconfig import display_drv, broker  # type: ignore
from eventsys.touch_keypad import Keypad   # type: ignore
from eventsys.keys import Keys            # type: ignore
from random import randint
from pygfx.framebuf_plus import FrameBuffer, RGB565   # type: ignore
from micropython import const
from pygfx.displaybuf import DisplayBuffer as SSD
import pygfx                         # Bring in the drawing functions
from time import ticks_ms, ticks_diff, sleep
import ujson as json   # for loading and saving the highscore file

# Display dimensions
display_drv.rotation = 0
WIDTH = display_drv.width
HEIGHT = display_drv.height
if WIDTH > HEIGHT:
    display_drv.rotation += 90

# Disable auto byte swap if supported
if display_drv.requires_byte_swap:
    needs_swap = display_drv.disable_auto_byte_swap(True)
else:
    needs_swap = False

# Define some colors
class pal:
	BLACK   = 0x0000
	WHITE   = 0xFFFF
	GREEN   = 0x07E0 if not needs_swap else 0xE007
	DKGREEN = 0x0600 if not needs_swap else 0x0006
	RED     = 0xF800 if not needs_swap else 0x00F8
	ORANGE  = 0xFD20 if not needs_swap else 0x20FD
	GREY    = 0x8410 if not needs_swap else 0x1084

# Set up block size
GRID_HEIGHT = const(25)
GRID_WIDTH  = const(14)
block_size  = min(WIDTH // GRID_WIDTH, HEIGHT // GRID_HEIGHT)
half_block = block_size // 2
BASE_UNIT = block_size // 15


# Offset to center or position the grid
grid_x_offset = (WIDTH - (GRID_WIDTH * block_size)) // 2
grid_y_offset = (HEIGHT - (GRID_HEIGHT * block_size)) // 2

# Key mapping
BT_ROWS = 5
BT_COLS = 2
BT_WIDTH = WIDTH // BT_COLS
BT_HEIGHT = HEIGHT // BT_ROWS
BT_WIDTH_HALF = BT_WIDTH // 2
BT_HEIGHT_HALF = BT_HEIGHT // 2
START = Keys.K_RETURN
PAUSE = Keys.K_ESCAPE
LEFT  = Keys.K_LEFT
RIGHT = Keys.K_RIGHT
UP    = Keys.K_UP
DOWN  = Keys.K_DOWN
keypad = Keypad(broker.poll, 0, 0, WIDTH, HEIGHT, rows=BT_ROWS, cols=BT_COLS,
                keys=[START, PAUSE, 
					  UP, UP, 
					  LEFT, RIGHT,
					  LEFT, RIGHT,
					  DOWN, DOWN])

# Create a buffer for the text area
text_buf_width = WIDTH
text_buf_height = grid_y_offset - 1
text_buf    = bytearray(text_buf_width * text_buf_height * 2)
text_fb     = FrameBuffer(text_buf, text_buf_width, text_buf_height, RGB565)


# Create buffers for apple, snake head, snake body, and black cell
apple_buf = FrameBuffer(bytearray(block_size * block_size * 2), block_size, block_size, RGB565)
snake_head_buf = FrameBuffer(bytearray(block_size * block_size * 2), block_size, block_size, RGB565)
snake_body_buf = FrameBuffer(bytearray(block_size * block_size * 2), block_size, block_size, RGB565)
black_cell_buf = FrameBuffer(bytearray(block_size * block_size * 2), block_size, block_size, RGB565)

# Draw pre-rendered images
# - Apple
apple_buf.fill(pal.BLACK)
pygfx.circle(apple_buf, half_block, half_block, half_block, pal.RED, True)  # the apple
pygfx.arc(apple_buf, half_block, half_block, half_block, 215, 240, pal.WHITE)  # shiny spot
pygfx.fill_rect(apple_buf, half_block + BASE_UNIT, 0, BASE_UNIT * 2, BASE_UNIT * 4, pal.DKGREEN)  # stem
pygfx.fill_rect(apple_buf, half_block, BASE_UNIT * 3, BASE_UNIT * 2, BASE_UNIT * 2, pal.BLACK)

# - Snake
snake_head_buf.fill(pal.GREEN)
pygfx.fill_rect(snake_head_buf, (half_block // 2), (half_block // 2), 4, 4, pal.BLACK)
snake_body_buf.fill(pal.DKGREEN)
black_cell_buf.fill(pal.BLACK)

# Canvas setup
canvas = SSD(display_drv, SSD.RGB565)


# draw the outer border
def draw_outer_border():
    outer_x = grid_x_offset - 1
    outer_y = grid_y_offset - 1
    outer_width = GRID_WIDTH * block_size + 2
    outer_height = GRID_HEIGHT * block_size + 2
    canvas.rect(outer_x, outer_y, outer_width, outer_height, pal.GREY)


# Helper to draw pre-rendered images
def draw_image(buffer, x, y):
    canvas.blit(buffer, grid_x_offset + x * block_size, grid_y_offset + y * block_size)


# Save and load high score
def load_high_score():
    try:
        with open("snake_high_score.json", "r") as f:
            return json.load(f).get("high_score", 0)
    except (OSError, ValueError):
        return 0


def save_high_score(high_score):
    with open("snake_high_score.json", "w") as f:
        json.dump({"high_score": high_score}, f)


TEXT_ROW_SIZE = 12
def show_text(msg, color=pal.WHITE, bg=pal.BLACK):
    text_fb.fill(bg)
    lines = msg.split("\n")
    total_height = len(lines) * TEXT_ROW_SIZE
    start_y = (text_buf_height - total_height) // 2
    for i, line in enumerate(lines):
        text_fb.text(line, 20, start_y + (i * TEXT_ROW_SIZE), color)  # Center vertically
    canvas.blit(text_fb, 0, 0)
    canvas.show()


# Simple little helper function for drawing centered text on the canvas
def canvas_text(msg, x, y, color=pal.WHITE, center = True):
    if center:
        y -= 4
        x -= len(msg) * 4
    pygfx.text(canvas, msg, x, y, color, scale=1, inverted=False, font_file=None, height=8)


# Place an apple randomly
def place_apple():
    global snake
    while True:
        apple = (randint(0, GRID_WIDTH - 1), randint(0, GRID_HEIGHT - 1))
        if apple not in snake:
            return apple

# Main game
def main():
    global text_fb, snake

    # Load high score
    high_score = load_high_score()

    # Show touch-screen control locations
    canvas.fill(pal.BLACK)
    pygfx.rect(canvas, 0, 0, BT_WIDTH, BT_HEIGHT, pal.GREY)  # Start
    canvas_text("Start", BT_WIDTH_HALF, BT_HEIGHT_HALF, pal.ORANGE)
    pygfx.rect(canvas, BT_WIDTH, 0, BT_WIDTH, BT_HEIGHT, pal.GREY)  # Pause
    canvas_text("Pause", BT_WIDTH + BT_WIDTH_HALF, BT_HEIGHT_HALF, pal.ORANGE)
    pygfx.rect(canvas, 0, BT_HEIGHT, WIDTH, BT_HEIGHT, pal.GREY)  # Up
    canvas_text("Up", BT_WIDTH, BT_HEIGHT + BT_HEIGHT_HALF, pal.ORANGE)
    pygfx.rect(canvas, 0, BT_HEIGHT * 2, WIDTH, BT_HEIGHT * 2, pal.GREY)  # Left
    canvas_text("Left", BT_WIDTH_HALF, BT_HEIGHT * 3, pal.ORANGE)
    pygfx.rect(canvas, BT_WIDTH, BT_HEIGHT * 2, WIDTH, BT_HEIGHT * 2, pal.GREY)  # Right
    canvas_text("Right", BT_WIDTH + BT_WIDTH_HALF, BT_HEIGHT * 3, pal.ORANGE)
    pygfx.rect(canvas, 0, BT_HEIGHT * 4, WIDTH, BT_HEIGHT, pal.GREY)  # Down
    canvas_text("Down", BT_WIDTH, BT_HEIGHT * 4 + BT_HEIGHT_HALF, pal.ORANGE)
    canvas.show()

    # Wait for START
    while True:
        if keypad.read() == START:
            break

    # Clear screen
    canvas.fill(pal.BLACK)
    draw_outer_border()
    canvas.show()

    # Initialize snake
    snake = [(GRID_WIDTH//2, GRID_HEIGHT//2)]
    direction = (1, 0)  # start moving right
    snake_length = 3
    score = 0
    apple_count = 0
    apple_bonus = 1

    apple = place_apple()
    draw_image(apple_buf, apple[0], apple[1])
    last_move = ticks_ms()
    move_delay = 250  # ms between snake moves

    show_text(f"Score {score}")

    # Game loop
    while True:
        # --- INPUT ---
        key = keypad.read()
        if key:
            # Change direction if valid  (Can't switch 180 degrees)
            if key == LEFT  and direction != (1, 0):  direction = (-1, 0)
            if key == RIGHT and direction != (-1,0):  direction = (1, 0)
            if key == UP    and direction != (0, 1):  direction = (0, -1)
            if key == DOWN  and direction != (0, -1): direction = (0, 1)

            if key == PAUSE:
                show_text("Paused.\nPress start 2x to quit,\nAny key to resume.")
                paused_key = None
                while paused_key is None:
                    paused_key = keypad.read()
                if paused_key == START:  # if they press Start once...
                    paused_key = None
                    while paused_key is None:   # check to see if they press it again
                        paused_key = keypad.read()
                    if paused_key == START:
                        return False    # quit if they pressed start twice
                show_text(f"Score {score}")

        # --- UPDATE SNAKE POSITION ---
        if ticks_diff(ticks_ms(), last_move) > move_delay:
            last_move = ticks_ms()

            # The head is in a new spot
            head_x, head_y = snake[-1]
            dx, dy = direction
            new_head = ((head_x + dx) % GRID_WIDTH, (head_y + dy) % GRID_HEIGHT)

            # Check collision with self
            if new_head in snake:
                # Game over
                break

            # Add the new head to the end of snake
            snake.append(new_head)

            # Erase the oldest part of the snake's tail
            if len(snake) > snake_length:
                tail = snake.pop(0)
                draw_image(black_cell_buf, tail[0], tail[1])

            # Draw new head
            draw_image(snake_head_buf, new_head[0], new_head[1])

            # Only draw the new tail segment (right behind the head)
            if len(snake) > 1:
                second_to_last = snake[-2]
                draw_image(snake_body_buf, second_to_last[0], second_to_last[1])

            # Check if we ate the apple
            if new_head == apple:
                snake_length += 1
                score += apple_bonus
                apple_count += 1

                # Increase apple bonus and adjust move delay every 5 apples
                if apple_count % 5 == 0:
                    apple_bonus += 2
                    move_delay = min(move_delay * 0.8, move_delay - 5)

                # place a new apple
                apple = place_apple()
                draw_image(apple_buf, apple[0], apple[1])
                show_text(f"Score {score}")

        # Update the canvas
        canvas.show()

    # Check for new high score
    if score > high_score:
        high_score = score
        save_high_score(high_score)
        show_text(f"New High Score!\nScore: {score}\nHigh Score: {high_score}", pal.GREEN)
    else:
        show_text(f"Game Over\nScore: {score}\nHigh Score: {high_score}")

    # Final wait for START to replay
    while keypad.read() != START:
        pass
    return True

while main() == True:
    pass

# Clear the screen when they quit
canvas.fill(pal.BLACK)
canvas.show()
