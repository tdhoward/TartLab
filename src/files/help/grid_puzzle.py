"""Grid puzzle: Phase 1 room contracts and interactive layout/input probe.

Copy this file to /files/user/my_puzzle.py to edit the actual implementation.
The movement and hazard phases are still pending; this probe inspects a room.

CODE MAP (search these numbered headings):
1. Settings   2. Symbols   3. Loading and state   4. Player interactions
5. Hazards    6. Simulation order   7. Layout/drawing   8. Input and main
"""

# 1. Settings ---------------------------------------------------------------
LEVEL_FILE = "/files/help/grid_puzzle_levels.json"
ASSET_FILE = "/files/assets/grid_puzzle.ts16"  # Artwork arrives in Phase 3.
DEBUG = False

COLS, ROWS, TILE_SIZE = 16, 12, 16
CELL_COUNT = COLS * ROWS
UPDATE_MS = 10
FRAME_MS = 50  # Proposed, not yet a measured device performance claim.
PLAYER_MS, SPIDER_MS, PROJECTILE_MS = 110, 150, 40
DIAMOND_SCORE, BONUS_START = 100, 500

# Names are logical button events, never GPIOs or board identities.
BUTTON_ACTIONS = {
    "up": "north", "right": "east", "down": "south", "left": "west",
    "restart": "restart", "pause": "pause", "back": "back",
}

# 2. Symbols and interaction vocabulary -------------------------------------
FLOOR, WALL, DIRT, WATER, FALSE_WALL, EXIT = range(6)
EMPTY, KEY, DIAMOND, BOULDER = range(4)
PLAYER, SNAKE, SPIDER, EMITTER = range(4)
NORTH, EAST, SOUTH, WEST = range(4)
FOLLOW_LEFT, FOLLOW_RIGHT = 0, 1
IDLE, EXTENDING, STOPPED = range(3)
PLAYING, DEAD, COMPLETED = range(3)
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
TERRAIN_NAMES = ("floor", "wall", "dirt", "water", "false wall", "exit")
OBJECT_NAMES = ("empty", "key", "diamond", "boulder")
ACTOR_NAMES = ("player", "snake", "spider", "spear emitter")


def cell_at(x, y):
    """Return -1 outside the room; check before using it as an array index."""
    if 0 <= x < COLS and 0 <= y < ROWS:
        return y * COLS + x
    return -1


def neighbor(cell, heading):
    if not 0 <= cell < CELL_COUNT or heading not in (NORTH, EAST, SOUTH, WEST):
        return -1
    dx, dy = DIRECTIONS[heading]
    return cell_at(cell % COLS + dx, cell // COLS + dy)


def decode_token(token, path="token"):
    """Return terrain, variant, object, actor, heading, follow mode, pad label.

    -1 means no actor/heading/follow mode/pad. Case is meaningful for spiders.
    A single token specifies all initial occupancy; metadata cannot add layers.
    """
    terrain, variant, obj = FLOOR, 0, EMPTY
    actor = heading = follow = label = -1
    if token == "..":
        pass
    elif token == "P.":
        actor, heading = PLAYER, SOUTH
    elif token == "E.":
        terrain = EXIT
    elif token in ("K.", "D.", "O."):
        obj = {"K.": KEY, "D.": DIAMOND, "O.": BOULDER}[token]
    elif token == "S.":
        actor = SNAKE
    elif len(token) == 2 and token[0] in "#WdFT" and token[1] in "0123456789":
        variant = int(token[1])
        if token[0] == "W" and variant == 9:
            _fail(path, "unknown token 'W9'; water variants are W0 through W8")
        if token[0] == "T":
            label, variant = variant, 0
        else:
            terrain = {"#": WALL, "W": WATER, "d": DIRT, "F": FALSE_WALL}[token[0]]
    elif len(token) == 2 and token[0] == "X" and token[1] in "neswNESW":
        actor = SPIDER
        heading = "nesw".index(token[1].lower())
        follow = FOLLOW_LEFT if token[1] in "nesw" else FOLLOW_RIGHT
    elif len(token) == 2 and token[0] == "R" and token[1] in "NESW":
        actor, heading = EMITTER, "NESW".index(token[1])
    else:
        _fail(path, "unknown token %r" % token)
    return terrain, variant, obj, actor, heading, follow, label


# 3. JSON loading/validation and logical state -------------------------------
def _fail(path, message):
    raise ValueError("%s: %s" % (path, message))


def _fields(value, allowed, required, path):
    if not isinstance(value, dict):
        _fail(path, "expected an object")
    for key in value:
        if key not in allowed:
            _fail(path, "unknown field %r" % key)
    for key in required:
        if key not in value:
            _fail(path, "missing field %r" % key)


def _integer(value, minimum, path, maximum=None):
    if type(value) is not int or value < minimum or (
            maximum is not None and value > maximum):
        limit = "at least %s" % minimum if maximum is None else "%s..%s" % (minimum, maximum)
        _fail(path, "expected integer %s (booleans are not integers here)" % limit)
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        _fail(path, "expected nonempty text")
    return value


def _records(value, path):
    if not isinstance(value, list) or len(value) > CELL_COUNT:
        _fail(path, "expected an array with at most %s records" % CELL_COUNT)
    return value


def validate_level(level, level_index=0):
    """Validate JSON data and return a definition with independent, fixed layers.

    Room numbers in errors are one-based; map rows/columns are zero-based.
    This checks structure, not solvability or whether a start is safe.
    """
    path = "room %s" % (level_index + 1)
    _fields(level, ("name", "map", "bonusStart", "timers", "actors", "messages", "rules"),
            ("name", "map"), path)
    name = _text(level["name"], path + ".name")
    path += ' "%s"' % name
    bonus = _integer(level.get("bonusStart", BONUS_START), 0, path + ".bonusStart")
    timers = {"player_ms": PLAYER_MS, "spider_ms": SPIDER_MS, "projectile_ms": PROJECTILE_MS}
    overrides = level.get("timers", {})
    _fields(overrides, timers, (), path + ".timers")
    for key in overrides:
        timers[key] = _integer(overrides[key], UPDATE_MS, path + ".timers." + key)

    rules = {"explosion_destructible": ("BOULDER", "DIRT"),
             "explosion_diamonds": True, "explosion_hurts_player": True}
    overrides = level.get("rules", {})
    _fields(overrides, rules, (), path + ".rules")
    for key, value in overrides.items():
        rule_path = path + ".rules." + key
        if key == "explosion_destructible":
            if not isinstance(value, list):
                _fail(rule_path, "expected an array of BOULDER and/or DIRT")
            seen = []
            for entry in value:
                if entry not in ("BOULDER", "DIRT") or entry in seen:
                    _fail(rule_path, "unsupported or duplicate destructible %r" % entry)
                seen.append(entry)
            rules[key] = tuple(seen)
        else:
            if type(value) is not bool:
                _fail(rule_path, "expected true or false")
            rules[key] = value

    rows = level["map"]
    if not isinstance(rows, list) or len(rows) != ROWS:
        _fail(path + ".map", "expected exactly 12 row strings")
    terrain, variants, objects, tokens, actors = [], [], [], [], []
    actor_by_cell, pads, messages = {}, {}, []
    starts, exits = [], []
    for y, row in enumerate(rows):
        row_path = "%s, row %s" % (path, y)
        if not isinstance(row, str):
            _fail(row_path, "expected a row string")
        row_tokens = row.split()
        if len(row_tokens) != COLS:
            _fail(row_path, "expected 16 tokens; got %s" % len(row_tokens))
        for x, token in enumerate(row_tokens):
            cell = cell_at(x, y)
            values = decode_token(token, "%s, column %s" % (row_path, x))
            ground, variant, obj, kind, heading, follow, label = values
            terrain.append(ground)
            variants.append(variant)
            objects.append(obj)
            tokens.append(token)
            if kind != -1:
                # Token expansion guarantees floor without objects for actors.
                interval = timers["player_ms"] if kind == PLAYER else timers["spider_ms"]
                if kind == EMITTER:
                    interval = timers["projectile_ms"]
                elif kind == SNAKE:
                    interval = 0  # Stationary; queried after occupancy changes.
                actor_by_cell[cell] = len(actors)
                actors.append((kind, cell, heading, follow, interval))
            if kind == PLAYER:
                starts.append(cell)
            if ground == EXIT:
                exits.append(cell)
            if label != -1:
                pads.setdefault(label, []).append(cell)
    if len(starts) != 1 or len(exits) != 1:
        _fail(path, "expected one player start and one exit; got %s and %s" %
              (len(starts), len(exits)))

    twins, labels = [-1] * CELL_COUNT, [-1] * CELL_COUNT
    for label, cells in pads.items():
        if len(cells) != 2:
            coordinates = [(cell % COLS, cell // COLS) for cell in cells]
            _fail(path, "T%s occurs %s times at %s; expected exactly two" %
                  (label, len(cells), coordinates))
        first, second = cells
        twins[first], twins[second] = second, first
        labels[first] = labels[second] = label

    annotated = []
    for i, annotation in enumerate(_records(level.get("actors", []), path + ".actors")):
        item_path = "%s.actors[%s]" % (path, i)
        _fields(annotation, ("x", "y", "step_ms"), ("x", "y", "step_ms"), item_path)
        x = _integer(annotation["x"], 0, item_path + ".x", COLS - 1)
        y = _integer(annotation["y"], 0, item_path + ".y", ROWS - 1)
        cell = cell_at(x, y)
        if cell in annotated:
            _fail(item_path, "duplicate actor annotation at (%s, %s)" % (x, y))
        annotated.append(cell)
        index = actor_by_cell.get(cell, -1)
        if index == -1 or actors[index][0] != EMITTER:
            _fail(item_path, "only map spear emitters accept metadata; spiders do not")
        interval = _integer(annotation["step_ms"], UPDATE_MS, item_path + ".step_ms")
        actors[index] = actors[index][:4] + (interval,)

    message_cells = []
    for i, message in enumerate(_records(level.get("messages", []), path + ".messages")):
        item_path = "%s.messages[%s]" % (path, i)
        _fields(message, ("text", "loc_x", "loc_y"), ("text", "loc_x", "loc_y"), item_path)
        text = _text(message["text"], item_path + ".text")
        x = _integer(message["loc_x"], 0, item_path + ".loc_x", COLS - 1)
        y = _integer(message["loc_y"], 0, item_path + ".loc_y", ROWS - 1)
        cell = cell_at(x, y)
        if cell in message_cells:
            _fail(item_path, "duplicate message location (%s, %s)" % (x, y))
        actor_index = actor_by_cell.get(cell, -1)
        if terrain[cell] in (WALL, WATER) or (actor_index != -1 and
                actors[actor_index][0] in (SNAKE, EMITTER)):
            _fail(item_path, "message location must be enterable terrain without a stationary enemy")
        message_cells.append(cell)
        messages.append((cell, text))

    return {"name": name, "terrain": tuple(terrain), "variants": tuple(variants),
            "objects": tuple(objects), "tokens": tuple(tokens), "actors": tuple(actors),
            "twins": tuple(twins), "labels": tuple(labels), "messages": tuple(messages),
            "start": starts[0], "exit": exits[0], "bonusStart": bonus,
            "timers": timers, "rules": rules}


def validate_level_pack(pack):
    _fields(pack, ("version", "levels"), ("version", "levels"), "pack")
    _integer(pack["version"], 1, "pack.version", 1)
    if not isinstance(pack["levels"], list) or not pack["levels"]:
        _fail("pack.levels", "expected a nonempty array")
    return {"version": 1, "levels": tuple(validate_level(room, i)
            for i, room in enumerate(pack["levels"]))}


def load_level_pack(path):
    """Read the selected JSON once. Errors retain its path; there is no fallback."""
    import json
    try:
        with open(path, "r") as stream:
            pack = json.load(stream)
        return validate_level_pack(pack)
    except (OSError, ValueError) as error:
        raise ValueError("Level file %s: %s" % (path, error))


class Actor:
    def __init__(self, actor_id, record):
        self.id = actor_id
        self.kind, self.cell, self.heading, self.follow, self.interval_ms = record
        self.next_due_ms = 0 if self.kind == PLAYER else self.interval_ms
        self.alive = True
        self.trap_state = IDLE
        self.tip = self.cell


class LevelState:
    def __init__(self, definition):
        self.definition = definition  # Read-only; restart never edits the source.
        self.terrain = bytearray(definition["terrain"])
        self.variants = bytearray(definition["variants"])
        self.objects = bytearray(definition["objects"])
        self.actors = [Actor(i, record) for i, record in enumerate(definition["actors"])]
        self.actor_at = [-1] * CELL_COUNT
        self.spear_at = [-1] * CELL_COUNT
        for actor in self.actors:
            self.actor_at[actor.cell] = actor.id
            if actor.kind == PLAYER:
                self.player = actor
        for actor in self.actors:
            if actor.kind == SNAKE:
                actor.heading = EAST if self.player.cell % COLS >= actor.cell % COLS else WEST
        # MicroPython bytearray.count expects bytes, not CPython's integer form.
        self.remaining_keys = sum(1 for obj in self.objects if obj == KEY)
        self.exit_active = self.remaining_keys == 0
        self.status, self.elapsed_ms, self.score = PLAYING, 0, 0
        self.bonus = definition["bonusStart"]
        self.message_seen = bytearray(len(definition["messages"]))
        self.active_message = -1
        for i, message in enumerate(definition["messages"]):
            if message[0] == self.player.cell:
                self.active_message = i
                self.message_seen[i] = 1
        self.paused = self.active_message != -1
        # Reused, room-bounded flags for the later simulation/rendering phases.
        self.changed_cells = bytearray(CELL_COUNT)
        self.pending_explosions = bytearray(CELL_COUNT)


def create_state(definition):
    return LevelState(definition)


# 4. Player movement, pushing, collection, teleportation ---------------------
# Phase 2 implements player transactions here; Phase 3 adds terrain/teleports.
# The probe below moves an inspector cursor, never the player or room objects.

# 5. Snakes, spiders, traps, explosions --------------------------------------
# Phase 4 implements the documented predicates and hazard rules here.

# 6. Explicit simulation order ---------------------------------------------
# No simulation runs in Phase 1. Implement step(state, input_state, dt_ms=10)
# here with all fourteen stages documented in GRID_PUZZLE_PROJECT.md.

# 7. Art preparation, layout, rendering, debug -------------------------------
HUD_HEIGHT, PANEL_WIDTH, PANEL_HEIGHT, CONTROL_SIZE = 24, 112, 112, 32


class Layout:
    def __init__(self, width, height, rotation, scale, placement, touch):
        self.width, self.height, self.rotation = width, height, rotation
        self.scale, self.placement, self.touch = scale, placement, touch
        self.tile_size = TILE_SIZE * scale
        board_width, board_height = COLS * self.tile_size, ROWS * self.tile_size
        panel_width = PANEL_WIDTH if placement == "side" else 0
        panel_height = PANEL_HEIGHT if placement == "below" else 0
        footer_height = 8 if placement == "buttons" else 0
        x = (width - board_width - panel_width) // 2
        y = HUD_HEIGHT + (height - HUD_HEIGHT - board_height - panel_height - footer_height) // 2
        self.board = (x, y, board_width, board_height)
        self.controls = []
        if placement == "side":
            px, py = x + board_width, y
            self.readout = (px, py)
            pad_x, pad_y = px + 8, py + 20
            action_x, action_y = px, py + 120
        elif placement == "below":
            px, py = x, y + board_height
            self.readout = (px + 104, py)
            pad_x, pad_y = px, py + 8
            action_x, action_y = px + 104, py + 24
        else:
            self.readout = (0, height - 8)
            return
        for action, col, row in (("north", 1, 0), ("west", 0, 1),
                                 ("east", 2, 1), ("south", 1, 2)):
            self.controls.append((action, (pad_x + col * CONTROL_SIZE,
                                          pad_y + row * CONTROL_SIZE, CONTROL_SIZE, CONTROL_SIZE)))
        self.controls.extend((("restart", (action_x, action_y, 56, 32)),
                              ("pause", (action_x + 56, action_y, 56, 32)),
                              ("back", (action_x, action_y + 36, 112, 32))))

    def logical_point(self, point, native_height):
        # The same rotation passed to DirectCanvas: logical x = H - 1 - y.
        x, y = point
        return (native_height - 1 - y, x) if self.rotation == 90 else (x, y)

    def cell_from_point(self, x, y):
        bx, by, bw, bh = self.board
        if bx <= x < bx + bw and by <= y < by + bh:
            return cell_at((x - bx) // self.tile_size, (y - by) // self.tile_size)
        return -1

    def action_from_point(self, x, y):
        for action, (cx, cy, cw, ch) in self.controls:
            if cx <= x < cx + cw and cy <= y < cy + ch:
                return action
        return None


def choose_layout(width, height, touch=True, button_names=()):
    """Fit a whole square-tiled board, HUD and controls using capabilities only."""
    _integer(width, 1, "display.width")
    _integer(height, 1, "display.height")
    if not touch and not all(name in button_names for name in BUTTON_ACTIONS):
        raise ValueError("Grid puzzle needs touch or named up/right/down/left/restart/pause/back buttons")
    candidates = []
    for rotation, w, h in ((0, width, height), (90, height, width)):
        if touch:
            options = (("side", (w - PANEL_WIDTH) // 256, (h - HUD_HEIGHT) // 192),
                       ("below", w // 256, (h - HUD_HEIGHT - PANEL_HEIGHT) // 192))
        else:
            options = (("buttons", w // 256, (h - HUD_HEIGHT - 8) // 192),)
        for placement, sx, sy in options:
            scale = min(sx, sy)
            if scale > 0:
                candidates.append(Layout(w, h, rotation, scale, placement, touch))
    if not candidates:
        raise ValueError("Grid puzzle: %sx%s cannot fit a 256x192 room plus HUD and controls; "
                         "use IDE/reset to choose another app" % (width, height))
    # Largest integer scale, then side panel, then native rotation. No cropping.
    return max(candidates, key=lambda item: (item.scale, item.placement == "side", item.rotation == 0))


def inspect_cell(state, cell):
    if not 0 <= cell < CELL_COUNT:
        raise ValueError("inspector cell is outside the room")
    description = TERRAIN_NAMES[state.terrain[cell]]
    if state.objects[cell] != EMPTY:
        description += " + " + OBJECT_NAMES[state.objects[cell]]
    actor_id = state.actor_at[cell]
    if actor_id != -1:
        description += " + " + ACTOR_NAMES[state.actors[actor_id].kind]
    label = state.definition["labels"][cell]
    if label != -1:
        twin = state.definition["twins"][cell]
        description += " + T%s twin (%s,%s)" % (label, twin % COLS, twin // COLS)
    return "(%s,%s) %s" % (cell % COLS, cell // COLS, description)


def draw_probe(canvas, state, layout, selected, last_action, debug=False):
    """Primitive contract preview. Original sprites and game rendering follow."""
    canvas.fill(0)
    canvas.text("Grid puzzle: layout probe", 0, 0, 0xFFFF)
    canvas.text("K:%s %s" % (state.remaining_keys, state.definition["name"][:20]), 0, 12, 0xFFFF)
    bx, by, unused_w, unused_h = layout.board
    size = layout.tile_size
    for cell, token in enumerate(state.definition["tokens"]):
        x, y = bx + (cell % COLS) * size, by + (cell // COLS) * size
        # Concealed features use exactly the same pixels as their visible base.
        visible = ".." if token[0] == "T" else ("#" + token[1] if token[0] == "F" else token)
        canvas.rect(x, y, size, size, 0x4208)
        canvas.text(token if debug else visible, x, y + (size - 8) // 2, 0xFFFF)
    x, y = bx + (selected % COLS) * size, by + (selected // COLS) * size
    canvas.rect(x, y, size, size, 0xFFFF)
    rx, ry = layout.readout
    canvas.text("%s,%s %s" % (selected % COLS, selected // COLS,
                              state.definition["tokens"][selected] if debug else ""), rx, ry, 0xFFFF)
    labels = {"north": "^", "east": ">", "south": "v", "west": "<",
              "restart": "Reset", "pause": "Pause", "back": "Back"}
    for action, (x, y, width, height) in layout.controls:
        canvas.rect(x, y, width, height, 0xFFFF)
        if action == last_action:
            canvas.rect(x + 2, y + 2, width - 4, height - 4, 0xFFFF)
        canvas.text(labels[action], x + 4, y + 12, 0xFFFF)
    canvas.show()


# 8. Input handling, probe session, resource cleanup, main -------------------
def run_probe(pack, platform, canvas, layout, debug=False):
    import time
    state = create_state(pack["levels"][0])
    selected = state.player.cell
    last_action = None
    released = False  # Require a release after ownership changes.
    wake_polls = 0
    draw_probe(canvas, state, layout, selected, last_action, debug)
    print("Phase 1: directions select cells; Reset rebuilds state; Pause toggles labels; Back returns to UI.")
    print(inspect_cell(state, selected))
    while True:
        action, point = None, None
        touch_is_down = False
        if layout.touch:
            if wake_polls == 0:
                platform.keep_touch_awake()
            wake_polls = (wake_polls + 1) % 250
            raw = platform.read_game_touch()
            touch_is_down = raw is not None
            if raw is None:
                released = True
            elif released:
                point = layout.logical_point(raw, platform.height)
                action = layout.action_from_point(*point)
                released = False
        for name, pressed in platform.read_button_events():
            if pressed:
                action = BUTTON_ACTIONS.get(name)
        if action == "back":
            return
        changed = False
        if point is not None:
            cell = layout.cell_from_point(*point)
            if cell != -1:
                selected, changed = cell, True
        if action in ("north", "east", "south", "west"):
            cell = neighbor(selected, ("north", "east", "south", "west").index(action))
            if cell != -1:
                selected = cell
        elif action == "restart":
            state = create_state(pack["levels"][0])
            selected = state.player.cell
        elif action == "pause":
            debug = not debug
        clear_highlight = not touch_is_down and last_action is not None
        if action is not None or changed or clear_highlight:
            last_action = action
            draw_probe(canvas, state, layout, selected, last_action, debug)
            if action or changed:
                print(inspect_cell(state, selected))
        time.sleep_ms(20)


def main():
    # Validate first, before importing device modules or allocating a canvas.
    pack = load_level_pack(LEVEL_FILE)
    from tartlabutils.platform import get_platform
    platform = get_platform()
    if not platform.capabilities.get("direct_rgb565", False):
        raise ValueError("Grid puzzle requires the modern direct canvas; return to IDE/reset")
    buttons = getattr(platform, "buttons", None)
    layout = choose_layout(platform.width, platform.height,
                           platform.capabilities.get("touch", False),
                           buttons.names if buttons is not None else ())
    print("Level file: %s; %s rooms; %sx%s rotation=%s scale=%s %s" %
          (LEVEL_FILE, len(pack["levels"]), layout.width, layout.height,
           layout.rotation, layout.scale, layout.placement))
    from tartlabutils.app import DirectCanvas, game_surface
    canvas = None
    try:
        canvas = DirectCanvas(game_surface(), rotation=layout.rotation)
        run_probe(pack, platform, canvas, layout, DEBUG)
    finally:
        try:
            if canvas is not None:
                canvas.close()
        finally:
            try:
                if buttons is not None:
                    buttons.reset()
            finally:
                platform.enter_ui_mode()


if globals().get("_GRID_PUZZLE_AUTOSTART", True):
    main()
