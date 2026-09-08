"""Animate one sprite sheet using TartLab's modern direct canvas."""

from random import choice
from time import sleep_ms

from tartlabutils.app import DirectCanvas, TouchGrid, game_surface, rgb565
from tartlabutils.sprites import SpriteSheet


surface = game_surface()
canvas = DirectCanvas(surface)
stop_button = TouchGrid(["stop"], 1, 1)

sheet = SpriteSheet("files/assets/warrior.ts16")
sprite_width = sheet.width // 3
sprite_height = sheet.height // 4
background = rgb565(30, 40, 50)

directions = {
    "down": sheet.height // 2,
    "left": sheet.height * 3 // 4,
    "right": sheet.height // 4,
    "up": 0,
}


# Prepare the twelve frames once; the animation performs no image decoding.
sprites = {name: tuple(sheet.sprite(frame_x, frame_y, sprite_width, sprite_height)
                       for frame_x in (0, sprite_width, sprite_width * 2))
           for name, frame_y in directions.items()}
del sheet
clip = (0, 0, canvas.width, canvas.height)


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

    for frame in (0, 1, 2, 1):
        canvas.fill_rect(x, y, sprite_width, sprite_height, background)
        x, y = next_x, next_y
        sprites[direction][frame].draw(canvas, x, y, clip)
        canvas.show()
        sleep_ms(50)
