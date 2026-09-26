"""Grid puzzle: editable movement, terrain, teleportation and hazard engine.

Copy this file to /files/user/my_puzzle.py to edit the actual implementation.
Move, collect keys, push boulders into water, and reach the exit.
Dig dirt, reveal false walls and discover paired hidden passages.
Watch snake cover, wall-following spiders and one-shot extending spears.

CODE MAP (search these numbered headings):
1. Settings   2. Symbols   3. Loading and state   4. Player interactions
5. Hazards    6. Simulation order   7. Layout/drawing   8. Input and main
"""

# 1. Settings ---------------------------------------------------------------
LEVEL_FILE = "/files/help/grid_puzzle_levels.json"
ASSET_FILE = "/files/assets/grid_puzzle.ts16"
DEBUG = False

COLS, ROWS, TILE_SIZE = 16, 12, 16
CELL_COUNT = COLS * ROWS
UPDATE_MS = 10
FRAME_MS = 50  # Proposed, not yet a measured device performance claim.
CANVAS_TRANSFER_ROWS = 64  # Amortize surface transactions; measured by the benchmark.
PLAYER_MS, SPIDER_MS, PROJECTILE_MS = 110, 150, 40
DIAMOND_SCORE, BONUS_START = 100, 500
BLAST_MS = 180  # Visual only: damage resolves once, before these frames appear.

# Names are logical button events, never GPIOs or board identities.
BUTTON_ACTIONS = {
    "up": "north", "right": "east", "down": "south", "left": "west",
    "restart": "restart", "pause": "pause", "back": "back",
}

# 2. Symbols and interaction vocabulary -------------------------------------
FLOOR, WALL, DIRT, WATER, FALSE_WALL, EXIT = range(6)
EMPTY, KEY, DIAMOND, BOULDER = range(4)
KEY_BYTE = bytes((KEY,))
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
TELEPORTED = 64
EFFECT_CHANGED = 128
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
        self.snakes = [actor for actor in self.actors if actor.kind == SNAKE]
        self.spiders = [actor for actor in self.actors if actor.kind == SPIDER]
        self.emitters = [actor for actor in self.actors if actor.kind == EMITTER]
        self.occupancy_version, self.trapped_version = 0, -1
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
        self.remaining_keys = self.objects.count(KEY_BYTE)  # Bytes works on both interpreters.
        self.exit_active = self.remaining_keys == 0
        self.status, self.elapsed_ms, self.score = PLAYING, 0, 0
        self.bonus = definition["bonusStart"]
        self.message_seen = bytearray(len(definition["messages"]))
        self.active_message = -1
        self.pending_messages = []  # Each validated message can enter once.
        for i, message in enumerate(definition["messages"]):
            if message[0] == self.player.cell:
                self.active_message = i
                self.message_seen[i] = 1
        self.paused = self.active_message != -1
        # Reused room-bounded buffers; explosions never grow an event list.
        self.changed_cells = bytearray(CELL_COUNT)
        self.clear_cells = bytes(CELL_COUNT)
        self.events = bytearray(CELL_COUNT)  # Per-cell event bits; reused each step.
        self.step_events = 0
        self.pending_explosions = bytearray(CELL_COUNT)
        self.blast_cells = bytearray(CELL_COUNT)
        self.blast_drops = bytearray(CELL_COUNT)
        self.blast_until = [0] * CELL_COUNT


def create_state(definition):
    return LevelState(definition)


# 4. Player movement, pushing, collection, teleportation ---------------------
def mark_changed(state, cell, event):
    state.changed_cells[cell] = 1
    state.events[cell] |= event
    state.occupancy_version += 1


def accepts_boulder(state, cell):
    """Check the entire destination before committing either half of a push."""
    return (0 <= cell < CELL_COUNT and state.terrain[cell] in (FLOOR, WATER)
            and state.objects[cell] == EMPTY and state.actor_at[cell] == -1
            and state.spear_at[cell] == -1 and state.definition["twins"][cell] == -1)


def can_player_enter(state, cell):
    """Legal entry may be lethal; collision is resolved after the transaction."""
    if not 0 <= cell < CELL_COUNT:
        return False
    actor_id, spear_id = state.actor_at[cell], state.spear_at[cell]
    return ((state.terrain[cell] in (FLOOR, DIRT, FALSE_WALL) or
             (state.terrain[cell] == EXIT and state.exit_active))
            and state.objects[cell] != BOULDER
            and (actor_id == -1 or state.actors[actor_id].kind != EMITTER)
            and (spear_id == -1 or state.actors[spear_id].trap_state == EXTENDING))


def can_spider_enter(state, cell, actor):
    """Shared entry query for teleport previews and autonomous spider moves."""
    if not 0 <= cell < CELL_COUNT:
        return False
    occupant = state.actor_at[cell]
    return (state.terrain[cell] == FLOOR and state.objects[cell] == EMPTY
            and state.spear_at[cell] == -1
            and (occupant in (-1, actor.id) or occupant == state.player.id))


def place_actor(state, actor, destination, event=MOVED):
    origin = actor.cell
    if state.actor_at[origin] == actor.id:
        state.actor_at[origin] = -1
    # On lethal contact retain the enemy in the lookup. The player also has an
    # explicit position, so neither actor disappears from collision queries.
    if actor.kind != PLAYER or state.actor_at[destination] == -1:
        state.actor_at[destination] = actor.id
    actor.cell = destination
    mark_changed(state, origin, event)
    mark_changed(state, destination, event)


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
    if state.terrain[destination] in (DIRT, FALSE_WALL):
        state.terrain[destination], state.variants[destination] = FLOOR, 0
        mark_changed(state, destination, TERRAIN_CHANGED)
    place_actor(state, player, destination)
    player.heading = heading
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


def teleport_destination(state, actor, entered_cell):
    """Pure one-hop query; a blocked arrival returns the entered pad itself.

    Call only on entry. Standing on a pad never bounces or retries, and the same
    query can preview a spider's complete move without changing any occupancy.
    """
    if not 0 <= entered_cell < CELL_COUNT:
        return -1
    twin = state.definition["twins"][entered_cell]
    if twin != -1:
        allowed = (can_player_enter(state, twin) if actor.kind == PLAYER else
                   can_spider_enter(state, twin, actor))
        if allowed:
            return twin
    return entered_cell


def teleport_actor(state, actor):
    # Entering an occupied source pad cannot provide an escape from contact.
    resolve_contact(state)
    if actor.kind == PLAYER and state.status != PLAYING:
        return False
    destination = teleport_destination(state, actor, actor.cell)
    if destination == actor.cell:
        return False
    place_actor(state, actor, destination, TELEPORTED)
    # Direction, movement deadline and interval deliberately remain unchanged.
    resolve_immediate_hazards(state)
    return True


def trigger_message(state, cell):
    if state.status != PLAYING:
        return
    for index, message in enumerate(state.definition["messages"]):
        if message[0] == cell and not state.message_seen[index]:
            state.message_seen[index] = 1
            if state.active_message == -1:
                state.active_message = index
            else:
                state.pending_messages.append(index)
            state.paused = True


def dismiss_message(state):
    """Acknowledge explicitly; all messages triggered by a hop remain readable."""
    if state.active_message == -1:
        return False
    state.active_message = state.pending_messages.pop(0) if state.pending_messages else -1
    state.paused = state.active_message != -1
    return True

# 5. Snakes, spiders, traps, explosions --------------------------------------
def kill_player(state):
    if state.status == PLAYING and state.player.alive:
        state.player.alive = False
        state.status = DEAD
        state.step_events |= DIED
        mark_changed(state, state.player.cell, DIED)


def blocks_snake_ray(state, cell):
    if not 0 <= cell < CELL_COUNT:
        return True
    return (state.terrain[cell] in (WALL, FALSE_WALL, DIRT)
            or (state.terrain[cell] == EXIT and not state.exit_active)
            or state.objects[cell] != EMPTY or state.actor_at[cell] != -1
            or state.spear_at[cell] != -1)


def resolve_contact(state):
    cell = state.player.cell
    occupant, spear = state.actor_at[cell], state.spear_at[cell]
    if ((occupant != -1 and state.actors[occupant].kind in (SNAKE, SPIDER))
            or (spear != -1 and state.actors[spear].trap_state == EXTENDING)):
        kill_player(state)


def resolve_immediate_hazards(state):
    resolve_contact(state)
    cell = state.player.cell
    for actor in state.snakes:
        if not actor.alive:
            continue
        heading = EAST if cell % COLS >= actor.cell % COLS else WEST
        if actor.heading != heading:
            actor.heading = heading
            mark_changed(state, actor.cell, MOVED)
        if actor.cell // COLS != cell // COLS:
            continue
        target = neighbor(actor.cell, heading)
        while target != -1:
            # Player contact takes precedence over blockers at that location.
            if target == cell:
                kill_player(state)
                break
            if blocks_snake_ray(state, target):
                break
            target = neighbor(target, heading)


def spider_destination(state, actor, heading):
    """Preview the whole entry, including a blocked twin or a return to self.

    A blocked twin still permits entry onto the source pad. Even a hop back to
    the current cell is a legal move; it must not falsely trap the spider.
    """
    entered = neighbor(actor.cell, heading)
    if not can_spider_enter(state, entered, actor):
        return -1
    return teleport_destination(state, actor, entered)


def next_spider_heading(state, actor):
    """Round supported corners; otherwise seek a wall by moving straight.

    A blocked back-side diagonal supports a turn toward the following side.
    Without it, turn away from a wall ahead to put that wall on the correct
    side. Recheck current occupancy every time, including after teleporting
    or losing an obstacle; no remembered wall or movement mode is needed.
    The mover, debug preview and trapped-set test share this pure query.
    """
    side = -1 if actor.follow == FOLLOW_LEFT else 1
    side_heading = (actor.heading + side) % 4
    behind = neighbor(actor.cell, (actor.heading + 2) % 4)
    back_side = neighbor(behind, side_heading)
    if not can_spider_enter(state, back_side, actor):
        if spider_destination(state, actor, side_heading) != -1:
            return side_heading
    for turn in (0, -side, 2, side):
        heading = (actor.heading + turn) % 4
        if spider_destination(state, actor, heading) != -1:
            return heading
    return None


def resolve_moving_spider_contact(state, actor):
    """A moving spider reaches its own cell and four orthogonal neighbors.

    Check each occupied position in the move, including departure, entered pad
    and teleport arrival. Diagonal cells and opposite row edges are not adjacent.
    A stationary spider retains the ordinary same-cell contact rule.
    """
    player = state.player.cell
    distance = abs(actor.cell % COLS - player % COLS) + abs(actor.cell // COLS - player // COLS)
    if actor.alive and distance <= 1:
        kill_player(state)


def move_spiders(state):
    for actor in state.spiders:  # Stable source-map IDs; later moves see earlier ones.
        if not actor.alive or state.elapsed_ms < actor.next_due_ms:
            continue
        actor.next_due_ms += actor.interval_ms
        heading = next_spider_heading(state, actor)
        if heading is not None:
            resolve_moving_spider_contact(state, actor)
            actor.heading = heading
            place_actor(state, actor, neighbor(actor.cell, heading))
            resolve_moving_spider_contact(state, actor)
            # Proximity at the entered pad is lethal even if its twin is clear.
            teleport_actor(state, actor)
            resolve_moving_spider_contact(state, actor)


def remove_trapped_spiders(state):
    # A trapped set cannot change without an occupancy change. Late spear or
    # explosion mutations increment the version and are checked next quantum.
    if state.trapped_version == state.occupancy_version:
        return
    state.trapped_version = state.occupancy_version
    # First query every spider against ONE occupancy snapshot. Only then remove
    # the trapped set, so an earlier removal cannot free a later spider.
    for actor in state.spiders:
        if actor.alive and next_spider_heading(state, actor) is None:
            state.pending_explosions[actor.cell] = 1
    for actor in state.spiders:
        if actor.alive and state.pending_explosions[actor.cell]:
            actor.alive = False
            if state.actor_at[actor.cell] == actor.id:
                state.actor_at[actor.cell] = -1
            mark_changed(state, actor.cell, DIED)


def blocks_spear_ray(state, cell):
    # The shipped blocker sets match. Keep a separate rule entry point so a
    # student's snake-cover experiment need not change projectile behavior.
    if not 0 <= cell < CELL_COUNT:
        return True
    return (state.terrain[cell] in (WALL, FALSE_WALL, DIRT)
            or (state.terrain[cell] == EXIT and not state.exit_active)
            or state.objects[cell] != EMPTY or state.actor_at[cell] != -1
            or state.spear_at[cell] != -1)


def spear_sees_player(state, actor):
    cell = neighbor(actor.cell, actor.heading)
    while cell != -1:
        if cell == state.player.cell:
            return True
        if blocks_spear_ray(state, cell):
            return False
        cell = neighbor(cell, actor.heading)
    return False


def spear_can_extend(state, cell):
    # Test the player before occupancy, as for detection and snake rays.
    return cell != -1 and (cell == state.player.cell or not blocks_spear_ray(state, cell))


def stop_spear(state, actor):
    actor.trap_state = STOPPED
    mark_changed(state, actor.cell, EFFECT_CHANGED)
    for cell in range(CELL_COUNT):
        if state.spear_at[cell] == actor.id:
            mark_changed(state, cell, EFFECT_CHANGED)


def advance_spears(state):
    for actor in state.emitters:  # Stable trap IDs also settle crossing shafts.
        if not actor.alive:
            continue
        if actor.trap_state == IDLE:
            if state.player.alive and spear_sees_player(state, actor):
                actor.trap_state = EXTENDING
                actor.next_due_ms = state.elapsed_ms + actor.interval_ms
                mark_changed(state, actor.cell, EFFECT_CHANGED)
            continue  # Activation NEVER extends a cell in this quantum.
        if actor.trap_state != EXTENDING or state.elapsed_ms < actor.next_due_ms:
            continue
        actor.next_due_ms += actor.interval_ms
        target = neighbor(actor.tip, actor.heading)
        if not spear_can_extend(state, target):
            stop_spear(state, actor)
            continue
        mark_changed(state, actor.tip, EFFECT_CHANGED)
        actor.tip = target
        state.spear_at[target] = actor.id
        mark_changed(state, target, EFFECT_CHANGED)
        # Resolve contact before stopping; a tip hitting the player immediately
        # before a wall still kills, though the resulting shaft is harmless.
        resolve_contact(state)
        if not spear_can_extend(state, neighbor(target, actor.heading)):
            stop_spear(state, actor)


def is_explosion_destructible(state, cell):
    if not 0 <= cell < CELL_COUNT:
        return False
    types = state.definition["rules"]["explosion_destructible"]
    return ((state.objects[cell] == BOULDER and "BOULDER" in types)
            or (state.terrain[cell] == DIRT and "DIRT" in types))


def resolve_explosions(state):
    """One deduplicated cross-shaped batch: clear, damage, then eligible drops."""
    state.blast_cells[:] = state.clear_cells
    state.blast_drops[:] = state.clear_cells
    if not any(state.pending_explosions):
        return  # No environment changed; no additional snake query is needed.
    for center in range(CELL_COUNT):
        if state.pending_explosions[center]:
            state.blast_cells[center] = state.blast_drops[center] = 1
            for heading in range(4):
                cell = neighbor(center, heading)
                if cell != -1:
                    state.blast_cells[cell] = 1
            state.pending_explosions[center] = 0
    rules = state.definition["rules"]
    for cell in range(CELL_COUNT):
        if not state.blast_cells[cell]:
            continue
        if is_explosion_destructible(state, cell):
            if state.objects[cell] == BOULDER and "BOULDER" in rules["explosion_destructible"]:
                state.objects[cell] = EMPTY
                mark_changed(state, cell, OBJECT_CHANGED)
            if state.terrain[cell] == DIRT and "DIRT" in rules["explosion_destructible"]:
                state.terrain[cell], state.variants[cell] = FLOOR, 0
                mark_changed(state, cell, TERRAIN_CHANGED)
            state.blast_drops[cell] = 1
        state.blast_until[cell] = state.elapsed_ms + BLAST_MS
        mark_changed(state, cell, EFFECT_CHANGED)
    if rules["explosion_hurts_player"] and state.blast_cells[state.player.cell]:
        kill_player(state)
    if rules["explosion_diamonds"]:
        for cell in range(CELL_COUNT):
            if (state.blast_drops[cell] and state.terrain[cell] == FLOOR
                    and state.objects[cell] == EMPTY and state.actor_at[cell] == -1
                    and cell != state.player.cell and state.spear_at[cell] == -1
                    and state.definition["twins"][cell] == -1):
                state.objects[cell] = DIAMOND
                mark_changed(state, cell, OBJECT_CHANGED)
    resolve_immediate_hazards(state)


def expire_blast_art(state):
    # Three short visual frames; neither their pixels nor their lifetime collide.
    if not any(state.blast_until):
        return
    for cell in range(CELL_COUNT):
        until = state.blast_until[cell]
        if until:
            remaining = until - state.elapsed_ms
            if remaining <= 0:
                state.blast_until[cell] = 0
            if remaining <= 0 or (remaining - 1) // 60 != (remaining + UPDATE_MS - 1) // 60:
                mark_changed(state, cell, EFFECT_CHANGED)

# 6. Explicit simulation order ---------------------------------------------
def step(state, direction=None, dt_ms=UPDATE_MS):
    """One pure simulation quantum. None releases input; no clocks or I/O here.

    Event buffers describe only this quantum, including when it is frozen.
    Renderers must accumulate them before the next call.
    """
    if type(dt_ms) is not int or dt_ms != UPDATE_MS:
        raise ValueError("step requires one %s ms quantum" % UPDATE_MS)
    if direction is not None and (type(direction) is not int or direction not in range(4)):
        raise ValueError("direction must be one cardinal integer or None")
    state.step_events = 0
    state.changed_cells[:] = state.clear_cells
    state.events[:] = state.clear_cells
    if state.paused or state.status != PLAYING:
        return
    state.elapsed_ms += dt_ms
    expire_blast_art(state)
    player = state.player
    # 1. Eligible intent. Failed attempts also advance the same deadline.
    moved = False
    if player.alive and direction is not None and state.elapsed_ms >= player.next_due_ms:
        # After idle time, start a fresh interval. While held, retain the prior
        # due time so nonmultiples of 10 do not accumulate rounding drift.
        if player.next_due_ms <= state.elapsed_ms - dt_ms:
            player.next_due_ms = state.elapsed_ms
        player.next_due_ms += player.interval_ms
        # 2. Atomic movement transaction, including digging and revealing.
        moved = move_player(state, direction)
    # 3. Collect once on entry.
    if moved:
        collect_player_object(state)
    entered = player.cell if moved else -1
    # 4. Player teleportation, exactly once for this successful entry.
    if moved:
        teleport_actor(state, player)
    # 5. Immediate contact and snake exposure, including arrival occupancy.
    resolve_immediate_hazards(state)
    # 6. Due enemy movement and one-hop teleportation.
    move_spiders(state)
    # 7. Enemy/player collisions (also checked at each committed entry).
    resolve_contact(state)
    # 8. Snapshot trapped spiders, then remove together and queue explosions.
    remove_trapped_spiders(state)
    # 9. Recalculate snake exposure after enemy movement/removal.
    resolve_immediate_hazards(state)
    # 10. Activate/advance independently timed spear traps.
    advance_spears(state)
    # 11. Complete the explosion batch even after death; flush new exposure.
    resolve_explosions(state)
    # 12. Reconcile keys from authoritative occupancy.
    state.remaining_keys = state.objects.count(KEY_BYTE)
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
    # Panels freeze subsequent quanta, never interrupt a committed transaction
    # or protect the player from hazards on this entry. Source-pad hint first.
    if moved:
        trigger_message(state, entered)
        if entered != player.cell:
            trigger_message(state, player.cell)


class Session:
    """Room-local score rolls back on restart; completed rooms bank once."""
    def __init__(self, pack, start_level=0):
        self.pack, self.room_index = pack, start_level
        self.banked_score, self.room_award = 0, 0
        self.direction = None
        self.art = None
        self.renderer = None
        self.message_page = 0
        self.state = create_state(pack["levels"][start_level])

    def advance(self, updates):
        for unused in range(updates):
            step(self.state, self.direction)
            if self.renderer is not None:
                self.renderer.capture(self.state)
            if self.state.step_events & FINISHED:
                self.room_award = self.state.score + self.state.bonus
                self.banked_score += self.room_award

    def restart(self):
        # Restart after completion must not allow banking this room twice.
        self.banked_score -= self.room_award
        self.room_award = 0
        self.direction = None
        self.message_page = 0
        self.state = create_state(self.pack["levels"][self.room_index])

    def next_room(self):
        if self.state.status != COMPLETED or self.room_index + 1 >= len(self.pack["levels"]):
            return False
        self.room_index += 1
        self.room_award = 0
        self.direction = None
        self.message_page = 0
        self.state = create_state(self.pack["levels"][self.room_index])
        return True

    def total_score(self):
        return self.banked_score if self.state.status == COMPLETED else self.banked_score + self.state.score


def validate_playable_pack(pack):
    """All version-1 validated room mechanics are now playable.

    Retain this entry point for trusted tools and student copies. Structural
    validation belongs to validate_level_pack, before state/art acquisition.
    """
    return pack

# 7. Art preparation, layout, rendering, debug -------------------------------
HUD_HEIGHT, PANEL_WIDTH, PANEL_HEIGHT, CONTROL_SIZE = 24, 112, 112, 32
# Atlas indices are app data: an 8x8 sheet of original 16x16 cells. False walls
# intentionally use the SAME sprite as their matching wall, with no overlay.
ART_FLOOR, ART_WALL, ART_DIRT = 0, 1, 11
ART_KEY, ART_DIAMOND, ART_BOULDER = 21, 22, 23
ART_EXIT_LOCKED, ART_EXIT_OPEN, ART_PLAYER = 24, 25, 26
ART_SNAKE_WEST, ART_SNAKE_EAST, ART_SPIDER, ART_EMITTER = 30, 31, 32, 36
ART_WATER = (40, 41, 42, 48, 49, 50, 56, 57, 58)
ART_SPEAR_TIP, ART_PAD, ART_SHAFT, ART_BLAST = 43, 47, 51, 53


def terrain_art(terrain, variant, exit_active):
    if terrain in (WALL, FALSE_WALL):
        return ART_WALL + variant
    if terrain == DIRT:
        return ART_DIRT + variant
    if terrain == WATER:
        return ART_WATER[variant]
    if terrain == EXIT:
        return ART_EXIT_OPEN if exit_active else ART_EXIT_LOCKED
    return ART_FLOOR


class PuzzleArt:
    """Prepare only the active room's sprites in one decoder pass, then release it.

    Restart reuses this cache. Room changes replace it rather than accumulating
    every room's prepared spans. No second board framebuffer is allocated.
    """
    def __init__(self, path, scale):
        self.path, self.scale = path, scale
        self.sprites = {}
        self.prepared = {}
        self.canvas = None
        self.key = 0

    def prepare(self, definition, canvas=None):
        needed = {ART_FLOOR, ART_EXIT_LOCKED, ART_EXIT_OPEN}
        for terrain, variant in zip(definition["terrain"], definition["variants"]):
            needed.add(terrain_art(terrain, variant, False))
        for obj in definition["objects"]:
            if obj != EMPTY:
                needed.add(ART_KEY + obj - 1)
        for kind, cell, heading, follow, interval in definition["actors"]:
            if kind == PLAYER:
                needed.update(range(ART_PLAYER, ART_PLAYER + 4))
            elif kind == SNAKE:
                needed.update((ART_SNAKE_WEST, ART_SNAKE_EAST))
            elif kind == SPIDER:
                needed.update(range(ART_SPIDER, ART_SPIDER + 4))
                needed.update(range(ART_BLAST, ART_BLAST + 3))
                if definition["rules"]["explosion_diamonds"]:
                    needed.add(ART_DIAMOND)
            elif kind == EMITTER:
                needed.add(ART_EMITTER + heading)
                needed.add(ART_SPEAR_TIP + heading)
                needed.add(ART_SHAFT + heading % 2)
        if needed == set(self.sprites) and canvas is self.canvas:
            return
        self.close()
        from tartlabutils.sprites import SpriteSheet
        try:
            sheet = SpriteSheet(self.path)
            if (sheet.width, sheet.height) != (128, 128):
                raise ValueError("expected an 8x8 atlas of 16x16 cells")
            indices = sorted(needed)
            crops = [(index % 8 * TILE_SIZE, index // 8 * TILE_SIZE,
                      TILE_SIZE, TILE_SIZE) for index in indices]
            prepared = sheet.sprites(crops, scale=self.scale)
            self.sprites = dict(zip(indices, prepared))
            if canvas is not None and hasattr(canvas, "prepare_sprite"):
                # One native blit per tile replaces hundreds of Python span
                # calls. Keep transparent pixels; never bake floor under actors.
                from framebuf import FrameBuffer, RGB565
                colors = {sprite.spans[i] for sprite in prepared
                          for i in range(3, len(sprite.spans), 4)}
                self.key = 0
                while self.key in colors:
                    self.key += 1
                for index, sprite in zip(indices, prepared):
                    buffer = bytearray(sprite.width * sprite.height * 2)
                    tile = FrameBuffer(buffer, sprite.width, sprite.height, RGB565)
                    tile.fill(self.key)
                    sprite.draw(tile, 0, 0, (0, 0, sprite.width, sprite.height))
                    self.prepared[index] = canvas.prepare_sprite(tile, sprite.width, sprite.height)
            self.canvas = canvas
            # SpriteSheet owns an in-memory decoder; its extraction closes the
            # row iterator. Keep only prepared spans, not the decoder or file.
        except (OSError, ValueError) as error:
            raise ValueError("Asset file %s: %s" % (self.path, error))

    def draw(self, canvas, index, x, y, clip):
        if canvas is self.canvas and index in self.prepared:
            left, top, width, height = clip
            size = TILE_SIZE * self.scale
            if left <= x and top <= y and x + size <= left + width and y + size <= top + height:
                canvas.draw_sprite(self.prepared[index], x, y, self.key)
                return
        self.sprites[index].draw(canvas, x, y, clip)

    def close(self):
        self.sprites.clear()
        self.prepared.clear()
        self.canvas = None


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
        self.controls.append(("debug", (pad_x + CONTROL_SIZE, pad_y + CONTROL_SIZE,
                                        CONTROL_SIZE, CONTROL_SIZE)))
        self.controls.extend((("restart", (action_x, action_y, 56, 32)),
                              ("pause", (action_x + 56, action_y, 56, 32)),
                              ("back", (action_x, action_y + 36, 56, 32)),
                              ("step", (action_x + 56, action_y + 36, 56, 32))))

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


def draw_board(canvas, state, layout, art, debug=False, cells=None):
    """Full reference renderer: terrain, objects, actors, effects, inspection."""
    bx, by, unused_w, unused_h = layout.board
    size = layout.tile_size
    for cell in range(CELL_COUNT):
        if cells is not None and not cells[cell]:
            continue
        x, y = bx + (cell % COLS) * size, by + (cell // COLS) * size
        terrain = state.terrain[cell]
        if terrain == EXIT:
            art.draw(canvas, ART_FLOOR, x, y, layout.board)
        art.draw(canvas, terrain_art(terrain, state.variants[cell], state.exit_active), x, y, layout.board)
    for cell in range(CELL_COUNT):
        if cells is not None and not cells[cell]:
            continue
        obj = state.objects[cell]
        if obj != EMPTY:
            x, y = bx + (cell % COLS) * size, by + (cell // COLS) * size
            art.draw(canvas, ART_KEY + obj - 1, x, y, layout.board)
    for actor in state.actors:
        if cells is not None and not cells[actor.cell]:
            continue
        if not actor.alive and actor.kind != PLAYER:
            continue
        if actor.kind == SNAKE:
            index = ART_SNAKE_EAST if actor.heading == EAST else ART_SNAKE_WEST
        else:
            base = ART_PLAYER if actor.kind == PLAYER else (ART_SPIDER if actor.kind == SPIDER else ART_EMITTER)
            index = base + actor.heading
        x, y = bx + (actor.cell % COLS) * size, by + (actor.cell // COLS) * size
        art.draw(canvas, index, x, y, layout.board)
    for cell in range(CELL_COUNT):
        if cells is not None and not cells[cell]:
            continue
        x, y = bx + (cell % COLS) * size, by + (cell // COLS) * size
        spear_id = state.spear_at[cell]
        if spear_id != -1:
            actor = state.actors[spear_id]
            index = (ART_SPEAR_TIP + actor.heading if cell == actor.tip else
                     ART_SHAFT + actor.heading % 2)
            art.draw(canvas, index, x, y, layout.board)
        if state.blast_until[cell] > state.elapsed_ms:
            frame = min(2, (BLAST_MS - (state.blast_until[cell] - state.elapsed_ms)) // 60)
            art.draw(canvas, ART_BLAST + frame, x, y, layout.board)
    if debug:
        inspector = debug if isinstance(debug, Inspector) else Inspector(state)
        inspector.draw(canvas, state, layout)


def message_lines(text, columns):
    """Wrap all text, including long words, without losing later hint pages."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + len(word) + 1 > columns:
            lines.append(line)
            line = ""
        while len(word) > columns:
            lines.append(word[:columns])
            word = word[columns:]
        if word:
            line = line + " " + word if line else word
    if line:
        lines.append(line)
    return lines


def message_content(state, layout):
    text = state.definition["messages"][state.active_message][1]
    return message_lines(text, (layout.board[2] - 24) // 8), (layout.board[3] - 52) // 12


def acknowledge_message(session, layout):
    lines, count = message_content(session.state, layout)
    if (session.message_page + 1) * count < len(lines):
        session.message_page += 1
    else:
        dismiss_message(session.state)
        session.message_page = 0


def draw_game(canvas, session, layout, last_action=None, debug=False):
    """The loop's presentation entry point; tools can call draw_full_game too."""
    if session.renderer is not None:
        session.renderer.present(session, last_action)
    else:
        draw_full_game(canvas, session, layout, last_action, debug)


def draw_full_game(canvas, session, layout, last_action=None, debug=False):
    """Reference image; dirty rendering must produce these same pixels."""
    canvas.fill(0)
    draw_board(canvas, session.state, layout, session.art, debug)
    draw_ui(canvas, session, layout, last_action, debug)
    canvas.show()


def draw_ui(canvas, session, layout, last_action=None, debug=False):
    state = session.state
    title = "%s/%s %s" % (session.room_index + 1, len(session.pack["levels"]), state.definition["name"])
    canvas.text(title[:layout.width // 8], 0, 0, 0xFFFF)
    status = "PAUSED" if state.paused else ("PLAY", "DEAD", "DONE")[state.status]
    hud = "K%s S%s B%s %s" % (state.remaining_keys, session.total_score(), state.bonus, status)
    canvas.text(hud[:layout.width // 8], 0, 12, 0xFFFF)
    rx, ry = layout.readout
    canvas.text("Exit open" if state.exit_active else "Exit locked", rx, ry, 0xFFFF)
    pause_label = "Play" if state.paused else "Pause"
    if state.active_message != -1:
        lines, count = message_content(state, layout)
        first = session.message_page * count
        pause_label = "More" if first + count < len(lines) else "OK"
        bx, by, bw, bh = layout.board
        canvas.rect(bx + 4, by + 4, bw - 8, bh - 8, 0, True)
        canvas.rect(bx + 4, by + 4, bw - 8, bh - 8, 0xFFFF)
        caption = "HINT %s/%s (PAUSED)" % (session.message_page + 1, (len(lines) + count - 1) // count)
        canvas.text(caption, bx + 12, by + 12, 0xFFE0)
        for row, line in enumerate(lines[first:first + count]):
            canvas.text(line, bx + 12, by + 30 + row * 12, 0xFFFF)
        canvas.text("Pause button: " + pause_label, bx + 12, by + bh - 18, 0xFFFF)
    if state.status == COMPLETED:
        pause_label = "Next" if session.room_index + 1 < len(session.pack["levels"]) else "Done"
    labels = {"north": "^", "east": ">", "south": "v", "west": "<",
              "restart": "Reset", "pause": pause_label, "back": "Back",
              "debug": "DBG", "step": "Step" if debug and state.paused else "-"}
    for action, (x, y, width, height) in layout.controls:
        canvas.rect(x, y, width, height, 0xFFFF)
        if action == last_action:
            canvas.rect(x + 2, y + 2, width - 4, height - 4, 0xFFFF)
        canvas.text(labels[action], x + 4, y + 12, 0xFFFF)


def ray_preview(state, actor):
    """Read the hazard's actual blocker query, testing the player before cover."""
    if actor.kind == EMITTER and actor.trap_state == STOPPED:
        return (), -1
    blocks = blocks_snake_ray if actor.kind == SNAKE else blocks_spear_ray
    origin = actor.tip if actor.kind == EMITTER and actor.trap_state == EXTENDING else actor.cell
    cell, cells = neighbor(origin, actor.heading), []
    while cell != -1:
        if cell == state.player.cell:
            cells.append(cell)
            return cells, cell
        if blocks(state, cell):
            return cells, cell
        cells.append(cell)
        cell = neighbor(cell, actor.heading)
    return cells, -1


class Inspector:
    """Optional bounded trails. Tap a paused cell again to page its readout."""
    TRAIL_LENGTH = 12

    def __init__(self, state):
        self.selected, self.page = state.player.cell, 0
        self.direction = None
        self.missed, self.dropped = 0, 0
        self.trails = {actor.id: [actor.cell] for actor in state.actors if actor.kind == SPIDER}

    def observe(self, state):
        for actor in state.actors:
            trail = self.trails.get(actor.id)
            if trail is not None and actor.alive and trail[-1] != actor.cell:
                if len(trail) == self.TRAIL_LENGTH:
                    del trail[0]
                trail.append(actor.cell)

    def select(self, cell):
        self.page = self.page + 1 if cell == self.selected else 0
        self.selected = cell

    def lines(self, state, columns):
        cell = self.selected
        details = [inspect_cell(state, cell), "Step direction: " +
                   ("idle" if self.direction is None else "NESW"[self.direction]),
                   "Level file: " + LEVEL_FILE,
                   "Keys %s missed %s dropped %sms" %
                   (state.remaining_keys, self.missed, self.dropped),
                   "Player enter %s; boulder %s" %
                   (can_player_enter(state, cell), accepts_boulder(state, cell)),
                   "Snake block %s; spear block %s" %
                   (blocks_snake_ray(state, cell), blocks_spear_ray(state, cell))]
        for actor in state.actors:
            if actor.cell == cell or state.spear_at[cell] == actor.id:
                details.append("%s #%s %s due %s now %s" %
                               (ACTOR_NAMES[actor.kind], actor.id, "NESW"[actor.heading],
                                actor.next_due_ms, state.elapsed_ms))
                if actor.kind == SPIDER:
                    heading = next_spider_heading(state, actor) if actor.alive else None
                    details.append("Follow %s next %s" %
                                   ("L" if actor.follow == FOLLOW_LEFT else "R",
                                    "trapped" if heading is None else "NESW"[heading]))
        lines = []
        for detail in details:
            lines.extend(message_lines(detail, columns))
        return lines

    def draw(self, canvas, state, layout):
        bx, by, bw, bh = layout.board
        size = layout.tile_size
        def center(cell):
            return bx + cell % COLS * size + size // 2, by + cell // COLS * size + size // 2
        for x in range(COLS):
            canvas.line(bx + x * size, by, bx + x * size, by + bh - 1, 0x4208)
            canvas.text(str(x), bx + x * size, by, 0xFFFF)
        for y in range(ROWS):
            canvas.line(bx, by + y * size, bx + bw - 1, by + y * size, 0x4208)
            canvas.text(str(y), bx, by + y * size, 0xFFFF)
        for cell in range(CELL_COUNT):
            x, y = bx + cell % COLS * size, by + cell // COLS * size
            if state.terrain[cell] == FALSE_WALL:
                canvas.rect(x + 1, y + 1, size - 2, size - 2, 0xFFE0)
            twin = state.definition["twins"][cell]
            if twin != -1:
                if cell < twin:  # One undirected line per pair.
                    x1, y1 = center(cell)
                    x2, y2 = center(twin)
                    canvas.line(x1, y1, x2, y2, 0x07FF)
                canvas.text("T%s" % state.definition["labels"][cell], x, y, 0x07FF)
        for actor in state.actors:
            if not actor.alive or actor.kind == PLAYER:
                continue
            x, y = center(actor.cell)
            dx, dy = DIRECTIONS[actor.heading]
            ex, ey = x + dx * (size // 2 - 2), y + dy * (size // 2 - 2)
            canvas.line(x, y, ex, ey, 0xFFFF)
            canvas.line(ex, ey, ex - dx * 3 + dy * 2, ey - dy * 3 - dx * 2, 0xFFFF)
            canvas.line(ex, ey, ex - dx * 3 - dy * 2, ey - dy * 3 + dx * 2, 0xFFFF)
            if actor.kind == SPIDER:
                canvas.text("L" if actor.follow == FOLLOW_LEFT else "R", x - size // 2, y, 0xFFE0)
                for visited in self.trails.get(actor.id, ()):
                    vx, vy = center(visited)
                    canvas.rect(vx - 1, vy - 1, 3, 3, 0x07FF, True)
                heading = next_spider_heading(state, actor)
                if heading is not None:
                    destination = spider_destination(state, actor, heading)
                    tx, ty = center(destination)
                    canvas.rect(tx - 3, ty - 3, 7, 7, 0x07E0)
            elif actor.kind in (SNAKE, EMITTER):
                cells, blocker = ray_preview(state, actor)
                for target in cells:
                    tx, ty = center(target)
                    canvas.rect(tx - 1, ty - 1, 3, 3, 0xF800, True)
                if blocker != -1:
                    tx, ty = center(blocker)
                    canvas.rect(tx - 4, ty - 4, 9, 9, 0xF800)
        x, y = center(self.selected)
        canvas.rect(x - size // 2, y - size // 2, size, size, 0xFFFF)
        if state.paused and state.active_message == -1:
            lines = self.lines(state, (bw - 16) // 8)
            count = 5
            pages = (len(lines) + count - 1) // count
            page = self.page % pages
            top = by + bh - 84
            canvas.rect(bx + 2, top, bw - 4, 82, 0, True)
            canvas.text("CELL %s,%s %s/%s (tap again)" %
                        (self.selected % COLS, self.selected // COLS, page + 1, pages),
                        bx + 8, top + 4, 0xFFE0)
            for row, line in enumerate(lines[page * count:(page + 1) * count]):
                canvas.text(line, bx + 8, top + 18 + row * 12, 0xFFFF)


def debug_step(session, direction=None):
    """Advance exactly one normal quantum, retaining an explicit user pause."""
    state = session.state
    if not state.paused or state.status != PLAYING or state.active_message != -1:
        return False
    state.paused = False
    session.direction = direction
    try:
        session.advance(1)
    finally:
        state.paused = True
        session.direction = None
    return True


class Renderer:
    """Accumulate every quantum; compose layers before one flush coordinator.

    Sparse frames rebuild changed cells. Debug uses the full reference because
    rays, links and trails cross clean cells. Dense damage and panel transitions
    also use it. No board framebuffer or sprite cache is duplicated.
    """
    def __init__(self, canvas, layout, debug=False):
        from tartlabutils.damage import DamageTracker
        import time
        self.canvas, self.layout = canvas, layout
        self.damage = DamageTracker((0, 0, layout.width, layout.height))
        rx, ry = layout.readout
        self.ui_regions = [(0, 0, layout.width, HUD_HEIGHT),
                           (rx, ry, min(112, layout.width - rx), 8)]
        self.ui_regions.extend(area for action, area in layout.controls)
        self.cells = bytearray(CELL_COUNT)
        self.state, self.ui_key = None, None
        self.debug, self.inspector = debug, None
        self.full = True
        self.ticks = getattr(time, "ticks_us", None)
        if self.ticks is None:
            self.ticks = lambda: int(time.monotonic() * 1000000)
        self.diff = getattr(time, "ticks_diff", lambda new, old: new - old)
        self.draw_us, self.transfer_us, self.dirty_count = 0, 0, 0

    def bind(self, state):
        if state is not self.state:
            self.state, self.full = state, True
            self.inspector = Inspector(state) if self.debug else None
            for cell in range(CELL_COUNT):
                self.cells[cell] = 0

    def toggle_debug(self, state):
        self.debug = not self.debug
        self.inspector = Inspector(state) if self.debug else None
        self.full = True

    def capture(self, state):
        self.bind(state)
        cell = state.changed_cells.find(b"\x01")
        while cell != -1:
            self.cells[cell] = 1
            cell = state.changed_cells.find(b"\x01", cell + 1)
        if self.inspector is not None:
            self.inspector.observe(state)

    def present(self, session, last_action=None):
        started = self.ticks()
        state, layout, canvas = session.state, self.layout, self.canvas
        self.bind(state)
        self.damage.clear()
        self.dirty_count = sum(self.cells)
        ui_key = (state.remaining_keys, session.total_score(), state.bonus,
                  state.status, state.paused, state.active_message,
                  session.message_page, last_action, self.debug)
        panel_changed = self.ui_key is not None and ui_key[5:7] != self.ui_key[5:7]
        full = self.full or self.debug or panel_changed or self.dirty_count >= CELL_COUNT // 3
        if full:
            if self.ui_key is None:
                canvas.fill(0)
            draw_board(canvas, state, layout, session.art, self.inspector or False)
            if ui_key != self.ui_key:
                for area in self.ui_regions:
                    canvas.rect(area[0], area[1], area[2], area[3], 0, True)
            if ui_key != self.ui_key or state.active_message != -1:
                draw_ui(canvas, session, layout, last_action, self.debug)
            if self.ui_key is None:
                self.damage.mark(0, 0, layout.width, layout.height)
            else:
                self.damage.add(layout.board)
                if ui_key != self.ui_key:
                    for area in self.ui_regions:
                        self.damage.add(area)
        else:
            if self.dirty_count:
                draw_board(canvas, state, layout, session.art, cells=self.cells)
            bx, by, bw, bh = layout.board
            size = layout.tile_size
            for cell in range(CELL_COUNT):
                if self.cells[cell]:
                    self.damage.mark(bx + cell % COLS * size, by + cell // COLS * size, size, size)
            if ui_key != self.ui_key:
                for area in self.ui_regions:
                    canvas.rect(area[0], area[1], area[2], area[3], 0, True)
                    self.damage.add(area)
                draw_ui(canvas, session, layout, last_action, False)
        self.draw_us = self.diff(self.ticks(), started)
        started = self.ticks()
        for index in range(self.damage.count):
            canvas.show(self.damage.area(index))
        self.transfer_us = self.diff(self.ticks(), started)
        self.full, self.ui_key = False, ui_key
        self.cells[:] = state.clear_cells

    def close(self):
        self.inspector = self.state = None
        self.damage.clear()


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
            mapped = name if name in ("debug", "step") else BUTTON_ACTIONS.get(name)
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
    session.art = PuzzleArt(ASSET_FILE, layout.scale)
    clock = None
    missed, dropped, wake_polls = 0, 0, 0
    print("Directions move; Reset restarts; Pause/Play freezes/resumes; Next advances; Back returns to UI.")
    print(inspect_cell(session.state, session.state.player.cell))
    try:
        session.art.prepare(session.state.definition, canvas)
        session.renderer = Renderer(canvas, layout, debug)
        session.renderer.bind(session.state)
        session.renderer.present(session)
        clock = clock_factory()  # Loading art is startup, not elapsed play time.
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
            elif action == "debug":
                session.renderer.toggle_debug(session.state)
            elif action == "step" and session.renderer.debug:
                rebase = debug_step(session, session.renderer.inspector.direction)
            elif action == "pause":
                if session.state.status == COMPLETED:
                    rebase = session.next_room()
                elif session.state.status == PLAYING:
                    if session.state.active_message != -1:
                        acknowledge_message(session, layout)
                    else:
                        session.state.paused = not session.state.paused
                    rebase = True
            if rebase:
                session.art.prepare(session.state.definition, canvas)
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
                was_paused = session.state.paused
                session.advance(updates)
                if ((was_playing and session.state.status != PLAYING)
                        or (not was_paused and session.state.paused)):
                    controls.reset()
                session.direction = controls.direction() if not session.state.paused else None
            if controls.fresh_touch and point is not None:
                selected = layout.cell_from_point(*point)
                if selected != -1:
                    print(inspect_cell(session.state, selected))
                    if session.renderer.inspector is not None:
                        session.renderer.inspector.select(selected)
            inspector = session.renderer.inspector
            if inspector is not None:
                if session.state.paused and controls.direction() is not None:
                    inspector.direction = controls.direction()
                inspector.missed = missed + clock.missed_deadlines
                inspector.dropped = dropped + clock.dropped_update_ms
            draw_game(canvas, session, layout, action, session.renderer.debug)
            if rebase:
                clock = clock_factory()  # Restart/hint transition drawing is paused time.
            clock.pace()
    finally:
        session.art.close()
        if session.renderer is not None:
            session.renderer.close()
        if clock is not None:
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
        canvas = DirectCanvas(game_surface(), rotation=layout.rotation,
                              transfer_rows=CANVAS_TRANSFER_ROWS)
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
