"""Grid puzzle: Phase 2 first playable room.

Copy this file to /files/user/my_puzzle.py to edit the actual implementation.
Move, collect keys, push boulders into water, and reach the exit.
Dirt, teleportation, hazards, and original sprite art arrive in later phases.

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
MOVED, COLLECTED, TERRAIN_CHANGED, OBJECT_CHANGED = 1, 2, 4, 8
DIED, FINISHED = 16, 32
ACTION_DIRECTIONS = {"north": NORTH, "east": EAST, "south": SOUTH, "west": WEST}


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
        self.next_due_ms = UPDATE_MS if self.kind == PLAYER else self.interval_ms
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
        self.events = bytearray(CELL_COUNT)  # Per-cell event bits; reused each step.
        self.step_events = 0
        self.pending_explosions = bytearray(CELL_COUNT)


def create_state(definition):
    return LevelState(definition)


# 4. Player movement, pushing, collection, teleportation ---------------------
def mark_changed(state, cell, event):
    state.changed_cells[cell] = 1
    state.events[cell] |= event


def accepts_boulder(state, cell):
    """Check the entire destination before committing either half of a push."""
    return (0 <= cell < CELL_COUNT and state.terrain[cell] in (FLOOR, WATER)
            and state.objects[cell] == EMPTY and state.actor_at[cell] == -1
            and state.spear_at[cell] == -1 and state.definition["twins"][cell] == -1)


def can_player_enter(state, cell):
    """Ordinary entry; boulder pushing has its own transaction below.

    Phase 3 adds digging/revealing; Phase 4 replaces actor blocking with contact
    hazards. The device rejects rooms needing those unimplemented mechanics.
    """
    return (0 <= cell < CELL_COUNT and (state.terrain[cell] == FLOOR or
            (state.terrain[cell] == EXIT and state.exit_active))
            and state.objects[cell] != BOULDER and state.actor_at[cell] == -1
            and state.spear_at[cell] == -1)


def move_player(state, heading):
    player = state.player
    destination = neighbor(player.cell, heading)
    if destination == -1:
        return False
    if state.objects[destination] == BOULDER:
        target = neighbor(destination, heading)
        if not accepts_boulder(state, target):
            return False
        # Nothing changes before the complete push is known to be legal.
        state.objects[destination] = EMPTY
        mark_changed(state, destination, OBJECT_CHANGED)
        if state.terrain[target] == WATER:
            state.terrain[target], state.variants[target] = FLOOR, 0
            mark_changed(state, target, TERRAIN_CHANGED)
        else:
            state.objects[target] = BOULDER
            mark_changed(state, target, OBJECT_CHANGED)
    elif not can_player_enter(state, destination):
        return False
    origin = player.cell
    state.actor_at[origin], state.actor_at[destination] = -1, player.id
    player.cell, player.heading = destination, heading
    mark_changed(state, origin, MOVED)
    mark_changed(state, destination, MOVED)
    return True


def collect_player_object(state):
    cell = state.player.cell
    obj = state.objects[cell]
    if obj in (KEY, DIAMOND):
        state.objects[cell] = EMPTY
        if obj == KEY:
            state.remaining_keys -= 1
        else:
            state.score += DIAMOND_SCORE
        mark_changed(state, cell, COLLECTED)

# 5. Snakes, spiders, traps, explosions --------------------------------------
# Phase 4 implements the documented predicates and hazard rules here.

# 6. Explicit simulation order ---------------------------------------------
def step(state, direction=None, dt_ms=UPDATE_MS):
    """One pure simulation quantum. None releases input; no clocks or I/O here.

    Event buffers describe only this quantum, including when it is frozen.
    Renderers must accumulate them before the next call (Phase 2 redraws fully).
    """
    if type(dt_ms) is not int or dt_ms != UPDATE_MS:
        raise ValueError("step requires one %s ms quantum" % UPDATE_MS)
    if direction is not None and (type(direction) is not int or direction not in range(4)):
        raise ValueError("direction must be one cardinal integer or None")
    state.step_events = 0
    for cell in range(CELL_COUNT):
        state.changed_cells[cell] = state.events[cell] = 0
    if state.paused or state.status != PLAYING:
        return
    state.elapsed_ms += dt_ms
    player = state.player
    # 1. Eligible intent. Failed attempts also advance the same deadline.
    moved = False
    if direction is not None and state.elapsed_ms >= player.next_due_ms:
        # After idle time, start a fresh interval. While held, retain the prior
        # due time so nonmultiples of 10 do not accumulate rounding drift.
        if player.next_due_ms <= state.elapsed_ms - dt_ms:
            player.next_due_ms = state.elapsed_ms
        player.next_due_ms += player.interval_ms
        # 2. Movement transaction (Phase 3 adds digging and revealing).
        moved = move_player(state, direction)
    # 3. Collect once on entry.
    if moved:
        collect_player_object(state)
    # 4. Player teleportation: Phase 3.
    # 5. Immediate contact and snake exposure: Phase 4.
    # 6. Due enemy movement and teleportation: Phase 4.
    # 7. Enemy/player collisions: Phase 4.
    # 8. Snapshot trapped spiders and queue explosions: Phase 4.
    # 9. Recalculate snake exposure: Phase 4.
    # 10. Activate/advance spear traps: Phase 4.
    # 11. Resolve explosions and resulting hazards: Phase 4.
    # 12. Reconcile keys from authoritative occupancy.
    state.remaining_keys = sum(1 for obj in state.objects if obj == KEY)
    # 13. Activate the exit in the same step as the final collection.
    active = state.remaining_keys == 0
    if active != state.exit_active:
        state.exit_active = active
        mark_changed(state, state.definition["exit"], TERRAIN_CHANGED)
    state.bonus = max(0, state.definition["bonusStart"] - state.elapsed_ms // 1000)
    # 14. Complete last; a latched death can never become completion.
    if state.status == PLAYING and player.alive and state.exit_active and player.cell == state.definition["exit"]:
        state.status = COMPLETED
        state.step_events |= FINISHED


class Session:
    """Room-local score rolls back on restart; completed rooms bank once."""
    def __init__(self, pack, start_level=0):
        self.pack, self.room_index = pack, start_level
        self.banked_score, self.room_award = 0, 0
        self.direction = None
        self.state = create_state(pack["levels"][start_level])

    def advance(self, updates):
        for unused in range(updates):
            step(self.state, self.direction)
            if self.state.step_events & FINISHED:
                self.room_award = self.state.score + self.state.bonus
                self.banked_score += self.room_award

    def restart(self):
        # Restart after completion must not allow banking this room twice.
        self.banked_score -= self.room_award
        self.room_award = 0
        self.direction = None
        self.state = create_state(self.pack["levels"][self.room_index])

    def next_room(self):
        if self.state.status != COMPLETED or self.room_index + 1 >= len(self.pack["levels"]):
            return False
        self.room_index += 1
        self.room_award = 0
        self.direction = None
        self.state = create_state(self.pack["levels"][self.room_index])
        return True

    def total_score(self):
        return self.banked_score if self.state.status == COMPLETED else self.banked_score + self.state.score


def validate_playable_pack(pack):
    """Keep future schema support without silently running incomplete rules."""
    for definition in pack["levels"]:
        if (any(t in (DIRT, FALSE_WALL) for t in definition["terrain"])
                or any(t != -1 for t in definition["twins"])
                or definition["messages"]
                or any(a[0] != PLAYER for a in definition["actors"])):
            raise ValueError('Room "%s" uses terrain, pads, messages or hazards pending Phases 3/4' % definition["name"])

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


def draw_game(canvas, session, layout, last_action=None, debug=False):
    """Primitive full redraw of live layers; no reference to initial occupancy."""
    state = session.state
    canvas.fill(0)
    title = "%s/%s %s" % (session.room_index + 1, len(session.pack["levels"]), state.definition["name"])
    canvas.text(title[:layout.width // 8], 0, 0, 0xFFFF)
    status = "PAUSED" if state.paused else ("PLAY", "DEAD", "DONE")[state.status]
    hud = "K%s S%s B%s %s" % (state.remaining_keys, session.total_score(), state.bonus, status)
    canvas.text(hud[:layout.width // 8], 0, 12, 0xFFFF)
    bx, by, unused_w, unused_h = layout.board
    size = layout.tile_size
    colors = (0x1082, 0x632C, 0x8200, 0x025F, 0x632C, 0x7800)
    for cell in range(CELL_COUNT):
        x, y = bx + (cell % COLS) * size, by + (cell // COLS) * size
        terrain = state.terrain[cell]
        color = 0x0400 if terrain == EXIT and state.exit_active else colors[terrain]
        canvas.rect(x, y, size, size, color, True)
        canvas.rect(x, y, size, size, 0x4208)
        glyph = "E" if terrain == EXIT else ""
        obj = state.objects[cell]
        if obj != EMPTY:
            glyph = ("", "K", "*", "O")[obj]
        actor_id = state.actor_at[cell]
        if actor_id != -1:
            glyph = ("P", "S", "X", "R")[state.actors[actor_id].kind]
        if glyph:
            canvas.text(glyph, x + (size - 8) // 2, y + (size - 8) // 2, 0xFFFF)
        if debug and (terrain == FALSE_WALL or state.definition["labels"][cell] != -1):
            canvas.text(state.definition["tokens"][cell], x, y, 0xFFE0)
    rx, ry = layout.readout
    canvas.text("Exit open" if state.exit_active else "Exit locked", rx, ry, 0xFFFF)
    pause_label = "Play" if state.paused else "Pause"
    if state.status == COMPLETED:
        pause_label = "Next" if session.room_index + 1 < len(session.pack["levels"]) else "Done"
    labels = {"north": "^", "east": ">", "south": "v", "west": "<",
              "restart": "Reset", "pause": pause_label, "back": "Back"}
    for action, (x, y, width, height) in layout.controls:
        canvas.rect(x, y, width, height, 0xFFFF)
        if action == last_action:
            canvas.rect(x + 2, y + 2, width - 4, height - 4, 0xFFFF)
        canvas.text(labels[action], x + 4, y + 12, 0xFFFF)
    canvas.show()  # Exactly one presentation coordinator.


# 8. Input handling, session, resource cleanup, main -------------------------
class Controls:
    """Most recent held direction wins; action controls fire only on edges.

    Touch precedes ordered button events within a poll, so a simultaneous button
    press wins. Releasing it restores the most recent still-held direction.
    """
    def __init__(self):
        self.buttons_down = {}
        self.touch_direction = None
        self.touch_down = False
        self.held = []  # At most four direction buttons and one touch.
        self.suppressed = True
        self.fresh_touch = False

    def reset(self):
        self.held[:] = []
        self.touch_direction = None
        self.suppressed = True  # All physical inputs must release after reset.

    def _hold(self, source, direction):
        for index, entry in enumerate(self.held):
            if entry[0] == source:
                del self.held[index]
                break
        if direction is not None:
            self.held.append((source, direction))

    def poll(self, point, button_events, layout):
        was_down = self.touch_down
        self.touch_down = point is not None
        self.fresh_touch = self.touch_down and not was_down and not self.suppressed
        touch_action = layout.action_from_point(*point) if point is not None else None
        direction = ACTION_DIRECTIONS.get(touch_action)
        action = None
        if not self.suppressed:
            if direction != self.touch_direction:
                self._hold("touch", direction)
            if self.fresh_touch and touch_action not in ACTION_DIRECTIONS:
                action = touch_action
        self.touch_direction = direction
        for name, pressed in button_events:
            mapped = BUTTON_ACTIONS.get(name)
            if mapped is None:
                continue
            previous = self.buttons_down.get(name, False)
            self.buttons_down[name] = pressed
            if not self.suppressed and pressed != previous:
                if mapped in ACTION_DIRECTIONS:
                    self._hold(name, ACTION_DIRECTIONS[mapped] if pressed else None)
                elif pressed:
                    action = mapped
        if self.suppressed and not self.touch_down and not any(self.buttons_down.values()):
            self.suppressed = False
        return action

    def direction(self):
        return self.held[-1][1] if self.held else None


def run(pack, platform, canvas, layout, debug=False, clock_factory=None):
    if clock_factory is None:
        from tartlabutils.timing import FrameClock
        clock_factory = lambda: FrameClock(frame_ms=FRAME_MS, update_ms=UPDATE_MS, max_updates=10)
    validate_playable_pack(pack)
    session, controls = Session(pack), Controls()
    clock = clock_factory()
    missed, dropped, wake_polls = 0, 0, 0
    print("Directions move; Reset restarts; Pause/Play freezes/resumes; Next advances; Back returns to UI.")
    print(inspect_cell(session.state, session.state.player.cell))
    try:
        while True:
            point = None
            if layout.touch:
                if wake_polls == 0:
                    platform.keep_touch_awake()
                wake_polls = (wake_polls + 1) % 100
                raw = platform.read_game_touch()
                if raw is not None:
                    point = layout.logical_point(raw, platform.height)
            action = controls.poll(point, platform.read_button_events(), layout)
            updates = clock.updates_due() if session.state.status == PLAYING and not session.state.paused else 0
            if action == "back":
                return session
            rebase = False
            if action == "restart":
                session.restart()
                rebase = True
            elif action == "pause":
                if session.state.status == COMPLETED:
                    rebase = session.next_room()
                elif session.state.status == PLAYING:
                    session.state.paused = not session.state.paused
                    rebase = True
            if rebase:
                controls.reset()
                session.direction = None
                missed += clock.missed_deadlines
                dropped += clock.dropped_update_ms
                clock = clock_factory()  # Discard paused wall time and old backlog.
            else:
                # Observed input belongs to the END of the elapsed batch. Queue
                # it for the next quantum, never apply a newly polled edge to
                # already elapsed catch-up steps.
                was_playing = session.state.status == PLAYING
                session.advance(updates)
                if was_playing and session.state.status != PLAYING:
                    controls.reset()
                session.direction = controls.direction() if not session.state.paused else None
            if controls.fresh_touch and point is not None:
                selected = layout.cell_from_point(*point)
                if selected != -1:
                    print(inspect_cell(session.state, selected))
            draw_game(canvas, session, layout, action, debug)
            clock.pace()
    finally:
        print("Grid puzzle timing: missed=%s dropped_update_ms=%s" %
              (missed + clock.missed_deadlines, dropped + clock.dropped_update_ms))


def main():
    # Validate first, before importing device modules or allocating a canvas.
    pack = load_level_pack(LEVEL_FILE)
    validate_playable_pack(pack)
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
        run(pack, platform, canvas, layout, DEBUG)
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
