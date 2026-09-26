"""Classic Snake, using the modern portrait drawing and touch APIs."""

from random import randint

GRID_WIDTH = 14
GRID_HEIGHT = 25
TOUCH_KEYS = ("start", "pause", "up", "up", "left", "right",
              "left", "right", "down", "down")
HIGH_SCORE_FILE = "snake_high_score.json"


class SnakeGame:
    def __init__(self):
        self.snake = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = (1, 0)
        self.snake_length = 3
        self.score = 0
        self.apple_count = 0
        self.apple_bonus = 1
        self.move_delay = 250
        self.apples = []
        for unused in range(3):
            self.place_apple()

    def place_apple(self):
        # Count free cells so a full board cannot leave the game spinning.
        free = GRID_WIDTH * GRID_HEIGHT - len(self.snake) - len(self.apples)
        if free <= 0:
            return
        index = randint(0, free - 1)
        for y in range(GRID_HEIGHT):
            for x in range(GRID_WIDTH):
                point = (x, y)
                if point not in self.snake and point not in self.apples:
                    if index == 0:
                        self.apples.append(point)
                        return
                    index -= 1

    def turn(self, key):
        direction = {"left": (-1, 0), "right": (1, 0),
                     "up": (0, -1), "down": (0, 1)}.get(key)
        if direction and direction != (-self.direction[0], -self.direction[1]):
            self.direction = direction

    def step(self):
        x, y = self.snake[-1]
        dx, dy = self.direction
        head = ((x + dx) % GRID_WIDTH, (y + dy) % GRID_HEIGHT)
        if head in self.snake:
            return False
        self.snake.append(head)
        # Preserve the original delayed growth: trim before eating.
        if len(self.snake) > self.snake_length:
            self.snake.pop(0)
        if head in self.apples:
            self.apples.remove(head)
            self.snake_length += 1
            self.score += self.apple_bonus
            self.apple_count += 1
            if self.apple_count % 5 == 0:
                self.apple_bonus += 2
                self.move_delay = min(self.move_delay * 0.8, self.move_delay - 5)
            self.place_apple()
        return True


def load_high_score():
    import ujson as json
    try:
        with open(HIGH_SCORE_FILE, "r") as stream:
            return json.load(stream).get("high_score", 0)
    except (OSError, ValueError):
        return 0


def save_high_score(value):
    import ujson as json
    with open(HIGH_SCORE_FILE, "w") as stream:
        json.dump({"high_score": value}, stream)


class SnakeView:
    def __init__(self, canvas):
        from framebuf import FrameBuffer, RGB565
        from math import cos, sin, pi
        from tartlabutils.app import framebuffer_color

        self.canvas = canvas
        self.black = framebuffer_color(0x0000)
        self.white = framebuffer_color(0xFFFF)
        self.green = framebuffer_color(0x07E0)
        self.dark_green = framebuffer_color(0x0600)
        self.red = framebuffer_color(0xF800)
        self.orange = framebuffer_color(0xFD20)
        self.grey = framebuffer_color(0x8410)
        self.block = min(canvas.width // GRID_WIDTH, canvas.height // GRID_HEIGHT)
        # Preserve the original geometry wherever its top margin fits the HUD.
        # Shorter aspect ratios need room for the three-line status messages.
        if (canvas.height - GRID_HEIGHT * self.block) // 2 < 37:
            self.block = max(1, min(self.block, (canvas.height - 74) // GRID_HEIGHT))
        self.x = (canvas.width - GRID_WIDTH * self.block) // 2
        self.y = (canvas.height - GRID_HEIGHT * self.block) // 2
        self.text_height = max(0, self.y - 1)
        self.sprites = {}
        half = self.block // 2
        unit = max(1, self.block // 15)
        for name, color in (("apple", self.black), ("head", self.green),
                            ("body", self.dark_green), ("empty", self.black)):
            sprite = FrameBuffer(bytearray(self.block * self.block * 2),
                                 self.block, self.block, RGB565)
            sprite.fill(color)
            if name == "apple":
                sprite.ellipse(half, half, half, half, self.red, True)
                # The small white highlight follows the legacy 215–240° arc.
                for angle in range(215, 241):
                    radians = angle * pi / 180
                    sprite.pixel(round(half + half * cos(radians)),
                                 round(half + half * sin(radians)), self.white)
                sprite.fill_rect(half + unit, 0, unit * 2, unit * 4, self.dark_green)
                sprite.fill_rect(half, unit * 3, unit * 2, unit * 2, self.black)
            elif name == "head":
                sprite.fill_rect(half // 2, half // 2, 4, 4, self.black)
            self.sprites[name] = canvas.prepare_sprite(sprite, self.block, self.block)

    def controls(self):
        c = self.canvas
        c.fill(self.black)
        w, h = c.width // 2, c.height // 5
        for label, x, y, width, height in (
                ("Start", 0, 0, w, h), ("Pause", w, 0, c.width - w, h),
                ("Up", 0, h, c.width, h),
                ("Left", 0, h * 2, w, h * 2),
                ("Right", w, h * 2, c.width - w, h * 2),
                ("Down", 0, h * 4, c.width, c.height - h * 4)):
            c.rect(x, y, width, height, self.grey)
            c.text(label, x + width // 2 - len(label) * 4,
                   y + height // 2 - 4, self.orange)
        c.show()

    def cell(self, position, kind):
        x = self.x + position[0] * self.block
        y = self.y + position[1] * self.block
        self.canvas.draw_sprite(self.sprites[kind], x, y)
        self.canvas.show((x, y, self.block, self.block))

    def begin(self, game):
        c = self.canvas
        c.fill(self.black)
        c.rect(self.x - 1, self.y - 1, GRID_WIDTH * self.block + 2,
               GRID_HEIGHT * self.block + 2, self.grey)
        c.show()
        for apple in game.apples:
            self.cell(apple, "apple")
        self.show_text("Score 0")

    def show_text(self, message, color=None):
        c = self.canvas
        lines = message.split("\n")
        height = self.text_height
        c.fill_rect(0, 0, c.width, height, self.black)
        start_y = (height - len(lines) * 12) // 2
        for i, line in enumerate(lines):
            c.text(line, min(20, max(0, (c.width - len(line) * 8) // 2)),
                   start_y + i * 12, self.white if color is None else color)
        c.show((0, 0, c.width, height))

    def restore(self, game):
        self.begin(game)
        for position in game.snake[:-1]:
            self.cell(position, "body")
        self.cell(game.snake[-1], "head")
        self.show_text("Score %s" % game.score)


def wait_key(touch):
    from time import sleep_ms
    while True:
        key = touch.read()
        if key is not None:
            return key
        sleep_ms(10)


def play(view, touch):
    from time import sleep_ms, ticks_diff, ticks_ms
    high_score = load_high_score()
    view.controls()
    while wait_key(touch) != "start":
        pass
    game = SnakeGame()
    view.begin(game)
    last_move = ticks_ms()
    while True:
        key = touch.read()
        game.turn(key)
        if key == "pause":
            view.show_text("Paused.\nPress start 2x to quit,\nAny key to resume.")
            if wait_key(touch) == "start" and wait_key(touch) == "start":
                return False
            view.restore(game)
        if ticks_diff(ticks_ms(), last_move) > game.move_delay:
            last_move = ticks_ms()
            tail = game.snake[0]
            old_head = game.snake[-1]
            old_apples = tuple(game.apples)
            if not game.step():
                break
            if tail not in game.snake:
                view.cell(tail, "empty")
            view.cell(old_head, "body")
            view.cell(game.snake[-1], "head")
            if tuple(game.apples) != old_apples:
                for apple in game.apples:
                    if apple not in old_apples:
                        view.cell(apple, "apple")
                view.show_text("Score %s" % game.score)
            if not game.apples:
                break
        sleep_ms(5)
    if game.score > high_score:
        high_score = game.score
        save_high_score(high_score)
        title, color = "New High Score!", view.green
    else:
        title, color = "Game Over", view.white
    view.show_text("%s\nScore: %s\nHigh Score: %s" %
                   (title, game.score, high_score), color)
    while wait_key(touch) != "start":
        pass
    return True


def main():
    from tartlabutils.app import PortraitCanvas, PortraitTouchGrid, game_surface
    canvas = PortraitCanvas(game_surface())
    try:
        touch = PortraitTouchGrid(TOUCH_KEYS, 2, 5)
        view = SnakeView(canvas)
        while play(view, touch):
            pass
    finally:
        try:
            canvas.fill(0)
            canvas.show()
        finally:
            canvas.close()


if globals().get("_SNAKE_AUTOSTART", True):
    main()
