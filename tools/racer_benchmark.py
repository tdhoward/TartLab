"""Measure bounded dirty-region Racer workloads through the raw REPL.

The probe injects working-tree Python sources in memory. It does not flash
firmware, write the device filesystem, or start a local service.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

try:
    from phase1_device import RawRepl
except ImportError:
    from tools.phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
MARKER = "RACER_BENCHMARK="
DEFAULT_ENTITY_COUNTS = (0, 3, 8, 16)


DEVICE_PROGRAM = r'''
import gc, sys, time, ujson
for search_path in reversed(('/device', '/lib', '/', '/files/user')):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import tartlabutils.modern_app as modern_app
exec(__MODERN_APP_SOURCE__, modern_app.__dict__)

damage_scope = {'__name__': 'tartlabutils.damage_probe'}
exec(__DAMAGE_SOURCE__, damage_scope)
motion_scope = {'__name__': 'tartlabutils.motion_probe'}
exec(__MOTION_SOURCE__, motion_scope)
timing_scope = {'__name__': 'tartlabutils.timing_probe'}
exec(__TIMING_SOURCE__, timing_scope)
racer_source = __RACER_SOURCE__
racer_source = racer_source.replace(
    'from tartlabutils.damage import DamageTracker\n', '')
racer_source = racer_source.replace(
    'from tartlabutils.motion import StagedMotion\n', '')
racer_source = racer_source.replace(
    'from tartlabutils.timing import FrameClock\n', '')
racer_scope = {
    '__name__': 'racer_probe',
    '_RACER_AUTOSTART': False,
    'DamageTracker': damage_scope['DamageTracker'],
    'StagedMotion': motion_scope['StagedMotion'],
    'FrameClock': timing_scope['FrameClock'],
}
exec(racer_source, racer_scope)

from tartlabutils.platform import get_platform

FrameClock = timing_scope['FrameClock']
Entity = racer_scope['Entity']
EntityKind = racer_scope['EntityKind']
GameState = racer_scope['GameState']
RoadState = racer_scope['RoadState']
RoadRenderer = racer_scope['RoadRenderer']
DirtyRegionAnimator = racer_scope['DirtyRegionAnimator']
PortraitCanvas = modern_app.PortraitCanvas
rgb565 = modern_app.rgb565

SAMPLES = __SAMPLES__
ENTITY_COUNTS = __ENTITY_COUNTS__
TARGET_FRAME_MS = 50
SIMULATION_STEP_MS = 50
MAX_UPDATES_PER_FRAME = 2
CENTER_PERIOD = 48
CENTER_RADIUS = 3
HEADER_HEIGHT = 24
CAR_RADIUS = 11
ROAD_SPEED_STAGES = ((0, 80), (1200, 120))

def ticks():
    return time.ticks_us()

def elapsed(started):
    return time.ticks_diff(ticks(), started)

def summary(values):
    ordered = sorted(values)
    count = len(ordered)
    p95_index = (count * 95 + 99) // 100 - 1
    return {
        'min': ordered[0],
        'median': ordered[count // 2],
        'p95': ordered[p95_index],
        'max': ordered[-1],
    }

class CountingSurface:
    def __init__(self, surface):
        self.surface = surface
        self.width = surface.width
        self.height = surface.height
        self.color_format = surface.color_format
        self.sent_bytes = 0
        self.transactions = 0
        self.write_us = 0

    def allocate_buffer(self, width, height):
        return self.surface.allocate_buffer(width, height)

    def free_buffer(self, buffer):
        return self.surface.free_buffer(buffer)

    def write(self, buffer, x, y, width, height):
        started = ticks()
        try:
            return self.surface.write(buffer, x, y, width, height)
        finally:
            self.write_us += elapsed(started)
            self.sent_bytes += len(buffer)
            self.transactions += 1

    def reset_scroll(self):
        reset_scroll = getattr(self.surface, 'reset_scroll', None)
        if reset_scroll is not None:
            reset_scroll()

    def reset_counts(self):
        self.sent_bytes = 0
        self.transactions = 0
        self.write_us = 0

platform = get_platform()
base_surface = platform.enter_game_mode()
surface = CountingSurface(base_surface)
canvas = None

try:
    canvas = PortraitCanvas(surface)
    width = canvas.width
    height = canvas.height
    track_top = HEADER_HEIGHT
    track_height = height - track_top
    road_margin = width // 6
    road_left = road_margin
    road_right = width - road_margin
    car_y = height - 54

    black = rgb565(0, 0, 0)
    white = rgb565(255, 255, 255)
    green = rgb565(34, 139, 34)
    yellow = rgb565(255, 214, 0)
    object_colors = (
        rgb565(244, 67, 54),
        rgb565(33, 150, 243),
        rgb565(156, 39, 176),
        rgb565(255, 152, 0),
    )
    workloads = {}

    for entity_count in ENTITY_COUNTS:
        setup_started = ticks()
        kinds = tuple(
            EntityKind('object', color, radius, radius, None, layer)
            for color, radius, layer in zip(
                object_colors, (7, 9, 11, 8), (0, 1, 0, 2)))
        road = RoadState(ROAD_SPEED_STAGES, 4, CENTER_PERIOD)
        game = GameState(
            road, road_left, road_right, track_top, height,
            width // 2, car_y, CAR_RADIUS, kinds, 1000000)
        usable_height = track_height - 120
        usable_width = road_right - road_left - 40
        for index in range(entity_count):
            object_kind = kinds[index % len(kinds)]
            x = road_left + 20 + (index * 37) % usable_width
            y = track_top + 20 + (index * 23) % usable_height
            velocity = 20 if index & 1 else -20
            game.add_entity(Entity(
                object_kind, x, y, velocity, True,
                racer_scope['bounce_at_road_edge']))

        renderer = RoadRenderer(
            canvas, game, width, CENTER_PERIOD, CENTER_RADIUS,
            green, black, white, yellow)
        animator = DirtyRegionAnimator(game, renderer)
        canvas.fill(black)
        renderer.rebuild((0, track_top, width, track_height))
        canvas.fill_rect(0, 0, width, HEADER_HEIGHT, black)
        canvas.text('RACER DIRTY BENCH', 8, 8, white)
        canvas.show()
        setup_us = elapsed(setup_started)

        clock = FrameClock(
            TARGET_FRAME_MS, SIMULATION_STEP_MS, MAX_UPDATES_PER_FRAME)
        clock.pace()
        gc.collect()
        heap_before = gc.mem_free()

        update_values = []
        render_values = []
        cpu_render_values = []
        write_values = []
        work_values = []
        interval_values = []
        byte_values = []
        transaction_values = []
        update_count_values = []
        dirty_pixel_values = []
        dirty_region_values = []
        work_deadline_misses = 0

        for sample in range(SAMPLES):
            frame_started = ticks()
            update_started = ticks()
            updates = clock.updates_due()
            animator.begin_frame()
            game.begin_frame()
            for unused in range(updates):
                animator.record_step(game.step(SIMULATION_STEP_MS))
            update_values.append(elapsed(update_started))

            dirty_pixel_values.append(animator.damage.pixel_count)
            dirty_region_values.append(animator.damage.count)
            surface.reset_counts()
            render_started = ticks()
            animator.present()
            render_us = elapsed(render_started)
            work_us = elapsed(frame_started)
            if work_us > TARGET_FRAME_MS * 1000:
                work_deadline_misses += 1

            render_values.append(render_us)
            write_values.append(surface.write_us)
            cpu_render_values.append(max(0, render_us - surface.write_us))
            work_values.append(work_us)
            byte_values.append(surface.sent_bytes)
            transaction_values.append(surface.transactions)
            update_count_values.append(updates)

            clock.pace()
            interval_values.append(elapsed(frame_started))

        heap_after = gc.mem_free()
        workloads[str(entity_count)] = {
            'entity_count': entity_count,
            'setup_us': setup_us,
            'metrics': {
                'update_us': summary(update_values),
                'render_us': summary(render_values),
                'cpu_render_us': summary(cpu_render_values),
                'surface_write_us': summary(write_values),
                'work_us': summary(work_values),
                'frame_interval_us': summary(interval_values),
                'bytes': summary(byte_values),
                'transactions': summary(transaction_values),
                'updates': summary(update_count_values),
                'dirty_pixels': summary(dirty_pixel_values),
                'dirty_regions': summary(dirty_region_values),
            },
            'work_deadline_misses': work_deadline_misses,
            'clock_missed_deadlines': clock.missed_deadlines,
            'dropped_update_ms': clock.dropped_update_ms,
            'distance_pixels': road.distance,
            'heap_free_before': heap_before,
            'heap_free_after': heap_after,
        }

    result = {
        'strategy': 'dirty-region-animation',
        'samples_per_workload': SAMPLES,
        'entity_counts': ENTITY_COUNTS,
        'logical_size': (width, height),
        'target_frame_ms': TARGET_FRAME_MS,
        'simulation_step_ms': SIMULATION_STEP_MS,
        'max_updates_per_frame': MAX_UPDATES_PER_FRAME,
        'speed_stages': ROAD_SPEED_STAGES,
        'workloads': workloads,
    }
    print('RACER_BENCHMARK=' + ujson.dumps(result))
finally:
    if canvas is not None:
        canvas.close()
    platform.enter_ui_mode()
'''


def device_program(
        samples: int = 12,
        entity_counts: tuple[int, ...] = DEFAULT_ENTITY_COUNTS) -> str:
    if samples < 3:
        raise ValueError("samples must be at least 3")
    counts = tuple(int(count) for count in entity_counts)
    if not counts or any(count < 0 for count in counts):
        raise ValueError("entity counts must be nonempty and nonnegative")

    sources = {
        "__MODERN_APP_SOURCE__": ROOT / "src/lib/tartlabutils/modern_app.py",
        "__DAMAGE_SOURCE__": ROOT / "src/lib/tartlabutils/damage.py",
        "__MOTION_SOURCE__": ROOT / "src/lib/tartlabutils/motion.py",
        "__TIMING_SOURCE__": ROOT / "src/lib/tartlabutils/timing.py",
        "__RACER_SOURCE__": ROOT / "src/files/help/racer.py",
    }
    program = (DEVICE_PROGRAM
               .replace("__SAMPLES__", str(samples))
               .replace("__ENTITY_COUNTS__", repr(counts)))
    for marker, path in sources.items():
        program = program.replace(
            marker, repr(path.read_text(encoding="utf-8")))
    return program


def extract_result(output: bytes) -> dict:
    text = output.decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    raise ValueError("Racer benchmark marker was not returned")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument(
        "--entity-counts", type=int, nargs="+",
        default=DEFAULT_ENTITY_COUNTS)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(
            device_program(args.samples, tuple(args.entity_counts)),
            args.timeout)
    finally:
        repl.close()
    result = extract_result(output)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
