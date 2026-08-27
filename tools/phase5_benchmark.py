"""Run and compare the Phase 5 graphics benchmark on a physical TartLab.

The device program deliberately uses the TartLab platform boundary.  It
selects either the qualified legacy PyDevices display or the modern native
``lcd_bus`` surface at runtime, while keeping geometry, SPI clock, assets,
region sizes, frame deadlines, and buffer counts fixed.

Raw results contain no settings, credentials, or user-file contents.  The
``collect`` command interrupts the foreground application through the raw REPL
for the duration of the benchmark, but does not install files or flash the
device.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

try:
    from phase1_device import RawRepl
except ImportError:  # Allow import as ``tools.phase5_benchmark`` in tests.
    from tools.phase1_device import RawRepl


MARKER = "PHASE5_BENCHMARK"
SCHEMA = 1
PROFILES = ("legacy", "modern", "pydevices")


DEVICE_BENCHMARK_TEMPLATE = r'''
import gc, machine, os, sys, time, uhashlib, ujson
from tartlabutils.platform import get_platform

SAMPLES = __SAMPLES__
SWITCHES = __SWITCHES__
SPI_HZ = 60000000
FULL_DEADLINE_US = 33333
PARTIAL_DEADLINE_US = 16667
TRANSPORT_ROWS = 24

def ticks():
    return time.ticks_us()

def elapsed(start):
    return time.ticks_diff(ticks(), start)

def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) & 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2

def digest(value):
    raw = uhashlib.sha256(value).digest()
    return ''.join('%02x' % byte for byte in raw)

def class_name(value):
    value_type = type(value)
    return (getattr(value_type, '__module__', '') + '.' +
            getattr(value_type, '__name__', ''))

def fill_from(target, source):
    target[:] = source

def network_state():
    result = {}
    try:
        import network
        for name, interface_id in (('station', network.STA_IF),
                                   ('access_point', network.AP_IF)):
            interface = network.WLAN(interface_id)
            entry = {'active': interface.active()}
            try:
                entry['status'] = interface.status()
            except Exception as error:
                entry['status_error'] = repr(error)
            result[name] = entry
    except Exception as error:
        result['error'] = repr(error)
    return result

platform = get_platform()
capabilities = platform.capabilities
modern = bool(capabilities.get('direct_rgb565', False))
profile = capabilities.get(
    'phase5_benchmark_profile', 'modern' if modern else 'legacy')
async_direct = bool(capabilities.get('async_direct_rgb565', modern))

def enter_game_mode():
    method = getattr(platform, 'enter_game_mode', None)
    if method is not None:
        return method()
    return platform.display

def enter_ui_mode():
    method = getattr(platform, 'enter_ui_mode', None)
    if method is not None:
        method()

surface = enter_game_mode()
if modern:
    width = surface.width
    height = surface.height
    pipeline_buffer_storage = capabilities.get(
        'direct_buffer_storage', 'native-internal-dma')
else:
    surface.rotation = 90
    surface.disable_auto_byteswap(False)
    width = surface.width
    height = surface.height
    pipeline_buffer_storage = 'micropython-bytearray'

if (width, height) != (480, 222):
    raise RuntimeError('benchmark requires logical 480x222 orientation')

tracked_allocations = [0]

def allocate(width_value, height_value):
    tracked_allocations[0] += 1
    if modern:
        return surface.allocate_buffer(width_value, height_value)
    return bytearray(width_value * height_value * 2)

def release(buffer):
    if modern:
        surface.free_buffer(buffer)

def transfer(buffer, x, y, width_value, height_value, wait=True):
    if modern:
        surface.write(buffer, x, y, width_value, height_value, wait=wait)
    else:
        surface.blit_rect(buffer, x, y, width_value, height_value)

def wait_transfer():
    if modern:
        surface.wait()

def transfer_region(buffer, x, y, width_value, height_value, wait=True,
                    tile_rows=TRANSPORT_ROWS):
    buffer_view = memoryview(buffer)
    offset_y = 0
    while offset_y < height_value:
        rows = min(tile_rows, height_value - offset_y)
        size = width_value * rows * 2
        transfer(buffer_view[:size], x, y + offset_y,
                 width_value, rows, wait=wait)
        if not wait:
            wait_transfer()
        offset_y += rows

def transfer_samples(buffer, x, y, width_value, height_value, count,
                     tile_rows=TRANSPORT_ROWS):
    values = []
    transfer_region(buffer, x, y, width_value, height_value,
                    tile_rows=tile_rows)
    transfer_region(buffer, x, y, width_value, height_value,
                    tile_rows=tile_rows)
    for unused in range(count):
        started = ticks()
        transfer_region(buffer, x, y, width_value, height_value,
                        tile_rows=tile_rows)
        values.append(elapsed(started))
    return values

def direct_transfer_samples(buffer, x, y, width_value, height_value, count):
    values = []
    transfer(buffer, x, y, width_value, height_value)
    transfer(buffer, x, y, width_value, height_value)
    for unused in range(count):
        started = ticks()
        transfer(buffer, x, y, width_value, height_value)
        values.append(elapsed(started))
    return values

def fill_asset(buffer, row_width):
    buffer_view = memoryview(buffer)
    for offset in range(0, len(buffer_view), 2):
        pixel = offset // 2
        value = (pixel * 37 + (pixel // row_width) * 17) & 0xff
        buffer_view[offset] = value
        buffer_view[offset + 1] = value
    return digest(buffer_view)

def pipeline(buffer_a, buffer_b, x, y, width_value, height_value,
             render_next, deadline_us):
    baseline = transfer_samples(
        buffer_a, x, y, width_value, height_value, 3)
    baseline_median = median(baseline)
    render_us = []
    submission_us = []
    wait_us = []
    total_us = []
    overlap_us = []
    current = buffer_a
    following = buffer_b
    for index in range(SAMPLES):
        started = ticks()
        submitted = ticks()
        transfer(current, x, y, width_value, height_value,
                 wait=not async_direct)
        submission_us.append(elapsed(submitted))
        rendered = ticks()
        render_next(following, current, index + 1)
        render_time = elapsed(rendered)
        render_us.append(render_time)
        waited = ticks()
        wait_transfer()
        wait_time = elapsed(waited)
        wait_us.append(wait_time)
        total = elapsed(started)
        total_us.append(total)
        if async_direct:
            hidden = baseline_median - wait_time
            if hidden < 0:
                hidden = 0
            if hidden > render_time:
                hidden = render_time
            overlap_us.append(hidden)
        else:
            overlap_us.append(0)
        current, following = following, current
    return {
        'transfer_baseline_us': baseline,
        'render_us': render_us,
        'submission_us': submission_us,
        'wait_after_render_us': wait_us,
        'overlap_estimate_us': overlap_us,
        'total_frame_us': total_us,
        'deadline_us': deadline_us,
        'missed_deadlines': sum(1 for value in total_us
                                if value > deadline_us),
        'overlap_method': ('sync-transfer-baseline-minus-post-render-wait'
                           if async_direct else
                           'unsupported-synchronous-transfer'),
    }

gc.collect()
heap_start = {'free': gc.mem_free(), 'allocated': gc.mem_alloc()}
transport = allocate(width, TRANSPORT_ROWS)
transport_view = memoryview(transport)
transport_pixels = width * TRANSPORT_ROWS

# Every pixel has equal high and low bytes.  The exact same wire-order asset
# is therefore invariant under the legacy driver's optional RGB565 byte swap.
asset_sha256 = fill_asset(transport, width)

regions = {}
for name, region_width, coverage in (
        ('full', 480, 100), ('dirty_50', 240, 50),
        ('dirty_25', 120, 25), ('dirty_10', 48, 10)):
    byte_count = region_width * height * 2
    if coverage == 100:
        region_buffer = transport
        region_digest = asset_sha256
        values = transfer_samples(
            region_buffer, 0, 0, region_width, height, SAMPLES)
        submission = 'ten-24-row-or-final-shorter-transfers'
    elif coverage == 50:
        # 106,560 bytes exceeds the contiguous internal-DMA ceiling after
        # LVGL owns its two transport buffers.  Two 240x111 tiles are the
        # largest exact, symmetric representation of the 50 percent region.
        tile_rows = height // 2
        region_buffer = allocate(region_width, tile_rows)
        region_digest = fill_asset(region_buffer, region_width)
        values = transfer_samples(
            region_buffer, 0, 0, region_width, height, SAMPLES,
            tile_rows=tile_rows)
        submission = 'two-240x111-dirty-rectangle-transfers'
        release(region_buffer)
    else:
        region_buffer = allocate(region_width, height)
        region_digest = fill_asset(region_buffer, region_width)
        values = direct_transfer_samples(
            region_buffer, 0, 0, region_width, height, SAMPLES)
        submission = 'one-dirty-rectangle-transfer'
        release(region_buffer)
    regions[name] = {
        'width': region_width,
        'height': height,
        'coverage_percent': coverage,
        'bytes': byte_count,
        'asset_sha256': region_digest,
        'submission': submission,
        'transfer_us': values,
        'throughput_bytes_per_second': [
            (byte_count * 1000000) // value for value in values],
        'deadline_us': (FULL_DEADLINE_US if coverage == 100
                        else PARTIAL_DEADLINE_US),
        'missed_deadlines': sum(
            1 for value in values
            if value > (FULL_DEADLINE_US if coverage == 100
                        else PARTIAL_DEADLINE_US)),
    }

black = bytes((0, 0)) * transport_pixels
white = bytes((255, 255)) * transport_pixels
tracked_allocations[0] += 2
solid_render_us = []
solid_transfer_us = []
solid_total_us = []
for index in range(SAMPLES):
    started = ticks()
    rendered = ticks()
    fill_from(transport_view, white if index & 1 else black)
    solid_render_us.append(elapsed(rendered))
    sent = ticks()
    transfer_region(transport, 0, 0, width, height)
    solid_transfer_us.append(elapsed(sent))
    solid_total_us.append(elapsed(started))
solid = {
    'render_us': solid_render_us,
    'transfer_us': solid_transfer_us,
    'overlap_us': [0] * SAMPLES,
    'total_frame_us': solid_total_us,
    'deadline_us': FULL_DEADLINE_US,
    'missed_deadlines': sum(
        1 for value in solid_total_us if value > FULL_DEADLINE_US),
    'method': 'allocation-free-prebuilt-solid-copy-then-full-transfer',
}

# A 48x32 dirty union erases the old 32x32 sprite and draws its new position
# over a deterministic static background.  Two buffers permit native DMA to
# overlap the next frame's render on the modern profile.
sprite_width = 48
sprite_height = 32
sprite_bytes = sprite_width * sprite_height * 2
fill_from(transport_view, black)
transfer_region(transport, 0, 0, width, height)
sprite_assets = []
for phase in (0, 1):
    value = bytearray(sprite_bytes)
    tracked_allocations[0] += 1
    for pixel in range(sprite_width * sprite_height):
        x_value = pixel % sprite_width
        y_value = pixel // sprite_width
        inside = ((phase * 16) <= x_value < (phase * 16) + 32)
        color = 255 if inside and ((x_value ^ y_value) & 4) else 0
        value[pixel * 2] = color
        value[pixel * 2 + 1] = color
    sprite_assets.append(bytes(value))
    tracked_allocations[0] += 1
sprite_a = allocate(sprite_width, sprite_height)
sprite_b = allocate(sprite_width, sprite_height)
fill_from(memoryview(sprite_a), sprite_assets[0])
fill_from(memoryview(sprite_b), sprite_assets[1])

def render_sprite(target, unused_current, phase):
    fill_from(memoryview(target), sprite_assets[phase & 1])

sprite = pipeline(
    sprite_a, sprite_b, 96, 80, sprite_width, sprite_height,
    render_sprite, PARTIAL_DEADLINE_US)
sprite['asset_sha256'] = [digest(value) for value in sprite_assets]
sprite['static_background'] = 'black full-frame transfer before samples'
release(sprite_a)
release(sprite_b)

# Scroll a 480x64 viewport upward by eight rows.  Rendering copies the retained
# rows into the alternate buffer and paints a deterministic new bottom band;
# only the 28.8 percent viewport is transferred.
scroll_width = width
scroll_height = 24
scroll_step = 4
row_bytes = scroll_width * 2
scroll_size = scroll_width * scroll_height * 2
scroll_tail = bytes((90, 90)) * (scroll_width * scroll_step)
tracked_allocations[0] += 1
scroll_a = allocate(scroll_width, scroll_height)
scroll_b = allocate(scroll_width, scroll_height)
scroll_a_view = memoryview(scroll_a)
scroll_b_view = memoryview(scroll_b)
for offset in range(len(scroll_a_view)):
    scroll_a_view[offset] = 0
    scroll_b_view[offset] = 0

def render_scroll(target, current, unused_phase):
    target_view = memoryview(target)
    current_view = memoryview(current)
    retained = row_bytes * (scroll_height - scroll_step)
    target_view[:retained] = current_view[row_bytes * scroll_step:]
    target_view[retained:] = scroll_tail

scroll = pipeline(
    scroll_a, scroll_b, 0, 48, scroll_width, scroll_height,
    render_scroll, PARTIAL_DEADLINE_US)
scroll['coverage_percent'] = round(
    100 * scroll_height / height, 3)
scroll['asset_sha256'] = digest(scroll_tail)
release(scroll_a)
release(scroll_b)

# Count Python work that can execute while a full-frame transfer is active.
# The legacy transfer is synchronous, so it necessarily exposes zero work in
# the interval; the modern callback clears ``surface.busy`` from the DMA
# completion path.
fill_from(transport_view, black)
cpu_value = 1
cpu_iterations = 0
started = ticks()
# LEGACY_SPECIALIZATION_START
if async_direct:
    offset_y = 0
    while offset_y < height:
        rows = min(TRANSPORT_ROWS, height - offset_y)
        size = width * rows * 2
        transfer(transport_view[:size], 0, offset_y, width, rows, wait=False)
        while surface.busy:
            cpu_value = (cpu_value * 1664525 + 1013904223) & 0xffffffff
            cpu_iterations += 1
        wait_transfer()
        offset_y += rows
else:
    transfer_region(transport, 0, 0, width, height)
# LEGACY_SPECIALIZATION_END
transfer_interval_us = elapsed(started)
baseline_value = 1
baseline_iterations = 0
started = ticks()
while elapsed(started) < transfer_interval_us:
    baseline_value = (baseline_value * 1664525 + 1013904223) & 0xffffffff
    baseline_iterations += 1
cpu_availability = {
    'transfer_interval_us': transfer_interval_us,
    'iterations_during_transfer': cpu_iterations,
    'baseline_iterations_same_interval': baseline_iterations,
    'availability_percent': (
        round(100 * cpu_iterations / baseline_iterations, 3)
        if baseline_iterations else 0),
    'checksum': cpu_value ^ baseline_value,
    'interpretation': 'CPU headroom proxy for IDE/network servicing',
}

release(transport)
del transport, transport_view, black, white, sprite_assets, scroll_tail
gc.collect()
heap_after_direct = {'free': gc.mem_free(), 'allocated': gc.mem_alloc()}

# Exercise the actual TartLab UI abstraction.  The modern call mutates LVGL
# widgets and is explicitly flushed; the legacy call performs synchronous
# framebuffer rendering and transfers inside show_update_progress, so its
# render/transfer split is not observable without changing the qualified code.
enter_ui_mode()
if modern:
    # The pinned task handler services LVGL from a background MicroPython
    # thread.  Pause it while raw-REPL benchmark code drives LVGL explicitly;
    # concurrent calls into LVGL are unsupported and can reset the runtime.
    pause_ui = getattr(platform, 'pause_ui_for_benchmark', None)
    if pause_ui is not None:
        pause_ui()
    else:
        platform.controller._task_handler.disable()
        platform.controller._task_paused = True
        if platform.input is not None:
            platform.input.enable(False)
view = platform.create_ide_view()
view.show_startup('PHASE5')
ui_mutation_us = []
ui_flush_us = []
ui_total_us = []
for index in range(SAMPLES):
    started = ticks()
    changed = ticks()
    view.show_update_progress('BENCHMARK', index + 1, SAMPLES)
    ui_mutation_us.append(elapsed(changed))
    flushed = ticks()
    if modern:
        import lvgl as lv
        lv.refr_now(platform.controller._lv_display)
        platform.controller.wait_for_transfer()
        ui_flush_us.append(elapsed(flushed))
    else:
        ui_flush_us.append(None)
    ui_total_us.append(elapsed(started))
ui_widgets = {
    'renderer': 'lvgl-widgets' if modern else 'legacy-framebuffer-widgets',
    'render_or_combined_us': ui_mutation_us,
    'transfer_us': ui_flush_us,
    'total_frame_us': ui_total_us,
    'split_observable': modern,
    'deadline_us': PARTIAL_DEADLINE_US,
    'missed_deadlines': sum(
        1 for value in ui_total_us if value > PARTIAL_DEADLINE_US),
}

if modern:
    animation_target_values = []
    running_animation_counts = []
    animation_transfer_us = []
    animation_total_us = []
    view._progress.set_style_anim_duration(250, 0)
    view._progress.set_value(SAMPLES, False)
    view._progress.set_value(0, True)
    for unused in range(SAMPLES):
        time.sleep_ms(17)
        started = ticks()
        lv.timer_handler()
        animation_target_values.append(view._progress.get_value())
        count_running = getattr(lv, 'anim_count_running', None)
        running_animation_counts.append(
            count_running() if count_running is not None else None)
        flushed = ticks()
        lv.refr_now(platform.controller._lv_display)
        platform.controller.wait_for_transfer()
        animation_transfer_us.append(elapsed(flushed))
        animation_total_us.append(elapsed(started))
    lvgl_animation = {
        'supported': True,
        'duration_ms': 250,
        'target_values': animation_target_values,
        'running_animation_counts': running_animation_counts,
        'frames_with_display_transfer': sum(
            1 for value in animation_transfer_us if value > 1000),
        'transfer_us': animation_transfer_us,
        'total_frame_us_excluding_17ms_cadence_sleep': animation_total_us,
        'deadline_us': PARTIAL_DEADLINE_US,
        'missed_deadlines': sum(
            1 for value in animation_total_us
            if value > PARTIAL_DEADLINE_US),
    }
else:
    lvgl_animation = {
        'supported': False,
        'reason': 'qualified legacy firmware does not contain LVGL',
    }

if modern:
    resume_ui = getattr(platform, 'resume_ui_after_benchmark', None)
    if resume_ui is not None:
        resume_ui()
    else:
        if platform.input is not None:
            platform.input.enable(True)
        platform.controller._task_handler.enable()
        platform.controller._task_paused = False

# Preallocate one 10 percent strip, then record GC bytes and timings across the
# exact UI/game/UI boundary.  No benchmark-owned allocation occurs in the
# steady-state loop; internal renderer behavior remains visible in mem_alloc.
enter_game_mode()
switch_buffer = allocate(48, height)
switch_view = memoryview(switch_buffer)
for offset in range(len(switch_view)):
    switch_view[offset] = 0
enter_ui_mode()
gc.collect()
switch_heap_free = []
switch_heap_allocated = []
switch_total_us = []
steady_allocations_before = tracked_allocations[0]
for unused in range(SWITCHES):
    started = ticks()
    enter_game_mode()
    transfer(switch_view, 0, 0, 48, height)
    enter_ui_mode()
    switch_total_us.append(elapsed(started))
    gc.collect()
    switch_heap_free.append(gc.mem_free())
    switch_heap_allocated.append(gc.mem_alloc())
steady_allocations_after = tracked_allocations[0]
enter_game_mode()
release(switch_buffer)
enter_ui_mode()
gc.collect()
heap_end = {'free': gc.mem_free(), 'allocated': gc.mem_alloc()}

mode_switches = {
    'iterations': SWITCHES,
    'total_us': switch_total_us,
    'heap_free_after_gc': switch_heap_free,
    'heap_allocated_after_gc': switch_heap_allocated,
    'benchmark_owned_allocations_during_loop': (
        steady_allocations_after - steady_allocations_before),
    'heap_free_delta_first_to_last': (
        switch_heap_free[-1] - switch_heap_free[0]),
    'heap_allocated_delta_first_to_last': (
        switch_heap_allocated[-1] - switch_heap_allocated[0]),
}

result = {
    'schema': 1,
    'profile': profile,
    'runtime': {
        'sys_version': sys.version,
        'implementation': repr(sys.implementation),
        'uname': repr(os.uname()),
        'machine_frequency_hz': machine.freq(),
        'configured_display_spi_hz': SPI_HZ,
        'platform_class': class_name(platform),
        'display_class': class_name(platform.display),
    },
    'matrix': {
        'logical_width': width,
        'logical_height': height,
        'color_format': 'RGB565_BE_symmetric_test_assets',
        'full_frame_bytes': width * height * 2,
        'transport_rows': TRANSPORT_ROWS,
        'raw_transport_buffer_count': 1,
        'pipeline_buffer_count': 2,
        'raw_buffer_storage': pipeline_buffer_storage,
        'pipeline_buffer_storage': pipeline_buffer_storage,
        'direct_transfer_async': async_direct,
        'samples': SAMPLES,
        'mode_switches': SWITCHES,
        'asset_sha256': asset_sha256,
        'network_state_during_benchmark': network_state(),
    },
    'raw_transfers': regions,
    'solid_fills': solid,
    'sprite': sprite,
    'scroll': scroll,
    'ui_widgets': ui_widgets,
    'lvgl_animation': lvgl_animation,
    'cpu_availability': cpu_availability,
    'heap': {
        'start': heap_start,
        'after_direct_workloads': heap_after_direct,
        'end': heap_end,
        'tracked_setup_allocations': tracked_allocations[0],
        'allocation_counter_limitation': (
            'MicroPython exposes allocated bytes, not allocation-event count; '
            'benchmark-owned steady-state allocations are instrumented'),
    },
    'mode_switches': mode_switches,
}
print('PHASE5_BENCHMARK=' + ujson.dumps(result))
'''


def device_program(samples: int, switches: int,
                   profile: str | None = None) -> str:
    """Return MicroPython-compatible benchmark source."""
    if samples < 3:
        raise ValueError("samples must be at least 3")
    if switches < 2:
        raise ValueError("switches must be at least 2")
    if profile is not None and profile not in PROFILES:
        raise ValueError("unsupported benchmark profile")
    source = (DEVICE_BENCHMARK_TEMPLATE
              .replace("__SAMPLES__", str(samples))
              .replace("__SWITCHES__", str(switches)))
    if profile == "legacy":
        # The complete universal program crosses the parser/compiler limit in
        # the pinned MicroPython 1.23 runtime.  Its transfer is synchronous, so
        # specialize away the unreachable asynchronous CPU-headroom branch.
        start = source.index("# LEGACY_SPECIALIZATION_START")
        end = source.index("# LEGACY_SPECIALIZATION_END", start)
        end += len("# LEGACY_SPECIALIZATION_END")
        source = (
            source[:start] +
            "transfer_region(transport, 0, 0, width, height)" +
            source[end:])
    return source


def extract_result(output: bytes) -> dict:
    decoded = output.decode("utf-8", "replace")
    prefix = MARKER + "="
    for line in decoded.splitlines():
        if line.startswith(prefix):
            result = json.loads(line[len(prefix):])
            if not isinstance(result, dict):
                raise ValueError("benchmark result is not a JSON object")
            return result
    raise ValueError(
        f"device output did not contain {MARKER}: {decoded[-1000:]}")


def validate_result(result: dict, expected_profile: str | None = None) -> None:
    if result.get("schema") != SCHEMA:
        raise ValueError("unsupported Phase 5 benchmark schema")
    profile = result.get("profile")
    if profile not in PROFILES:
        raise ValueError(
            "benchmark profile must be legacy, modern, or pydevices")
    if expected_profile is not None and profile != expected_profile:
        raise ValueError(
            f"connected device is {profile}, expected {expected_profile}")
    matrix = result.get("matrix", {})
    if (matrix.get("logical_width"), matrix.get("logical_height")) != (480, 222):
        raise ValueError("benchmark result has wrong panel geometry")
    if matrix.get("full_frame_bytes") != 213_120:
        raise ValueError("benchmark result has wrong full-frame byte count")
    if matrix.get("color_format") != "RGB565_BE_symmetric_test_assets":
        raise ValueError("benchmark result has wrong color format")
    if (matrix.get("transport_rows"),
            matrix.get("raw_transport_buffer_count"),
            matrix.get("pipeline_buffer_count")) != (24, 1, 2):
        raise ValueError("benchmark result has wrong buffer matrix")
    if (not isinstance(matrix.get("samples"), int)
            or matrix["samples"] < 3
            or not isinstance(matrix.get("mode_switches"), int)
            or matrix["mode_switches"] < 2):
        raise ValueError("benchmark result has invalid sample counts")
    expected_storage = (
        "native-internal-dma" if profile == "modern"
        else "micropython-bytearray")
    if (matrix.get("raw_buffer_storage") != expected_storage
            or matrix.get("pipeline_buffer_storage") != expected_storage):
        raise ValueError("benchmark result has wrong profile buffer storage")
    if result.get("runtime", {}).get("configured_display_spi_hz") != 60_000_000:
        raise ValueError("benchmark result has wrong display SPI clock")
    expected_regions = {
        "full": (480, 222, 100,
                 "ten-24-row-or-final-shorter-transfers"),
        "dirty_50": (240, 222, 50,
                     "two-240x111-dirty-rectangle-transfers"),
        "dirty_25": (120, 222, 25, "one-dirty-rectangle-transfer"),
        "dirty_10": (48, 222, 10, "one-dirty-rectangle-transfer"),
    }
    regions = result.get("raw_transfers", {})
    for name, expected in expected_regions.items():
        region = regions.get(name, {})
        actual = (region.get("width"), region.get("height"),
                  region.get("coverage_percent"), region.get("submission"))
        if actual != expected:
            raise ValueError(f"benchmark region {name} is not locked")


def percentile(values: list[int | float], percentage: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot summarize an empty sample")
    position = (len(ordered) - 1) * percentage
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def sample_summary(values: list[int | float]) -> dict:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return {"samples": 0}
    return {
        "samples": len(numeric),
        "minimum": min(numeric),
        "median": statistics.median(numeric),
        "p95": round(percentile(numeric, 0.95), 3),
        "maximum": max(numeric),
    }


def summarize_result(result: dict) -> dict:
    validate_result(result)
    raw = {}
    for name, region in result["raw_transfers"].items():
        raw[name] = {
            "transfer_us": sample_summary(region["transfer_us"]),
            "throughput_bytes_per_second": sample_summary(
                region["throughput_bytes_per_second"]),
            "missed_deadlines": region["missed_deadlines"],
            "deadline_us": region["deadline_us"],
        }
    workloads = {}
    for name, total_key in (
            ("solid_fills", "total_frame_us"),
            ("sprite", "total_frame_us"),
            ("scroll", "total_frame_us"),
            ("ui_widgets", "total_frame_us")):
        workload = result[name]
        workloads[name] = {
            "total_us": sample_summary(workload[total_key]),
            "render_us": sample_summary(workload.get(
                "render_us", workload.get("render_or_combined_us", []))),
            "transfer_us": sample_summary(workload.get(
                "transfer_us", workload.get("transfer_baseline_us", []))),
            "overlap_us": sample_summary(workload.get(
                "overlap_us", workload.get("overlap_estimate_us", []))),
            "missed_deadlines": workload["missed_deadlines"],
            "deadline_us": workload["deadline_us"],
        }
    animation = result["lvgl_animation"]
    if animation["supported"]:
        animation_summary = {
            "supported": True,
            "duration_ms": animation["duration_ms"],
            "frames_with_display_transfer": animation[
                "frames_with_display_transfer"],
            "samples_with_running_animation": sum(
                1 for value in animation["running_animation_counts"]
                if value is not None and value > 0),
            "total_us": sample_summary(
                animation["total_frame_us_excluding_17ms_cadence_sleep"]),
            "transfer_us": sample_summary(animation["transfer_us"]),
            "missed_deadlines": animation["missed_deadlines"],
        }
    else:
        animation_summary = animation
    return {
        "profile": result["profile"],
        "runtime": result["runtime"],
        "matrix": result["matrix"],
        "raw_transfers": raw,
        "workloads": workloads,
        "lvgl_animation": animation_summary,
        "cpu_availability": result["cpu_availability"],
        "heap": result["heap"],
        "mode_switches": {
            "total_us": sample_summary(result["mode_switches"]["total_us"]),
            "heap_free_delta_first_to_last": result["mode_switches"][
                "heap_free_delta_first_to_last"],
            "heap_allocated_delta_first_to_last": result["mode_switches"][
                "heap_allocated_delta_first_to_last"],
            "benchmark_owned_allocations_during_loop": result[
                "mode_switches"]["benchmark_owned_allocations_during_loop"],
        },
    }


def validate_comparable(legacy: dict, modern: dict) -> None:
    validate_result(legacy, "legacy")
    validate_result(modern, "modern")
    _validate_same_matrix(legacy, modern)


def _validate_same_matrix(left: dict, right: dict) -> None:
    locked_keys = (
        "logical_width", "logical_height", "color_format",
        "full_frame_bytes", "transport_rows", "raw_transport_buffer_count",
        "pipeline_buffer_count", "samples", "mode_switches", "asset_sha256",
    )
    for key in locked_keys:
        if left["matrix"].get(key) != right["matrix"].get(key):
            raise ValueError(f"benchmark matrix differs for {key}")
    for key in ("machine_frequency_hz", "configured_display_spi_hz"):
        if left["runtime"].get(key) != right["runtime"].get(key):
            raise ValueError(f"benchmark clocks differ for {key}")
    for name in left["raw_transfers"]:
        for key in ("width", "height", "coverage_percent", "bytes",
                    "deadline_us", "asset_sha256", "submission"):
            if (left["raw_transfers"][name].get(key) !=
                    right["raw_transfers"][name].get(key)):
                raise ValueError(f"benchmark region differs for {name}.{key}")
    if left["sprite"]["asset_sha256"] != right["sprite"]["asset_sha256"]:
        raise ValueError("sprite assets differ")
    if left["scroll"]["asset_sha256"] != right["scroll"]["asset_sha256"]:
        raise ValueError("scroll assets differ")


def alternative_comparison(reference: dict, alternative: dict) -> dict:
    """Compare the two modern stacks without relabeling either as production."""
    validate_result(reference, "modern")
    validate_result(alternative, "pydevices")
    _validate_same_matrix(reference, alternative)
    summaries = {
        "lcd_bus_reference": summarize_result(reference),
        "pydevices_displayif": summarize_result(alternative),
    }
    ratios = {"raw_transfer_median_pydevices_over_reference": {}}
    for name in reference["raw_transfers"]:
        reference_median = statistics.median(
            reference["raw_transfers"][name]["transfer_us"])
        alternative_median = statistics.median(
            alternative["raw_transfers"][name]["transfer_us"])
        ratios["raw_transfer_median_pydevices_over_reference"][name] = round(
            alternative_median / reference_median, 6)
    for name in ("solid_fills", "sprite", "scroll", "ui_widgets"):
        reference_median = statistics.median(
            reference[name]["total_frame_us"])
        alternative_median = statistics.median(
            alternative[name]["total_frame_us"])
        ratios[name + "_total_median_pydevices_over_reference"] = round(
            alternative_median / reference_median, 6)
    ratios["mode_switch_median_pydevices_over_reference"] = round(
        statistics.median(alternative["mode_switches"]["total_us"]) /
        statistics.median(reference["mode_switches"]["total_us"]),
        6,
    )
    return {
        "schema": SCHEMA,
        "kind": "phase5-modern-stack-comparison",
        "matrix_validated": True,
        "production_selected": False,
        "profiles": summaries,
        "ratios": ratios,
        "transport_observation": {
            "lcd_bus_reference_async": reference["matrix"].get(
                "direct_transfer_async", True),
            "pydevices_displayif_async": alternative["matrix"].get(
                "direct_transfer_async", False),
            "lcd_bus_reference_cpu_availability_percent": round(
                reference["cpu_availability"]["iterations_during_transfer"] /
                reference["cpu_availability"][
                    "baseline_iterations_same_interval"] * 100,
                3,
            ),
            "pydevices_displayif_cpu_availability_percent": round(
                alternative["cpu_availability"][
                    "iterations_during_transfer"] /
                alternative["cpu_availability"][
                    "baseline_iterations_same_interval"] * 100,
                3,
            ),
        },
    }


def comparison(legacy: dict, modern: dict) -> dict:
    validate_comparable(legacy, modern)
    summaries = {
        "legacy": summarize_result(legacy),
        "modern": summarize_result(modern),
    }
    ratios = {"raw_transfer_median_modern_over_legacy": {}}
    for name in legacy["raw_transfers"]:
        legacy_median = statistics.median(
            legacy["raw_transfers"][name]["transfer_us"])
        modern_median = statistics.median(
            modern["raw_transfers"][name]["transfer_us"])
        ratios["raw_transfer_median_modern_over_legacy"][name] = round(
            modern_median / legacy_median, 6)
    for name in ("solid_fills", "sprite", "scroll", "ui_widgets"):
        legacy_median = statistics.median(legacy[name]["total_frame_us"])
        modern_median = statistics.median(modern[name]["total_frame_us"])
        ratios[name + "_total_median_modern_over_legacy"] = round(
            modern_median / legacy_median, 6)
    return {
        "schema": SCHEMA,
        "kind": "phase5-comparative-hardware-benchmark",
        "matrix_validated": True,
        "profiles": summaries,
        "ratios": ratios,
        "limitations": [
            "Raw REPL collection pauses the foreground IDE server; the CPU "
            "availability result is a service-headroom proxy, not live HTTP latency.",
            "The qualified legacy UI performs synchronous rendering and transfer "
            "inside one call, so that profile has no non-invasive UI timing split.",
            "MicroPython exposes allocated bytes but no allocation-event counter; "
            "the harness instruments its own steady-state allocations and GC bytes.",
            "LVGL animation has no legacy result because the qualified legacy "
            "firmware does not contain LVGL.",
        ],
    }


def collect(args: argparse.Namespace) -> None:
    program = device_program(args.samples, args.switches, args.profile)
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(program, max(args.timeout, 180))
    finally:
        repl.close()
    result = extract_result(output)
    validate_result(result, args.profile)
    result["collection"] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "tool": "tools/phase5_benchmark.py",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summarize_result(result), indent=2, sort_keys=True))
    print(f"Raw {args.profile} result written to {args.output}", file=sys.stderr)


def compare(args: argparse.Namespace) -> None:
    legacy = json.loads(args.legacy.read_text(encoding="utf-8"))
    modern = json.loads(args.modern.read_text(encoding="utf-8"))
    result = comparison(legacy, modern)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Comparison written to {args.output}", file=sys.stderr)
    print(rendered, end="")


def compare_alternative(args: argparse.Namespace) -> None:
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    alternative = json.loads(args.alternative.read_text(encoding="utf-8"))
    result = alternative_comparison(reference, alternative)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Alternative comparison written to {args.output}",
              file=sys.stderr)
    print(rendered, end="")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--port", default="COM3")
    collect_parser.add_argument("--baudrate", type=int, default=115200)
    collect_parser.add_argument("--timeout", type=int, default=30)
    collect_parser.add_argument("--profile", choices=PROFILES, required=True)
    collect_parser.add_argument("--samples", type=int, default=12)
    collect_parser.add_argument("--switches", type=int, default=25)
    collect_parser.add_argument("--output", type=Path, required=True)
    collect_parser.set_defaults(func=collect)

    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--legacy", type=Path, required=True)
    compare_parser.add_argument("--modern", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path)
    compare_parser.set_defaults(func=compare)

    alternative_parser = commands.add_parser("compare-alternative")
    alternative_parser.add_argument("--reference", type=Path, required=True)
    alternative_parser.add_argument("--alternative", type=Path, required=True)
    alternative_parser.add_argument("--output", type=Path)
    alternative_parser.set_defaults(func=compare_alternative)
    return result


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TimeoutError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
