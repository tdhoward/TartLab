"""Measure a bounded scrolling Racer workload through the raw REPL.

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


DEVICE_PROGRAM = r'''
import gc, sys, time, ujson
for search_path in reversed(('/device', '/lib', '/', '/files/user')):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

import tartlabutils.modern_app as modern_app
exec(__MODERN_APP_SOURCE__, modern_app.__dict__)
timing_scope = {'__name__': 'tartlabutils.timing_probe'}
exec(__TIMING_SOURCE__, timing_scope)
motion_scope = {'__name__': 'tartlabutils.motion_probe'}
exec(__MOTION_SOURCE__, motion_scope)

from framebuf import FrameBuffer, RGB565
from tartlabutils.platform import get_platform

FrameClock = timing_scope['FrameClock']
StagedMotion = motion_scope['StagedMotion']
PortraitCanvas = modern_app.PortraitCanvas
rgb565 = modern_app.rgb565

SAMPLES = __SAMPLES__
TARGET_FRAME_MS = 50
SIMULATION_STEP_MS = 50
MAX_UPDATES_PER_FRAME = 2
SCROLL_QUANTUM = 4
CENTER_PERIOD = 48
CENTER_RADIUS = 3
HEADER_HEIGHT = 24
CAR_RADIUS = 11
OBSTACLE_GAP = 92
ROAD_SPEED_STAGES = ((0, 80), (1200, 120))
MAX_SCROLL_DELTA = 12

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
        self.scroll_us = 0

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

    def present_scroll(self, area, dx, dy, rotation=0):
        presenter = getattr(self.surface, 'present_scroll', None)
        if presenter is None:
            return False
        started = ticks()
        try:
            return presenter(area, dx, dy, rotation)
        finally:
            self.scroll_us += elapsed(started)

    def reset_scroll(self):
        reset = getattr(self.surface, 'reset_scroll', None)
        if reset is not None:
            reset()

    def reset_counts(self):
        self.sent_bytes = 0
        self.transactions = 0
        self.write_us = 0
        self.scroll_us = 0

platform = get_platform()
base_surface = platform.enter_game_mode()
surface = CountingSurface(base_surface)
canvas = None

try:
    setup_started = ticks()
    canvas = PortraitCanvas(surface)
    width = canvas.width
    height = canvas.height
    track_top = HEADER_HEIGHT
    track_height = height - track_top
    road_margin = width // 6
    road_left = road_margin
    road_right = width - road_margin
    road_width = road_right - road_left
    car_y = height - 54

    black = rgb565(0, 0, 0)
    white = rgb565(255, 255, 255)
    green = rgb565(34, 139, 34)
    yellow = rgb565(255, 214, 0)
    obstacle_colors = (
        rgb565(244, 67, 54),
        rgb565(33, 150, 243),
        rgb565(156, 39, 176),
    )

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

    def prepare_track_band(band_height, phase):
        data = bytearray(width * band_height * 2)
        band = FrameBuffer(data, width, band_height, RGB565)
        band.fill(green)
        band.fill_rect(road_left, 0, road_width, band_height, black)
        draw_centerline(
            band, track_top, track_top + band_height,
            phase, y_offset=track_top)
        return canvas.prepare_sprite(band, width, band_height)

    def obstacle_intersects(obstacle, area):
        x, y, radius, unused_color = obstacle
        left, top, area_width, area_height = area
        return not (
            x + radius < left or x - radius >= left + area_width or
            y + radius < top or y - radius >= top + area_height)

    def draw_obstacle(obstacle):
        filled_circle(obstacle[0], obstacle[1], obstacle[2], obstacle[3])

    def car_area(x, y):
        padding = 1
        return (
            x - CAR_RADIUS - padding,
            y - CAR_RADIUS - padding,
            (CAR_RADIUS + padding) * 2 + 1,
            (CAR_RADIUS + padding) * 2 + 1,
        )

    def redraw_car(car_x, scroll_delta, obstacles, center_phase):
        first = car_area(car_x, car_y + scroll_delta)
        second = car_area(car_x, car_y)
        left = min(first[0], second[0])
        top = min(first[1], second[1])
        right = max(first[0] + first[2], second[0] + second[2])
        bottom = max(first[1] + first[3], second[1] + second[3])
        dirty = (left, top, right - left, bottom - top)
        canvas.fill_rect(left, top, dirty[2], dirty[3], black)
        draw_centerline(canvas, top, bottom, center_phase)
        changed_rows = (0, top, width, dirty[3])
        for obstacle in obstacles:
            if obstacle_intersects(obstacle, changed_rows):
                draw_obstacle(obstacle)
        filled_circle(car_x, car_y, CAR_RADIUS, yellow)
        canvas.show(dirty)

    road_motion = StagedMotion(ROAD_SPEED_STAGES, SCROLL_QUANTUM)
    center_phase = 0
    track_bands = {
        (band_height, phase): prepare_track_band(band_height, phase)
        for band_height in range(
            SCROLL_QUANTUM, MAX_SCROLL_DELTA + 1, SCROLL_QUANTUM)
        for phase in range(0, CENTER_PERIOD, SCROLL_QUANTUM)
    }
    car_x = width // 2
    obstacles = [
        [road_left + road_width // 3, track_top + 75,
         9, obstacle_colors[0]],
        [road_left + road_width * 2 // 3, track_top + 185,
         11, obstacle_colors[1]],
        [road_left + road_width // 2, track_top + 300,
         8, obstacle_colors[2]],
    ]

    canvas.fill(black)
    canvas.fill_rect(0, track_top, width, track_height, green)
    canvas.fill_rect(road_left, track_top, road_width, track_height, black)
    draw_centerline(canvas, track_top, height, center_phase)
    for obstacle in obstacles:
        draw_obstacle(obstacle)
    filled_circle(car_x, car_y, CAR_RADIUS, yellow)
    canvas.fill_rect(0, 0, width, HEADER_HEIGHT, black)
    canvas.text('RACER BENCHMARK', 8, 8, white)
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
    scroll_command_values = []
    work_values = []
    interval_values = []
    byte_values = []
    transaction_values = []
    update_count_values = []
    scroll_pixel_values = []
    work_deadline_misses = 0

    for sample in range(SAMPLES):
        frame_started = ticks()
        update_started = ticks()
        updates = clock.updates_due()
        scroll_delta = 0
        for unused in range(updates):
            scroll_delta += road_motion.advance(SIMULATION_STEP_MS)
        center_phase = (center_phase + scroll_delta) % CENTER_PERIOD
        for obstacle in obstacles:
            obstacle[1] += scroll_delta
            if obstacle[1] - obstacle[2] >= height:
                obstacle[1] -= track_height + OBSTACLE_GAP
        update_values.append(elapsed(update_started))

        surface.reset_counts()
        render_started = ticks()
        canvas.scroll_region(
            (0, track_top, width, track_height),
            dy=scroll_delta,
            exposed=track_bands[(scroll_delta, center_phase)])
        redraw_car(car_x, scroll_delta, obstacles, center_phase)
        render_us = elapsed(render_started)
        work_us = elapsed(frame_started)
        if work_us > TARGET_FRAME_MS * 1000:
            work_deadline_misses += 1

        render_values.append(render_us)
        write_values.append(surface.write_us)
        scroll_command_values.append(surface.scroll_us)
        cpu_render_values.append(max(
            0, render_us - surface.write_us - surface.scroll_us))
        work_values.append(work_us)
        byte_values.append(surface.sent_bytes)
        transaction_values.append(surface.transactions)
        update_count_values.append(updates)
        scroll_pixel_values.append(scroll_delta)

        clock.pace()
        interval_values.append(elapsed(frame_started))

    heap_after = gc.mem_free()
    result = {
        'samples': SAMPLES,
        'logical_size': (width, height),
        'target_frame_ms': TARGET_FRAME_MS,
        'simulation_step_ms': SIMULATION_STEP_MS,
        'max_updates_per_frame': MAX_UPDATES_PER_FRAME,
        'speed_stages': ROAD_SPEED_STAGES,
        'setup_us': setup_us,
        'metrics': {
            'update_us': summary(update_values),
            'render_us': summary(render_values),
            'cpu_render_us': summary(cpu_render_values),
            'surface_write_us': summary(write_values),
            'scroll_command_us': summary(scroll_command_values),
            'work_us': summary(work_values),
            'frame_interval_us': summary(interval_values),
            'bytes': summary(byte_values),
            'transactions': summary(transaction_values),
            'updates': summary(update_count_values),
            'scroll_pixels': summary(scroll_pixel_values),
        },
        'work_deadline_misses': work_deadline_misses,
        'clock_missed_deadlines': clock.missed_deadlines,
        'dropped_update_ms': clock.dropped_update_ms,
        'distance_pixels': road_motion.distance,
        'heap_free_before': heap_before,
        'heap_free_after': heap_after,
    }
    print('RACER_BENCHMARK=' + ujson.dumps(result))
finally:
    if canvas is not None:
        canvas.close()
    platform.enter_ui_mode()
'''


def device_program(samples: int = 12) -> str:
    if samples < 3:
        raise ValueError("samples must be at least 3")
    modern_app = (ROOT / "src/lib/tartlabutils/modern_app.py").read_text(
        encoding="utf-8")
    timing = (ROOT / "src/lib/tartlabutils/timing.py").read_text(
        encoding="utf-8")
    motion = (ROOT / "src/lib/tartlabutils/motion.py").read_text(
        encoding="utf-8")
    return (DEVICE_PROGRAM
            .replace("__SAMPLES__", str(samples))
            .replace("__MODERN_APP_SOURCE__", repr(modern_app))
            .replace("__TIMING_SOURCE__", repr(timing))
            .replace("__MOTION_SOURCE__", repr(motion)))


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
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(device_program(args.samples), args.timeout)
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
