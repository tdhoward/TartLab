"""A portrait touch racer with display-independent simulation state."""

from random import choice, randint

from tartlabutils.damage import DamageTracker
from tartlabutils.motion import StagedMotion
from tartlabutils.timing import FrameClock


MILLIUNITS_PER_PIXEL = 1000

TARGET_FRAME_MS = 50
SIMULATION_STEP_MS = 50
MAX_UPDATES_PER_FRAME = 2
SCROLL_QUANTUM = 4
CENTER_PERIOD = 48
CENTER_RADIUS = 3
CAR_SPRITE_SCALE = 2
COW_SPRITE_SCALE = 2
CAR_RADIUS = 11 * CAR_SPRITE_SCALE
STEER_STEP = 18
OBSTACLE_GAP = 92
SCANOUT_MIN_ROAD_ENTITIES = 3
ROAD_SPEED_STAGES = (
    (0, 64),
    (1200, 80),
    (2800, 96),
    (5200, 112),
    (8400, 128),
)
# Keep the 95th-percentile mixed-sprite frame within two simulation steps.
MAX_ROAD_ENTITIES = 4
# Elapsed racing time, maximum road objects (coins included), spawn gap.
DIFFICULTY_STAGES = (
    (0, 2, 220),
    (20000, 3, 160),
    (45000, MAX_ROAD_ENTITIES, 120),
    (70000, MAX_ROAD_ENTITIES, 96),
    (100000, MAX_ROAD_ENTITIES, 80),
)
RODENT_START_MS = 45000
CHICKEN_START_MS = 100000
RODENT_SPEED = 48


class CircleCollision:
    """Describe a circular collision shape in logical pixels."""

    __slots__ = ("radius",)

    def __init__(self, radius):
        self.radius = int(radius)
        if self.radius < 0:
            raise ValueError("collision radius must not be negative")


class EntityKind:
    """Describe one visual and its player-contact behavior."""

    __slots__ = ("name", "visual", "visual_radius", "collision",
                 "draw_layer", "contact_handler")

    def __init__(self, name, visual, visual_radius, collision_radius,
                 contact_handler=None, draw_layer=0):
        self.name = name
        self.visual = visual
        self.visual_radius = int(visual_radius)
        if self.visual_radius < 0:
            raise ValueError("visual radius must not be negative")
        self.collision = CircleCollision(collision_radius)
        self.draw_layer = int(draw_layer)
        self.contact_handler = contact_handler


def bounce_at_road_edge(entity, left, right):
    """Reflect a horizontally moving entity back inside the road."""
    radius = entity.kind.visual_radius
    minimum = (left + radius) * MILLIUNITS_PER_PIXEL
    maximum = (right - radius - 1) * MILLIUNITS_PER_PIXEL
    if maximum <= minimum:
        entity.x_milli = minimum
        entity.horizontal_velocity = 0
        return

    while entity.x_milli < minimum or entity.x_milli > maximum:
        if entity.x_milli < minimum:
            entity.x_milli = minimum + (minimum - entity.x_milli)
            entity.horizontal_velocity = abs(entity.horizontal_velocity)
        elif entity.x_milli > maximum:
            entity.x_milli = maximum - (entity.x_milli - maximum)
            entity.horizontal_velocity = -abs(entity.horizontal_velocity)


def wrap_at_road_edge(entity, left, right):
    """Wrap a horizontally moving entity to the opposite road edge."""
    radius = entity.kind.visual_radius
    minimum = (left + radius) * MILLIUNITS_PER_PIXEL
    maximum = (right - radius - 1) * MILLIUNITS_PER_PIXEL
    span = maximum - minimum
    if span <= 0:
        entity.x_milli = minimum
        entity.horizontal_velocity = 0
    elif entity.x_milli < minimum or entity.x_milli > maximum:
        entity.x_milli = minimum + (entity.x_milli - minimum) % span


def deactivate_at_road_edge(entity, left, right):
    """Deactivate an entity whose visible shape leaves the road."""
    radius = entity.kind.visual_radius
    if (entity.x_milli <
            (left + radius) * MILLIUNITS_PER_PIXEL or
            entity.x_milli >
            (right - radius - 1) * MILLIUNITS_PER_PIXEL):
        entity.active = False


class Entity:
    """Hold the simulation state for one lightweight road object."""

    __slots__ = (
        "kind", "x_milli", "y_milli", "previous_bounds",
        "current_bounds", "frame_bounds", "horizontal_velocity",
        "road_relative", "boundary_policy", "active", "contacted",
        "visible_before_frame")

    def __init__(self, kind, x, y, horizontal_velocity=0,
                 road_relative=True, boundary_policy=bounce_at_road_edge):
        self.kind = kind
        self.x_milli = int(x) * MILLIUNITS_PER_PIXEL
        self.y_milli = int(y) * MILLIUNITS_PER_PIXEL
        self.horizontal_velocity = int(horizontal_velocity)
        self.road_relative = bool(road_relative)
        self.boundary_policy = boundary_policy
        self.active = True
        self.contacted = False
        self.current_bounds = self._visible_bounds()
        self.previous_bounds = self.current_bounds
        self.frame_bounds = self.current_bounds
        self.visible_before_frame = True

    @property
    def x(self):
        return self.x_milli // MILLIUNITS_PER_PIXEL

    @property
    def y(self):
        return self.y_milli // MILLIUNITS_PER_PIXEL

    def _visible_bounds(self):
        radius = self.kind.visual_radius
        return (
            self.x - radius,
            self.y - radius,
            radius * 2 + 1,
            radius * 2 + 1,
        )

    def advance(self, elapsed_ms, road_delta, road_left, road_right):
        """Advance position without drawing or presenting any pixels."""
        self.previous_bounds = self.current_bounds
        self.x_milli += self.horizontal_velocity * int(elapsed_ms)
        if self.road_relative:
            self.y_milli += int(road_delta) * MILLIUNITS_PER_PIXEL
        if self.boundary_policy is not None:
            self.boundary_policy(self, road_left, road_right)
        self.current_bounds = self._visible_bounds()


class CrossingAnimal(Entity):
    """Cross steadily as a capybara or roam inside the road as a chicken."""

    __slots__ = ("direction", "decision_ms", "_randint",
                 "previous_direction", "frame_direction")

    def __init__(self, kind, x, y, direction, randint_source=randint,
                 speed=RODENT_SPEED):
        self.direction = direction
        self.previous_direction = direction
        self.frame_direction = direction
        self.decision_ms = 0
        self._randint = randint_source
        speed = 96 if kind.name == "chicken" else int(speed)
        super().__init__(kind, x, y, direction * speed,
                         road_relative=True,
                         boundary_policy=(bounce_at_road_edge if kind.name == "chicken"
                                          else deactivate_at_road_edge))

    def advance(self, elapsed_ms, road_delta, road_left, road_right):
        self.previous_direction = self.direction
        if self.kind.name != "chicken":
            return super().advance(elapsed_ms, road_delta, road_left, road_right)
        self.previous_bounds = self.current_bounds
        remaining = int(elapsed_ms)
        while remaining > 0:
            if self.decision_ms <= 0:
                self.decision_ms = self._randint(200, 650)
                action = self._randint(0, 4)
                if action == 0:
                    self.horizontal_velocity = 0
                else:
                    self.direction = -1 if action <= 2 else 1
                    self.horizontal_velocity = self.direction * self._randint(48, 120)
            step = min(remaining, self.decision_ms)
            self.x_milli += self.horizontal_velocity * step
            # Reflect each burst separately so decisions are independent of FPS.
            self.boundary_policy(self, road_left, road_right)
            if self.horizontal_velocity:
                self.direction = 1 if self.horizontal_velocity > 0 else -1
            remaining -= step
            self.decision_ms -= step
        self.y_milli += int(road_delta) * MILLIUNITS_PER_PIXEL
        self.current_bounds = self._visible_bounds()


class InteractionEvent:
    """Record one player contact for later presentation or feedback."""

    __slots__ = ("event_type", "entity")

    def __init__(self, event_type, entity):
        self.event_type = event_type
        self.entity = entity


def collect_on_contact(game, entity):
    """Award one gold coin and remove it from the road."""
    game.score += 1
    entity.active = False
    return "collectible"


def crash_on_contact(game, entity):
    """Stop the race until the player releases and taps to restart."""
    game.crashed = True
    return "hazard"


class RoadState:
    """Own authoritative road distance and visual centerline phase."""

    __slots__ = ("motion", "center_period", "center_phase")

    def __init__(self, speed_stages=ROAD_SPEED_STAGES,
                 quantum=SCROLL_QUANTUM, center_period=CENTER_PERIOD):
        self.motion = StagedMotion(speed_stages, quantum)
        self.center_period = int(center_period)
        if self.center_period <= 0:
            raise ValueError("center period must be positive")
        self.center_phase = 0

    @property
    def distance(self):
        return self.motion.distance

    @property
    def speed_per_second(self):
        return self.motion.speed_per_second

    def advance(self, elapsed_ms):
        delta = self.motion.advance(elapsed_ms)
        self.center_phase = (
            self.center_phase + delta) % self.center_period
        return delta


class GameState:
    """Own Racer simulation, spawning, contacts, and entity lifecycle."""

    __slots__ = (
        "road", "road_left", "road_right", "track_top", "track_bottom",
        "player_x", "player_y", "player_radius", "entities",
        "interactions", "spawned_entities", "removed_entities",
        "entity_kinds", "spawn_gap", "next_spawn_distance", "score",
        "crashed", "_randint", "_choice")

    def __init__(self, road, road_left, road_right, track_top, track_bottom,
                 player_x, player_y, player_radius, entity_kinds=(),
                 spawn_gap=OBSTACLE_GAP, randint_source=randint,
                 choice_source=choice):
        self.road = road
        self.road_left = int(road_left)
        self.road_right = int(road_right)
        self.track_top = int(track_top)
        self.track_bottom = int(track_bottom)
        self.player_x = int(player_x)
        self.player_y = int(player_y)
        self.player_radius = int(player_radius)
        self.entities = []
        self.interactions = []
        self.spawned_entities = []
        self.removed_entities = []
        self.entity_kinds = tuple(entity_kinds)
        self.spawn_gap = int(spawn_gap)
        if self.spawn_gap <= 0:
            raise ValueError("spawn gap must be positive")
        self.next_spawn_distance = self.spawn_gap
        self.score = 0
        self.crashed = False
        self._randint = randint_source
        self._choice = choice_source

    def begin_frame(self):
        """Clear transient records before one or more fixed updates."""
        self.interactions.clear()
        self.spawned_entities.clear()
        self.removed_entities.clear()
        for entity in self.entities:
            entity.frame_bounds = entity.current_bounds
            entity.visible_before_frame = entity.active
            if isinstance(entity, CrossingAnimal):
                entity.frame_direction = entity.direction

    def move_player(self, direction):
        """Move the player one steering step while keeping it on the road."""
        minimum = self.road_left + self.player_radius + 2
        maximum = self.road_right - self.player_radius - 3
        self.player_x = max(minimum, min(maximum, self.player_x + direction))

    def add_entity(self, entity, spawned=False):
        index = len(self.entities)
        while (index and self.entities[index - 1].kind.draw_layer >
               entity.kind.draw_layer):
            index -= 1
        self.entities.insert(index, entity)
        if spawned:
            entity.visible_before_frame = False
            self.spawned_entities.append(entity)
        return entity

    def spawn_entity(self, kind=None, y=None, horizontal_velocity=0,
                     road_relative=True,
                     boundary_policy=bounce_at_road_edge):
        """Create an entity using injected random sources, without drawing."""
        if kind is None:
            if not self.entity_kinds:
                return None
            kind = self._choice(self.entity_kinds)
        radius = kind.visual_radius
        x = self._randint(
            self.road_left + radius + 3,
            self.road_right - radius - 4)
        if y is None:
            y = self.track_top + radius
        return self.add_entity(Entity(
            kind, x, y, horizontal_velocity,
            road_relative, boundary_policy), spawned=True)

    def _touches_player(self, entity):
        collision = entity.kind.collision
        dx = (entity.x_milli -
              self.player_x * MILLIUNITS_PER_PIXEL)
        dy = (entity.y_milli -
              self.player_y * MILLIUNITS_PER_PIXEL)
        radius = ((collision.radius + self.player_radius) *
                  MILLIUNITS_PER_PIXEL)
        return dx * dx + dy * dy <= radius * radius

    def _resolve_player_contacts(self):
        for entity in self.entities:
            handler = entity.kind.contact_handler
            if (entity.active and not entity.contacted and
                    handler is not None and self._touches_player(entity)):
                entity.contacted = True
                event_type = handler(self, entity)
                if event_type is not None:
                    self.interactions.append(
                        InteractionEvent(event_type, entity))

    def _cull_entities(self):
        for entity in self.entities:
            if not entity.active:
                continue
            radius = entity.kind.visual_radius
            if (entity.y - radius >= self.track_bottom or
                    entity.y + radius < self.track_top):
                entity.active = False

    def compact_entities(self):
        """Remove inactive entries in place without replacing the list."""
        write_index = 0
        for entity in self.entities:
            if entity.active:
                self.entities[write_index] = entity
                write_index += 1
            else:
                self.removed_entities.append(entity)
        if write_index < len(self.entities):
            del self.entities[write_index:]

    def step(self, elapsed_ms):
        """Run one fixed simulation update and return road screen movement."""
        if self.crashed:
            return 0
        road_delta = self.road.advance(elapsed_ms)
        for entity in self.entities:
            if entity.active:
                entity.advance(
                    elapsed_ms, road_delta, self.road_left, self.road_right)

        self._resolve_player_contacts()
        self._cull_entities()
        self.compact_entities()

        while (self.entity_kinds and
               self.road.distance >= self.next_spawn_distance):
            self.next_spawn_distance += self.spawn_gap
            self.spawn_entity()
        return road_delta


class ProgressiveRace(GameState):
    """Keep the difficulty curve, animal schedule and workload cap in the app."""

    __slots__ = ("elapsed_ms", "level", "max_entities", "next_rodent_ms",
                 "next_chicken_ms", "animal_kinds")

    def __init__(self, width, height, randint_source=randint, choice_source=choice):
        coin = EntityKind("coin", "coin", 16, 9, collect_on_contact, 1)
        hazards = tuple(
            EntityKind(name, name, 16 * scale, radius * scale, crash_on_contact)
            for name, radius, scale in (("cow", 11, COW_SPRITE_SCALE),
                                        ("pylon", 10, 1), ("oil", 12, 1)))
        super().__init__(RoadState(), width // 6, width - width // 6,
                         48, height, width // 2, height - 54, CAR_RADIUS,
                         (coin, coin) + hazards, DIFFICULTY_STAGES[0][2],
                         randint_source, choice_source)
        self.elapsed_ms = 0
        self.level = 0
        self.max_entities = DIFFICULTY_STAGES[0][1]
        self.next_rodent_ms = RODENT_START_MS
        self.next_chicken_ms = CHICKEN_START_MS
        self.animal_kinds = {
            "capybara": EntityKind("capybara", "capybara", 16, 12, crash_on_contact, 2),
            "chicken": EntityKind("chicken", "chicken", 16, 8, crash_on_contact, 2),
        }

    def _animal_present(self, name):
        return any(entity.active and entity.kind.name == name
                   for entity in self.entities)

    def spawn_entity(self, kind=None, y=None, horizontal_velocity=0,
                     road_relative=True, boundary_policy=bounce_at_road_edge):
        if len(self.entities) >= self.max_entities:
            return None
        if kind is None:
            animal = None
            if (self.elapsed_ms >= self.next_chicken_ms and
                    not self._animal_present("chicken")):
                animal = "chicken"
            elif (self.elapsed_ms >= self.next_rodent_ms and
                    not self._animal_present("capybara")):
                animal = "capybara"
            if animal is not None:
                kind = self.animal_kinds[animal]
                direction = self._choice((-1, 1))
                x = (self.road_left + kind.visual_radius + 1 if direction > 0
                     else self.road_right - kind.visual_radius - 2)
                spawn_y = self.track_top + 20
                speed = self._capybara_speed(kind, spawn_y) if animal == "capybara" else 96
                entity = CrossingAnimal(kind, x, spawn_y,
                                        direction, self._randint, speed)
                if animal == "chicken":
                    self.next_chicken_ms = self.elapsed_ms + 12000
                else:
                    self.next_rodent_ms = self.elapsed_ms + 18000
                return self.add_entity(entity, spawned=True)
            # Coins remain common early; later levels favor hazards.
            pool = self.entity_kinds if self.level < 2 else self.entity_kinds[1:]
            kind = self._choice(pool)
        return super().spawn_entity(kind, y, horizontal_velocity,
                                    road_relative, boundary_policy)

    def _capybara_speed(self, kind, spawn_y):
        """Pick one pace that puts this animal inside the road at encounter."""
        span = self.road_right - self.road_left - kind.visual_radius * 2 - 3
        # Use the current speed as a conservative bound: the road only speeds up.
        # Include both collision radii and quantization so it stays through passing.
        distance = max(1, self.player_y + self.player_radius +
                       kind.collision.radius + SCROLL_QUANTUM - spawn_y)
        fraction = self._randint(40, 70)
        return max(1, span * self.road.speed_per_second * fraction // (distance * 100))

    def step(self, elapsed_ms):
        if not self.crashed:
            self.elapsed_ms += int(elapsed_ms)
            while (self.level + 1 < len(DIFFICULTY_STAGES) and
                   self.elapsed_ms >= DIFFICULTY_STAGES[self.level + 1][0]):
                self.level += 1
                unused, limit, self.spawn_gap = DIFFICULTY_STAGES[self.level]
                self.max_entities = min(MAX_ROAD_ENTITIES, limit)
                self.next_spawn_distance = min(
                    self.next_spawn_distance, self.road.distance + self.spawn_gap)
        return super().step(elapsed_ms)


class RoadRenderer:
    """Reconstruct clipped Racer road regions from authoritative state."""

    __slots__ = (
        "canvas", "game", "width", "center_x", "center_period",
        "center_radius", "grass", "asphalt", "marker", "player_color",
        "_circle_spans", "art")

    def __init__(self, canvas, game, width, center_period, center_radius,
                 grass, asphalt, marker, player_color, art=None):
        self.canvas = canvas
        self.game = game
        self.width = int(width)
        self.center_x = self.width // 2
        self.center_period = int(center_period)
        self.center_radius = int(center_radius)
        self.grass = grass
        self.asphalt = asphalt
        self.marker = marker
        self.player_color = player_color
        self.art = art
        self._circle_spans = {}
        self._cache_circle(self.center_radius)
        self._cache_circle(game.player_radius)
        for kind in game.entity_kinds:
            self._cache_circle(kind.visual_radius)

    def _cache_circle(self, radius):
        radius = int(radius)
        spans = self._circle_spans.get(radius)
        if spans is not None:
            return spans
        radius_squared = radius * radius
        spans = []
        for offset_y in range(-radius, radius + 1):
            spans.append(int(
                (radius_squared - offset_y * offset_y) ** 0.5))
        spans = tuple(spans)
        self._circle_spans[radius] = spans
        return spans

    @staticmethod
    def _intersects(bounds, left, top, right, bottom):
        return not (
            bounds[0] + bounds[2] <= left or bounds[0] >= right or
            bounds[1] + bounds[3] <= top or bounds[1] >= bottom)

    def _draw_circle(self, target, x, y, radius, color,
                     left, top, right, bottom, x_offset=0, y_offset=0):
        spans = self._cache_circle(radius)
        first_y = max(top, y - radius)
        last_y = min(bottom - 1, y + radius)
        for target_y in range(first_y, last_y + 1):
            half_width = spans[target_y - y + radius]
            first_x = max(left, x - half_width)
            last_x = min(right - 1, x + half_width)
            if last_x >= first_x:
                target.hline(
                    first_x - x_offset, target_y - y_offset,
                    last_x - first_x + 1, color)

    def _draw_visual(self, target, x, y, radius, visual,
                     left, top, right, bottom, x_offset=0, y_offset=0):
        if self.art is None:
            self._draw_circle(target, x, y, radius, visual,
                              left, top, right, bottom, x_offset, y_offset)
        else:
            sprite = self.art.sprites[visual]
            sprite.draw(target, x - sprite.width // 2,
                        y - sprite.height // 2,
                        (left, top, right - left, bottom - top),
                        x_offset, y_offset)

    def rebuild_background(self, area, target=None, x_offset=0, y_offset=0,
                           center_phase=None):
        """Rebuild clipped grass, asphalt, and markers on one target."""
        game = self.game
        target = self.canvas if target is None else target
        left = max(0, int(area[0]))
        top = max(game.track_top, int(area[1]))
        right = min(self.width, int(area[0]) + int(area[2]))
        bottom = min(game.track_bottom, int(area[1]) + int(area[3]))
        if right <= left or bottom <= top:
            return False

        target.fill_rect(
            left - x_offset, top - y_offset,
            right - left, bottom - top, self.grass)
        road_left = max(left, game.road_left)
        road_right = min(right, game.road_right)
        if road_right > road_left:
            target.fill_rect(
                road_left - x_offset, top - y_offset,
                road_right - road_left, bottom - top, self.asphalt)

        phase = game.road.center_phase if center_phase is None else \
            int(center_phase)
        center_y = game.track_top + phase - self.center_period
        while center_y - self.center_radius < bottom:
            if center_y + self.center_radius >= top:
                self._draw_visual(
                    target, self.center_x, center_y,
                    self.center_radius, self.marker,
                    left, top, right, bottom, x_offset, y_offset)
            center_y += self.center_period
        return True

    def rebuild(self, area):
        """Rebuild one arbitrary rectangle clipped to the track."""
        game = self.game
        left = max(0, int(area[0]))
        top = max(game.track_top, int(area[1]))
        right = min(self.width, int(area[0]) + int(area[2]))
        bottom = min(game.track_bottom, int(area[1]) + int(area[3]))
        if right <= left or bottom <= top:
            return False

        self.rebuild_background((left, top, right - left, bottom - top))

        for entity in game.entities:
            if (entity.active and self._intersects(
                    entity.current_bounds, left, top, right, bottom)):
                self._draw_visual(
                    self.canvas, entity.x, entity.y,
                    entity.kind.visual_radius,
                    (entity.kind.visual + "_left" if self.art is not None and
                     isinstance(entity, CrossingAnimal) and entity.direction < 0
                     else entity.kind.visual), left, top, right, bottom)

        if self._intersects(self.player_bounds(game.player_x),
                            left, top, right, bottom):
            self._draw_visual(
                self.canvas, game.player_x, game.player_y, game.player_radius,
                self.player_color, left, top, right, bottom)
        return True

    def player_bounds(self, x):
        if self.art is not None:
            sprite = self.art.sprites[self.player_color]
            return (int(x) - sprite.width // 2,
                    self.game.player_y - sprite.height // 2,
                    sprite.width, sprite.height)
        radius = self.game.player_radius
        return (
            int(x) - radius, self.game.player_y - radius,
            radius * 2 + 1, radius * 2 + 1)

    def render(self, damage, synchronize=True):
        """Rebuild every final region before presenting any of them."""
        for index in range(damage.count):
            self.rebuild(damage.area(index))
        if synchronize and damage.count:
            self.canvas.wait_for_frame_sync()
        for index in range(damage.count):
            self.canvas.show(damage.area(index))


class DirtyRegionAnimator:
    """Coordinate Racer changes through one reusable damage tracker."""

    __slots__ = ("game", "renderer", "damage", "_old_player_x")

    def __init__(self, game, renderer, capacity=12, merge_overhead=48):
        self.game = game
        self.renderer = renderer
        self.damage = DamageTracker(
            (0, game.track_top, renderer.width,
             game.track_bottom - game.track_top),
            capacity, merge_overhead)
        self._old_player_x = game.player_x

    def begin_frame(self):
        self.damage.clear()
        self._old_player_x = self.game.player_x

    def record_step(self, road_delta):
        game = self.game
        if road_delta:
            radius = self.renderer.center_radius
            self.damage.mark(
                self.renderer.center_x - radius, game.track_top,
                radius * 2 + 1, game.track_bottom - game.track_top)

        for entity in game.entities:
            if (entity.previous_bounds != entity.current_bounds or
                    (isinstance(entity, CrossingAnimal) and
                     entity.previous_direction != entity.direction)):
                self.damage.add(entity.previous_bounds)
                self.damage.add(entity.current_bounds)
        for entity in game.removed_entities:
            self.damage.add(entity.previous_bounds)
            self.damage.add(entity.current_bounds)
        for entity in game.spawned_entities:
            self.damage.add(entity.current_bounds)

    def present(self):
        if self._old_player_x != self.game.player_x:
            self.damage.add(self.renderer.player_bounds(self._old_player_x))
            self.damage.add(self.renderer.player_bounds(self.game.player_x))
        self.renderer.render(self.damage)


class RoadBandCache:
    """Prepare every exposed road band reachable by one rendered frame."""

    __slots__ = (
        "canvas", "renderer", "quantum", "max_delta", "phase_count",
        "_bands")

    def __init__(self, canvas, renderer, quantum, max_delta,
                 framebuffer_factory):
        self.canvas = canvas
        self.renderer = renderer
        self.quantum = int(quantum)
        self.max_delta = int(max_delta)
        period = renderer.center_period
        if (self.quantum <= 0 or self.max_delta < self.quantum or
                self.max_delta % self.quantum or period % self.quantum):
            raise ValueError("band dimensions must align to the road quantum")
        self.phase_count = period // self.quantum
        self._bands = [None] * (self.max_delta // self.quantum + 1)

        width = renderer.width
        top = renderer.game.track_top
        for delta in range(
                self.quantum, self.max_delta + 1, self.quantum):
            phases = [None] * self.phase_count
            for phase in range(0, period, self.quantum):
                band = framebuffer_factory(width, delta)
                renderer.rebuild_background(
                    (0, top, width, delta), band,
                    y_offset=top, center_phase=phase)
                phases[phase // self.quantum] = canvas.prepare_sprite(
                    band, width, delta)
            self._bands[delta // self.quantum] = phases

    def get(self, delta, phase):
        """Return a warmed band for one aligned movement and final phase."""
        delta = int(delta)
        phase = int(phase) % self.renderer.center_period
        if (delta <= 0 or delta > self.max_delta or
                delta % self.quantum or phase % self.quantum):
            raise ValueError("road band was not prepared")
        return self._bands[delta // self.quantum][phase // self.quantum]


class ScanoutAnimator:
    """Scroll retained road pixels, then reconstruct non-carried damage."""

    __slots__ = (
        "game", "renderer", "bands", "damage", "_old_player_x",
        "_road_delta")

    def __init__(self, game, renderer, bands,
                 capacity=12, merge_overhead=48):
        self.game = game
        self.renderer = renderer
        self.bands = bands
        self.damage = DamageTracker(
            (0, game.track_top, renderer.width,
             game.track_bottom - game.track_top),
            capacity, merge_overhead)
        self._old_player_x = game.player_x
        self._road_delta = 0

    def begin_frame(self):
        self.damage.clear()
        self._old_player_x = self.game.player_x
        self._road_delta = 0

    def record_step(self, road_delta):
        self._road_delta += int(road_delta)

    def _mark_carried(self, bounds):
        self.damage.mark(
            bounds[0], bounds[1] + self._road_delta,
            bounds[2], bounds[3])

    def present(self):
        game = self.game
        delta = self._road_delta

        for entity in game.entities:
            if not entity.visible_before_frame:
                self.damage.add(entity.current_bounds)
                continue
            previous = entity.frame_bounds
            current = entity.current_bounds
            if (previous[0] != current[0] or
                    (isinstance(entity, CrossingAnimal) and
                     entity.frame_direction != entity.direction) or
                    (delta > 0 and previous[1] < game.track_top) or
                    previous[1] + delta != current[1] or
                    previous[2] != current[2] or
                    previous[3] != current[3]):
                self._mark_carried(previous)
                self.damage.add(current)

        for entity in game.removed_entities:
            if entity.visible_before_frame:
                self._mark_carried(entity.frame_bounds)

        player_bounds = self.renderer.player_bounds(self._old_player_x)
        self._mark_carried(player_bounds)
        self.damage.add(self.renderer.player_bounds(game.player_x))

        if delta or self.damage.count:
            self.renderer.canvas.wait_for_frame_sync()
        if delta:
            self.renderer.canvas.scroll_region(
                (0, game.track_top, self.renderer.width,
                 game.track_bottom - game.track_top),
                dy=delta,
                exposed=self.bands.get(delta, game.road.center_phase))
        self.renderer.render(self.damage, synchronize=False)


def supports_scanout_animation(canvas):
    """Return whether final-coordinate capabilities fit Racer's road."""
    capabilities = canvas.scroll_capabilities()
    return (
        "y" in capabilities.get("axes", ()) and
        capabilities.get("fixed_areas", False) and
        capabilities.get("wraps", False) and
        capabilities.get("full_orthogonal_axis", False))


def prefers_scanout_animation(canvas, game,
                              minimum=SCANOUT_MIN_ROAD_ENTITIES):
    """Apply the measured scanout policy to the current object workload."""
    if not supports_scanout_animation(canvas):
        return False
    carried = 0
    for entity in game.entities:
        if not entity.active:
            continue
        if not entity.road_relative or entity.horizontal_velocity:
            return False
        carried += 1
    return carried >= int(minimum)


def maximum_scroll_delta(speed_stages=ROAD_SPEED_STAGES,
                         update_ms=SIMULATION_STEP_MS,
                         max_updates=MAX_UPDATES_PER_FRAME,
                         quantum=SCROLL_QUANTUM):
    """Return the largest quantized road delta one frame can emit."""
    speed = max(stage[1] for stage in speed_stages)
    distance = (speed * update_ms * max_updates + 999) // 1000
    return ((distance + quantum - 1) // quantum) * quantum


class RacerArt:
    """Own the app's atlas layout and predecoded sprites and HUD glyphs."""

    def __init__(self, path="/files/assets/racer.ts16"):
        from tartlabutils.sprites import SpriteSheet

        sheet = SpriteSheet(path)
        self.sprites = {}
        for index, name in enumerate(("car", "cow", "pylon", "oil", "coin",
                                      "capybara", "chicken")):
            scale = (CAR_SPRITE_SCALE if name == "car" else
                     COW_SPRITE_SCALE if name == "cow" else 1)
            self.sprites[name] = sheet.sprite(
                index * 32, 0, 32, 32, scale=scale)
            if name in ("capybara", "chicken"):
                self.sprites[name + "_left"] = sheet.sprite(
                    index * 32, 0, 32, 32, flip_x=True)
        self.sprites["marker"] = sheet.sprite(0, 32, 7, 8)
        self.background = sheet.color_at(9, 32)
        self.asphalt = sheet.color_at(10, 32)
        self.grass = sheet.color_at(11, 32)
        self.glyphs = {}
        for character in " SCORE0123456789DISTMCRASHED-TAPLEFT/RIGHT":
            if character not in self.glyphs:
                index = ord(character) - 32
                self.glyphs[character] = sheet.sprite(
                    index % 26 * 6, 40 + index // 26 * 8, 6, 8, scale=2)

    def text(self, canvas, value, x, y, clip):
        for character in value:
            self.glyphs[character].draw(canvas, x, y, clip)
            x += 12


class RacerHUD:
    """Present changed score, distance and race status in the fixed top area."""

    def __init__(self, canvas, game, art):
        self.canvas, self.game, self.art = canvas, game, art
        self.previous = None

    def draw(self, present=True):
        game = self.game
        values = (game.score, game.road.distance // 100, game.crashed,
                  getattr(game, "level", 0))
        if values == self.previous:
            return False
        self.previous = values
        area = (0, 0, self.canvas.width, game.track_top)
        self.canvas.fill_rect(*area, self.art.background)
        self.art.text(self.canvas, "SCORE %04d" % min(values[0], 9999), 8, 5, area)
        distance = "%04dM" % min(values[1], 9999)
        self.art.text(self.canvas, distance, self.canvas.width - 68, 5, area)
        status = "CRASHED - TAP" if game.crashed else "L%d LEFT / RIGHT" % (values[3] + 1)
        self.art.text(self.canvas, status, 8, 27, area)
        if present:
            self.canvas.show(area)
        return True


def create_race(width, height):
    """Start with an easy coin on the player's line and one distant cow."""
    game = ProgressiveRace(width, height)
    coin_y = game.track_top + (game.player_y - game.track_top) // 2
    game.add_entity(Entity(game.entity_kinds[0], game.player_x, coin_y))
    cow = game.entity_kinds[2]
    game.add_entity(Entity(cow, game.road_left + cow.visual_radius + 3,
                           game.track_top + cow.visual_radius + 3))
    game.spawned_entities.clear()
    return game


def main():
    """Create the display resources and run the interactive Racer."""
    from framebuf import FrameBuffer, RGB565
    from tartlabutils.modern_app import (
        PortraitCanvas, PortraitTouchGrid, game_surface)

    surface = game_surface()
    canvas = PortraitCanvas(surface)
    touch = PortraitTouchGrid(("left", "right"), 2, 1)

    art = RacerArt()
    width = canvas.width
    height = canvas.height
    header_height = 48
    track_top = header_height
    track_height = height - track_top
    game = create_race(width, height)
    hud = RacerHUD(canvas, game, art)
    renderer = RoadRenderer(
        canvas, game, width, CENTER_PERIOD, 4,
        art.grass, art.asphalt, "marker", "car", art)
    if prefers_scanout_animation(canvas, game):
        def make_band(band_width, band_height):
            return FrameBuffer(
                bytearray(band_width * band_height * 2),
                band_width, band_height, RGB565)

        bands = RoadBandCache(
            canvas, renderer, SCROLL_QUANTUM,
            maximum_scroll_delta(), make_band)
        animator = ScanoutAnimator(game, renderer, bands)
    else:
        animator = DirtyRegionAnimator(game, renderer)

    canvas.fill(art.background)
    renderer.rebuild((0, track_top, width, track_height))
    hud.draw(present=False)
    canvas.show()

    clock = FrameClock(
        TARGET_FRAME_MS, SIMULATION_STEP_MS, MAX_UPDATES_PER_FRAME)
    restart_armed = False

    while True:
        updates = clock.updates_due()
        if not updates:
            clock.pace()
            continue

        animator.begin_frame()
        key = touch.read()
        if game.crashed:
            if key is None:
                restart_armed = True
            elif restart_armed:
                game = create_race(width, height)
                renderer.game = game
                animator.game = game
                hud.game = game
                hud.previous = None
                renderer.rebuild((0, track_top, width, track_height))
                hud.draw(present=False)
                canvas.show()
                restart_armed = False
            clock.pace()
            continue
        if key == "left":
            game.move_player(-STEER_STEP)
        elif key == "right":
            game.move_player(STEER_STEP)

        game.begin_frame()
        for unused in range(updates):
            animator.record_step(game.step(SIMULATION_STEP_MS))

        animator.present()
        hud.draw()
        clock.pace()


if globals().get("_RACER_AUTOSTART", True):
    main()
