"""Animate one sprite sheet using TartLab's modern direct canvas."""

from framebuf import FrameBuffer, RGB565
from random import choice
from time import sleep_ms

from bmp565 import BMP565
from tartlabutils.modern_app import (
    DirectCanvas, TouchGrid, framebuffer_color, game_surface,
    swap565_buffer)


surface = game_surface()
canvas = DirectCanvas(surface)
stop_button = TouchGrid(["stop"], 1, 1)

sheet = BMP565("files/assets/warrior.bmp", streamed=True)
sprite_width = sheet.width // 3
sprite_height = sheet.height // 4
background = framebuffer_color(sheet[0])

directions = {
    "down": sheet.height // 2,
    "left": sheet.height * 3 // 4,
    "right": sheet.height // 4,
    "up": 0,
}
frames = (0, sprite_width, sprite_width * 2, sprite_width)


def draw_sprite(x, y, frame_x, frame_y):
    pixels = sheet[
        frame_x:frame_x + sprite_width,
        frame_y:frame_y + sprite_height]
    swap565_buffer(pixels)
    sprite = FrameBuffer(pixels, sprite_width, sprite_height, RGB565)
    canvas.blit(sprite, x, y)


canvas.fill(background)
x = 0
y = 0
step = 7
direction = choice(tuple(directions))

for unused in range(300):
    if stop_button.read() == "stop":
        break
    if direction == "down":
        next_x, next_y = x, y + step
    elif direction == "up":
        next_x, next_y = x, y - step
    elif direction == "left":
        next_x, next_y = x - step, y
    else:
        next_x, next_y = x + step, y

    if not (0 <= next_x <= surface.width - sprite_width and
            0 <= next_y <= surface.height - sprite_height):
        direction = choice(tuple(directions))
        continue

    for frame_x in frames:
        canvas.fill_rect(x, y, sprite_width, sprite_height, background)
        x, y = next_x, next_y
        draw_sprite(x, y, frame_x, directions[direction])
        canvas.show()
        sleep_ms(50)
