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
CAR_RADIUS = 11
STEER_STEP = 18
OBSTACLE_GAP = 92
SCANOUT_MIN_ROAD_ENTITIES = 3
ROAD_SPEED_STAGES = (
    (0, 80),
    (1200, 120),
)


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


class InteractionEvent:
    """Record one player contact for later presentation or feedback."""

    __slots__ = ("event_type", "entity")

    def __init__(self, event_type, entity):
        self.event_type = event_type
        self.entity = entity


def collect_on_contact(game, entity):
    """Placeholder collectible outcome used by the Racer example."""
    game.score += 1
    entity.active = False
    return "collectible"


def crash_on_contact(game, entity):
    """Placeholder hazard outcome used by the Racer example."""
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


class RoadRenderer:
    """Reconstruct clipped Racer road regions from authoritative state."""

    __slots__ = (
        "canvas", "game", "width", "center_x", "center_period",
        "center_radius", "grass", "asphalt", "marker", "player_color",
        "_circle_spans")

    def __init__(self, canvas, game, width, center_period, center_radius,
                 grass, asphalt, marker, player_color):
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
                self._draw_circle(
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
                self._draw_circle(
                    self.canvas, entity.x, entity.y,
                    entity.kind.visual_radius,
                    entity.kind.visual, left, top, right, bottom)

        player_radius = game.player_radius
        if not (
                game.player_x + player_radius < left or
                game.player_x - player_radius >= right or
                game.player_y + player_radius < top or
                game.player_y - player_radius >= bottom):
            self._draw_circle(
                self.canvas, game.player_x, game.player_y, player_radius,
                self.player_color, left, top, right, bottom)
        return True

    def player_bounds(self, x):
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
            if entity.previous_bounds != entity.current_bounds:
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


def main():
    """Create the display resources and run the interactive Racer."""
    from framebuf import FrameBuffer, RGB565
    from tartlabutils.modern_app import (
        PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)

    surface = game_surface()
    canvas = PortraitCanvas(surface)
    touch = PortraitTouchGrid(("left", "right"), 2, 1)

    black = rgb565(0, 0, 0)
    white = rgb565(255, 255, 255)
    green = rgb565(34, 139, 34)
    yellow = rgb565(255, 214, 0)
    obstacle_colors = (
        rgb565(244, 67, 54),
        rgb565(33, 150, 243),
        rgb565(156, 39, 176),
        rgb565(255, 152, 0),
    )

    width = canvas.width
    height = canvas.height
    header_height = 24
    track_top = header_height
    track_height = height - track_top
    road_margin = width // 6
    road_left = road_margin
    road_right = width - road_margin
    car_y = height - 54

    collectible_kind = EntityKind(
        "coin", white, 7, 7, collect_on_contact, 0)
    hazard_kinds = tuple(
        EntityKind("hazard", color, radius, radius,
                   crash_on_contact, 0)
        for color, radius in zip(obstacle_colors, (9, 11, 8, 10)))
    road = RoadState()
    game = GameState(
        road, road_left, road_right, track_top, height,
        width // 2, car_y, CAR_RADIUS,
        (collectible_kind,) + hazard_kinds)

    for initial_y, kind in zip(
            (track_top + 75, track_top + 185, track_top + 300),
            hazard_kinds):
        game.spawn_entity(kind, initial_y)
    game.spawned_entities.clear()

    def draw_header():
        canvas.fill_rect(0, 0, width, header_height, black)
        canvas.text("RACER  TAP LEFT / RIGHT", 8, 8, white)

    renderer = RoadRenderer(
        canvas, game, width, CENTER_PERIOD, CENTER_RADIUS,
        green, black, white, yellow)
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

    canvas.fill(black)
    renderer.rebuild((0, track_top, width, track_height))
    draw_header()
    canvas.show()

    clock = FrameClock(
        TARGET_FRAME_MS, SIMULATION_STEP_MS, MAX_UPDATES_PER_FRAME)

    while True:
        updates = clock.updates_due()
        if not updates:
            clock.pace()
            continue

        animator.begin_frame()
        key = touch.read()
        if key == "left":
            game.move_player(-STEER_STEP)
        elif key == "right":
            game.move_player(STEER_STEP)

        game.begin_frame()
        for unused in range(updates):
            animator.record_step(game.step(SIMULATION_STEP_MS))

        animator.present()
        clock.pace()


if globals().get("_RACER_AUTOSTART", True):
    main()
