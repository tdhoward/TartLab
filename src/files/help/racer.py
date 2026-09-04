"""A portrait touch racer with display-independent simulation state."""

from random import choice, randint

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
ROAD_SPEED_STAGES = (
    (0, 80),
    (1200, 120),
)
MAX_SCROLL_DELTA = (
    ROAD_SPEED_STAGES[-1][1] * SIMULATION_STEP_MS *
    MAX_UPDATES_PER_FRAME + 999) // 1000
MAX_SCROLL_DELTA = (
    (MAX_SCROLL_DELTA + SCROLL_QUANTUM - 1) // SCROLL_QUANTUM *
    SCROLL_QUANTUM)


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
        "current_bounds", "horizontal_velocity", "road_relative",
        "boundary_policy", "active", "contacted")

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
        "interactions", "spawned_entities", "entity_kinds", "spawn_gap",
        "next_spawn_distance", "score", "crashed", "_randint", "_choice")

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

    def move_player(self, direction):
        """Move the player one steering step while keeping it on the road."""
        minimum = self.road_left + self.player_radius + 2
        maximum = self.road_right - self.player_radius - 3
        self.player_x = max(minimum, min(maximum, self.player_x + direction))

    def add_entity(self, entity, spawned=False):
        self.entities.append(entity)
        if spawned:
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
    road_width = road_right - road_left
    car_y = height - 54

    # Keep these established symbolic names at the portable scroll boundary.
    WIDTH = width
    TRACK_TOP = track_top
    TRACK_HEIGHT = track_height

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

    def filled_circle(x, y, radius, color):
        radius_squared = radius * radius
        for offset_y in range(-radius, radius + 1):
            half_width = int(
                (radius_squared - offset_y * offset_y) ** 0.5)
            canvas.hline(
                x - half_width, y + offset_y,
                half_width * 2 + 1, color)

    def draw_centerline(target, top, bottom, phase, y_offset=0):
        center_y = track_top + phase - CENTER_PERIOD
        while center_y - CENTER_RADIUS < bottom:
            if center_y + CENTER_RADIUS >= top:
                radius_squared = CENTER_RADIUS * CENTER_RADIUS
                first_y = max(top, center_y - CENTER_RADIUS)
                last_y = min(bottom - 1, center_y + CENTER_RADIUS)
                for y in range(first_y, last_y + 1):
                    offset_y = y - center_y
                    half_width = int(
                        (radius_squared - offset_y * offset_y) ** 0.5)
                    target.hline(
                        width // 2 - half_width, y - y_offset,
                        half_width * 2 + 1, white)
            center_y += CENTER_PERIOD

    def draw_track_band(top, band_height):
        canvas.fill_rect(0, top, width, band_height, green)
        canvas.fill_rect(road_left, top, road_width, band_height, black)
        draw_centerline(
            canvas, top, top + band_height, road.center_phase)

    def prepare_track_band(band_height, phase):
        data = bytearray(width * band_height * 2)
        band = FrameBuffer(data, width, band_height, RGB565)
        band.fill(green)
        band.fill_rect(road_left, 0, road_width, band_height, black)
        draw_centerline(
            band, track_top, track_top + band_height,
            phase, y_offset=track_top)
        return canvas.prepare_sprite(band, width, band_height)

    def draw_header():
        canvas.fill_rect(0, 0, width, header_height, black)
        canvas.text("RACER  TAP LEFT / RIGHT", 8, 8, white)

    def draw_entity(entity):
        filled_circle(
            entity.x, entity.y, entity.kind.visual_radius,
            entity.kind.visual)

    def entity_intersects(entity, area):
        left, top, area_width, area_height = area
        entity_left, entity_top, entity_width, entity_height = (
            entity.current_bounds)
        return not (
            entity_left + entity_width <= left or
            entity_left >= left + area_width or
            entity_top + entity_height <= top or
            entity_top >= top + area_height)

    def car_area(x, y):
        padding = 1
        return (
            x - CAR_RADIUS - padding,
            y - CAR_RADIUS - padding,
            (CAR_RADIUS + padding) * 2 + 1,
            (CAR_RADIUS + padding) * 2 + 1,
        )

    def combined_area(first, second):
        left = min(first[0], second[0])
        top = min(first[1], second[1])
        right = max(first[0] + first[2], second[0] + second[2])
        bottom = max(first[1] + first[3], second[1] + second[3])
        return left, top, right - left, bottom - top

    def redraw_car(old_x, scroll_delta):
        """Retain the Phase 1 renderer until Phase 3 adds composition."""
        dirty = combined_area(
            car_area(old_x, car_y + scroll_delta),
            car_area(game.player_x, car_y))
        left, top, dirty_width, dirty_height = dirty
        canvas.fill_rect(left, top, dirty_width, dirty_height, black)
        draw_centerline(canvas, top, top + dirty_height, road.center_phase)
        changed_rows = (0, top, width, dirty_height)
        for entity in game.entities:
            if entity_intersects(entity, changed_rows):
                draw_entity(entity)
        filled_circle(game.player_x, car_y, CAR_RADIUS, yellow)
        canvas.show(dirty)

    track_bands = {
        (band_height, phase): prepare_track_band(band_height, phase)
        for band_height in range(
            SCROLL_QUANTUM, MAX_SCROLL_DELTA + 1, SCROLL_QUANTUM)
        for phase in range(0, CENTER_PERIOD, SCROLL_QUANTUM)
    }

    canvas.fill(black)
    draw_track_band(track_top, track_height)
    for initial_y, kind in zip(
            (track_top + 75, track_top + 185, track_top + 300),
            hazard_kinds):
        draw_entity(game.spawn_entity(kind, initial_y))
    game.spawned_entities.clear()
    filled_circle(game.player_x, car_y, CAR_RADIUS, yellow)
    draw_header()
    canvas.show()

    clock = FrameClock(
        TARGET_FRAME_MS, SIMULATION_STEP_MS, MAX_UPDATES_PER_FRAME)

    while True:
        updates = clock.updates_due()
        if not updates:
            clock.pace()
            continue

        old_car_x = game.player_x
        key = touch.read()
        if key == "left":
            game.move_player(-STEER_STEP)
        elif key == "right":
            game.move_player(STEER_STEP)

        game.begin_frame()
        scroll_delta = 0
        for unused in range(updates):
            scroll_delta += game.step(SIMULATION_STEP_MS)

        canvas.scroll_region(
            (0, TRACK_TOP, WIDTH, TRACK_HEIGHT),
            dy=scroll_delta,
            exposed=track_bands[(scroll_delta, road.center_phase)])

        for entity in game.spawned_entities:
            draw_entity(entity)
            radius = entity.kind.visual_radius
            canvas.show((
                entity.x - radius, entity.y - radius,
                radius * 2 + 1, radius * 2 + 1))

        redraw_car(old_car_x, scroll_delta)
        clock.pace()


if __name__ == "__main__":
    main()
