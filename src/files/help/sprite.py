"""Animate one sprite sheet using TartLab's modern direct canvas."""

from random import choice
from time import sleep_ms

from tartlabutils.app import DirectCanvas, TouchGrid, game_surface, rgb565
from tartlabutils.sprites import SpriteSheet
from tartlabutils.platform import get_platform


surface = game_surface()
canvas = DirectCanvas(surface)
platform = get_platform()
stop_button = TouchGrid(["stop"], 1, 1) if platform.capabilities.get("touch", False) else None


def stop_requested():
    if stop_button is not None:
        return stop_button.read() == "stop"
    if platform.capabilities.get("buttons", False):
        return any(not pressed for name, pressed in platform.read_button_events())
    return False

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


# One decoder pass also works for QOI sheets. The animation does no decoding.
frames = sheet.sprites([
    (frame_x, frame_y, sprite_width, sprite_height)
    for frame_y in directions.values()
    for frame_x in (0, sprite_width, sprite_width * 2)
])
sprites = {name: tuple(frames[index * 3:index * 3 + 3])
           for index, name in enumerate(directions)}
del frames, sheet
clip = (0, 0, canvas.width, canvas.height)


canvas.fill(background)
x = 0
y = 0
step = 7
direction = choice(tuple(directions))

for unused in range(300):
    if stop_requested():
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
