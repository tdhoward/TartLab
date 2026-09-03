"""Diagnose modern dirty-region drawing costs without changing the device.

The device program is executed temporarily through raw REPL. It does not
flash firmware or write to the device filesystem.
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
except ImportError:  # Allow import as ``tools.drawing_diagnostics``.
    from tools.phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
MARKER = "DRAWING_DIAGNOSTICS"
SCHEMA = 1
STAGE_CASES = (
    "direct_piece", "direct_text", "portrait_piece", "portrait_text")
SHAPES = ("wide_144x36", "square_72x72", "tall_36x144")
TEXT_VARIANTS = (
    "direct_native", "portrait_current", "portrait_reused_mask",
    "portrait_cached_sprite")
EMITTER_SWAP_SIZES = (128, 2048, 32_768, 213_120)


DEVICE_PROGRAM = r'''
import gc, machine, micropython, os, sys, time, ujson
for search_path in reversed(('/device', '/lib', '/', '/files/user')):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)
_MODERN_APP_SOURCE = __MODERN_APP_SOURCE__
_MODERN_EMITTER_SOURCE = __MODERN_EMITTER_SOURCE__
import tartlabutils.modern_app as _working_modern_app
exec(_MODERN_EMITTER_SOURCE, _working_modern_app.__dict__)
exec(_MODERN_APP_SOURCE, _working_modern_app.__dict__)
from framebuf import FrameBuffer, MONO_HLSB, RGB565
from tartlabutils.modern_app import DirectCanvas, PortraitCanvas, game_surface
from tartlabutils.platform import get_platform

SAMPLES = __SAMPLES__
BLACK = 0
WHITE = 65535
BLOCK_SIZE = 18
TEXT_WIDTH = 144
TEXT_HEIGHT = 36

def ticks():
    return time.ticks_us()

def elapsed(started):
    return time.ticks_diff(ticks(), started)

def average(values):
    return (sum(values) + len(values) // 2) // len(values)

platform = get_platform()
if not platform.capabilities.get('direct_rgb565', False):
    raise RuntimeError('drawing diagnostics require a modern device')
surface = game_surface()

class TimingSurface:
    def __init__(self, target):
        self.target = target
        self.width = target.width
        self.height = target.height
        self.color_format = target.color_format
        self.allocations = 0
        self.frees = 0
        self.reset()

    def reset(self):
        self.submit_us = []
        self.wait_us = []
        self.regions = []

    def allocate_buffer(self, width, height):
        self.allocations += 1
        return self.target.allocate_buffer(width, height)

    def free_buffer(self, buffer):
        self.frees += 1
        return self.target.free_buffer(buffer)

    def write(self, buffer, x, y, width, height):
        started = ticks()
        self.target.write(buffer, x, y, width, height, wait=False)
        self.submit_us.append(elapsed(started))
        started = ticks()
        self.target.wait()
        self.wait_us.append(elapsed(started))
        self.regions.append((x, y, width, height))

timing_surface = TimingSurface(surface)

def make_block(index):
    data = bytearray(BLOCK_SIZE * BLOCK_SIZE * 2)
    block = FrameBuffer(data, BLOCK_SIZE, BLOCK_SIZE, RGB565)
    block.fill(BLACK)
    if index:
        block.fill_rect(1, 1, BLOCK_SIZE - 2, BLOCK_SIZE - 2, WHITE)
        inset = 2 + index % 5
        block.fill_rect(inset, inset,
                        BLOCK_SIZE - inset * 2,
                        BLOCK_SIZE - inset * 2, BLACK)
    return data, block

def make_blocks(canvas):
    blocks = []
    for index in range(8):
        data, block = make_block(index)
        blocks.append((data, canvas.prepare_sprite(
            block, BLOCK_SIZE, BLOCK_SIZE)))
    return blocks

def record_stages(canvas, render, area):
    render(0)
    canvas.show(area)
    result = {
        'render_us': [], 'pack_and_loop_us': [], 'submit_us': [],
        'wait_us': [], 'show_us': [], 'total_us': [], 'transfers': [],
    }
    for sample in range(SAMPLES):
        gc.collect()
        started = ticks()
        render(sample + 1)
        render_us = elapsed(started)
        timing_surface.reset()
        started = ticks()
        canvas.show(area)
        show_us = elapsed(started)
        submit_us = sum(timing_surface.submit_us)
        wait_us = sum(timing_surface.wait_us)
        pack_us = show_us - submit_us - wait_us
        if pack_us < 0:
            pack_us = 0
        result['render_us'].append(render_us)
        result['pack_and_loop_us'].append(pack_us)
        result['submit_us'].append(submit_us)
        result['wait_us'].append(wait_us)
        result['show_us'].append(show_us)
        result['total_us'].append(render_us + show_us)
        result['transfers'].append(len(timing_surface.regions))
    return result

direct = DirectCanvas(timing_surface)
portrait = PortraitCanvas(timing_surface)
direct_blocks = make_blocks(direct)
portrait_blocks = make_blocks(portrait)

def piece_renderer(canvas, blocks, portrait_mode):
    grid_width = 10 if portrait_mode else 20
    grid_height = 20 if portrait_mode else 10
    field_width = grid_width * BLOCK_SIZE
    field_height = grid_height * BLOCK_SIZE
    logical_width = canvas.width if portrait_mode else surface.width
    logical_height = canvas.height if portrait_mode else surface.height
    field_x = (logical_width - field_width) // 2
    field_y = (logical_height - field_height) // 2
    piece_y = (grid_height - 2) // 2

    def draw(frame):
        old_x = 3 if frame & 1 else 4
        new_x = 4 if frame & 1 else 3
        for y in range(2):
            for x in range(2):
                canvas.draw_sprite(
                    blocks[0][1],
                    field_x + (old_x + x) * BLOCK_SIZE,
                    field_y + (piece_y + y) * BLOCK_SIZE)
                canvas.draw_sprite(
                    blocks[frame % 7 + 1][1],
                    field_x + (new_x + x) * BLOCK_SIZE,
                    field_y + (piece_y + y) * BLOCK_SIZE)

    area = (field_x + 3 * BLOCK_SIZE,
            field_y + piece_y * BLOCK_SIZE,
            3 * BLOCK_SIZE, 2 * BLOCK_SIZE)
    return draw, area

TEXT_LINES = ('Frame: 1234', 'Score: 1,234', 'Drop: 1000 ms')

def text_renderer(canvas, portrait_mode):
    logical_width = canvas.width if portrait_mode else surface.width
    logical_height = canvas.height if portrait_mode else surface.height
    text_x = (logical_width - TEXT_WIDTH) // 2
    text_y = (logical_height - TEXT_HEIGHT) // 2

    def draw(unused_frame):
        canvas.fill_rect(
            text_x, text_y, TEXT_WIDTH, TEXT_HEIGHT, BLACK)
        for index, value in enumerate(TEXT_LINES):
            canvas.text(value, text_x, text_y + 4 + index * 8, WHITE)

    return draw, (text_x, text_y, TEXT_WIDTH, TEXT_HEIGHT)

direct_piece, direct_piece_area = piece_renderer(
    direct, direct_blocks, False)
portrait_piece, portrait_piece_area = piece_renderer(
    portrait, portrait_blocks, True)
direct_text, direct_text_area = text_renderer(direct, False)
portrait_text, portrait_text_area = text_renderer(portrait, True)

stages = {
    'direct_piece': record_stages(
        direct, direct_piece, direct_piece_area),
    'direct_text': record_stages(
        direct, direct_text, direct_text_area),
    'portrait_piece': record_stages(
        portrait, portrait_piece, portrait_piece_area),
    'portrait_text': record_stages(
        portrait, portrait_text, portrait_text_area),
}

def fill_buffer(buffer):
    view = memoryview(buffer)
    for offset in range(0, len(view), 2):
        view[offset] = 255
        view[offset + 1] = 255

def record_shape(width, height):
    x = 12
    y = 12
    direct.fill_rect(x, y, width, height, WHITE)
    direct.show((x, y, width, height))
    tiled_total_us = []
    tiled_pack_us = []
    tiled_submit_us = []
    tiled_wait_us = []
    tiled_transfers = []
    for unused in range(SAMPLES):
        timing_surface.reset()
        started = ticks()
        direct.show((x, y, width, height))
        total_us = elapsed(started)
        submit_us = sum(timing_surface.submit_us)
        wait_us = sum(timing_surface.wait_us)
        pack_us = total_us - submit_us - wait_us
        if pack_us < 0:
            pack_us = 0
        tiled_total_us.append(total_us)
        tiled_pack_us.append(pack_us)
        tiled_submit_us.append(submit_us)
        tiled_wait_us.append(wait_us)
        tiled_transfers.append(len(timing_surface.regions))

    raw = surface.allocate_buffer(width, height)
    fill_buffer(raw)
    raw_total_us = []
    raw_submit_us = []
    raw_wait_us = []
    try:
        timing_surface.write(raw, x, y, width, height)
        for unused in range(SAMPLES):
            timing_surface.reset()
            started = ticks()
            timing_surface.write(raw, x, y, width, height)
            raw_total_us.append(elapsed(started))
            raw_submit_us.append(sum(timing_surface.submit_us))
            raw_wait_us.append(sum(timing_surface.wait_us))
    finally:
        surface.free_buffer(raw)
    return {
        'width': width, 'height': height,
        'bytes': width * height * 2,
        'tiled_total_us': tiled_total_us,
        'tiled_pack_us': tiled_pack_us,
        'tiled_submit_us': tiled_submit_us,
        'tiled_wait_us': tiled_wait_us,
        'tiled_transfers': tiled_transfers,
        'raw_total_us': raw_total_us,
        'raw_submit_us': raw_submit_us,
        'raw_wait_us': raw_wait_us,
        'raw_transfers': [1] * SAMPLES,
    }

shapes = {
    'wide_144x36': record_shape(144, 36),
    'square_72x72': record_shape(72, 72),
    'tall_36x144': record_shape(36, 144),
}

mask_data = bytearray(TEXT_WIDTH)
mask = FrameBuffer(mask_data, TEXT_WIDTH, 8, MONO_HLSB)

def reused_mask_text(unused_frame):
    text_x = (portrait.width - TEXT_WIDTH) // 2
    text_y = (portrait.height - TEXT_HEIGHT) // 2
    portrait.fill_rect(
        text_x, text_y, TEXT_WIDTH, TEXT_HEIGHT, BLACK)
    for index, value in enumerate(TEXT_LINES):
        mask.fill(0)
        mask.text(value, 0, 0, 1)
        width = len(value) * 8
        for glyph_y in range(8):
            for glyph_x in range(width):
                if mask.pixel(glyph_x, glyph_y):
                    portrait.pixel(
                        text_x + glyph_x,
                        text_y + 4 + index * 8 + glyph_y, WHITE)

sprite_data = bytearray(TEXT_WIDTH * TEXT_HEIGHT * 2)
sprite_framebuffer = FrameBuffer(
    sprite_data, TEXT_WIDTH, TEXT_HEIGHT, RGB565)
sprite_framebuffer.fill(BLACK)
for index, value in enumerate(TEXT_LINES):
    sprite_framebuffer.text(value, 0, 4 + index * 8, WHITE)
cached_text = portrait.prepare_sprite(
    sprite_framebuffer, TEXT_WIDTH, TEXT_HEIGHT)

def cached_sprite_text(unused_frame):
    text_x = (portrait.width - TEXT_WIDTH) // 2
    text_y = (portrait.height - TEXT_HEIGHT) // 2
    portrait.fill_rect(
        text_x, text_y, TEXT_WIDTH, TEXT_HEIGHT, BLACK)
    portrait.draw_sprite(cached_text, text_x, text_y)

def render_samples(draw):
    values = []
    draw(0)
    for sample in range(SAMPLES):
        gc.collect()
        started = ticks()
        draw(sample + 1)
        values.append(elapsed(started))
    return values

text_rendering = {
    'direct_native': render_samples(direct_text),
    'portrait_current': render_samples(portrait_text),
    'portrait_reused_mask': render_samples(reused_mask_text),
    'portrait_cached_sprite': render_samples(cached_sprite_text),
}

def python_swap(buffer, size):
    view = memoryview(buffer)
    for offset in range(0, size, 2):
        view[offset], view[offset + 1] = view[offset + 1], view[offset]

@micropython.native
def native_swap(buffer, size):
    view = memoryview(buffer)
    for offset in range(0, size, 2):
        view[offset], view[offset + 1] = view[offset + 1], view[offset]

def swap_correct(function):
    buffer = bytearray(range(32))
    expected = bytearray(32)
    for offset in range(0, 32, 2):
        expected[offset] = buffer[offset + 1]
        expected[offset + 1] = buffer[offset]
    function(buffer, len(buffer))
    return buffer == expected

def public_viper_swap(buffer, unused_size):
    _working_modern_app.swap565_buffer(buffer)

def swap_samples(function, size, repeats):
    buffer = bytearray(size)
    values = []
    for unused_sample in range(SAMPLES):
        gc.collect()
        started = ticks()
        for unused_repeat in range(repeats):
            function(buffer, size)
            function(buffer, size)
        values.append(elapsed(started) // (repeats * 2))
    return values

swap_sizes = __EMITTER_SWAP_SIZES__
swap_repeats = (50, 10, 2, 1)
byte_swap = {}
for index in range(len(swap_sizes)):
    size = swap_sizes[index]
    repeats = swap_repeats[index]
    byte_swap[str(size)] = {
        'repeats': repeats,
        'python_us': swap_samples(python_swap, size, repeats),
        'native_us': swap_samples(native_swap, size, repeats),
        'viper_us': swap_samples(public_viper_swap, size, repeats),
    }

FILL_WIDTH = 480
FILL_HEIGHT = 16
FILL_COLOR = 0x34AB

def python_fill(buffer):
    view = memoryview(buffer)
    high = (FILL_COLOR >> 8) & 0xFF
    low = FILL_COLOR & 0xFF
    for offset in range(0, len(view), 2):
        view[offset] = high
        view[offset + 1] = low

def compiled_fill(buffer):
    FrameBuffer(buffer, FILL_WIDTH, FILL_HEIGHT, RGB565).fill(
        _working_modern_app.framebuffer_color(FILL_COLOR))

def fill_samples(function):
    buffer = bytearray(FILL_WIDTH * FILL_HEIGHT * 2)
    values = []
    for unused_sample in range(SAMPLES):
        gc.collect()
        started = ticks()
        function(buffer)
        values.append(elapsed(started))
    return values, list(buffer[:8])

python_fill_us, python_fill_head = fill_samples(python_fill)
compiled_fill_us, compiled_fill_head = fill_samples(compiled_fill)
emitters = {
    'byte_swap': byte_swap,
    'byte_swap_correct': [
        swap_correct(python_swap),
        swap_correct(native_swap),
        swap_correct(public_viper_swap),
    ],
    'fill_tile': {
        'bytes': FILL_WIDTH * FILL_HEIGHT * 2,
        'python_us': python_fill_us,
        'compiled_us': compiled_fill_us,
        'same_prefix': python_fill_head == compiled_fill_head,
    },
}

direct.close()
portrait.close()
lifecycle_heap = []
for unused in range(10):
    lifecycle_canvas = DirectCanvas(timing_surface)
    lifecycle_canvas.fill(BLACK)
    lifecycle_canvas.show((0, 0, 1, 1))
    lifecycle_canvas.close()
    del lifecycle_canvas
    gc.collect()
    lifecycle_heap.append(gc.mem_free())
platform.enter_ui_mode()
lifecycle = {
    'iterations': 10,
    'allocation_balance': timing_surface.allocations - timing_surface.frees,
    'heap_free': lifecycle_heap,
    'final_owner': platform.controller.owner,
    'transfer_pending': platform.controller.transfer_pending,
}

result = {
    'schema': 1,
    'profile': 'modern',
    'runtime': {
        'sys_version': sys.version,
        'implementation': repr(sys.implementation),
        'uname': repr(os.uname()),
        'machine_frequency_hz': machine.freq(),
        'display_class': type(platform.display).__name__,
    },
    'matrix': {
        'samples': SAMPLES,
        'transfer_rows': 16,
        'equal_area_bytes': 10368,
        'text_width': TEXT_WIDTH,
        'text_height': TEXT_HEIGHT,
    },
    'stages': stages,
    'shapes': shapes,
    'text_rendering': text_rendering,
    'emitters': emitters,
    'lifecycle': lifecycle,
}
print('DRAWING_DIAGNOSTICS=' + ujson.dumps(result))
'''


def device_program(samples: int) -> str:
    if samples < 3:
        raise ValueError("samples must be at least 3")
    modern_app_source = (ROOT / "src/lib/tartlabutils/modern_app.py").read_text(
        encoding="utf-8")
    emitter_source = (ROOT / "src/lib/tartlabutils/_modern_emitters.py").read_text(
        encoding="utf-8")
    modern_app_source = modern_app_source.replace(
        "from ._modern_emitters import swap565 as _swap565_viper",
        "_swap565_viper = swap565")
    return (DEVICE_PROGRAM
            .replace("__SAMPLES__", str(samples))
            .replace("__MODERN_APP_SOURCE__", repr(modern_app_source))
            .replace("__MODERN_EMITTER_SOURCE__", repr(emitter_source))
            .replace("__EMITTER_SWAP_SIZES__", repr(EMITTER_SWAP_SIZES)))


def extract_result(output: bytes) -> dict:
    prefix = MARKER + "="
    decoded = output.decode("utf-8", "replace")
    for line in decoded.splitlines():
        if line.startswith(prefix):
            value = json.loads(line[len(prefix):])
            if isinstance(value, dict):
                return value
    raise ValueError(f"device output did not contain {MARKER}")


def _positive_samples(value: object, samples: int, label: str,
                      allow_zero: bool = False) -> None:
    if not isinstance(value, list) or len(value) != samples:
        raise ValueError(f"invalid samples for {label}")
    for item in value:
        if (not isinstance(item, (int, float))
                or (item < 0 if allow_zero else item <= 0)):
            raise ValueError(f"invalid samples for {label}")


def validate_result(result: dict) -> None:
    if result.get("schema") != SCHEMA or result.get("profile") != "modern":
        raise ValueError("diagnostics require the modern schema")
    matrix = result.get("matrix", {})
    samples = matrix.get("samples")
    if not isinstance(samples, int) or samples < 3:
        raise ValueError("diagnostics require at least three samples")
    if (matrix.get("transfer_rows"), matrix.get("equal_area_bytes"),
            matrix.get("text_width"), matrix.get("text_height")) != (
            16, 10_368, 144, 36):
        raise ValueError("diagnostic matrix differs")
    stages = result.get("stages", {})
    if set(stages) != set(STAGE_CASES):
        raise ValueError("diagnostic stage cases differ")
    for case in STAGE_CASES:
        item = stages[case]
        for metric in ("render_us", "submit_us", "wait_us", "show_us",
                       "total_us", "transfers"):
            _positive_samples(item.get(metric), samples, case + "." + metric)
        _positive_samples(item.get("pack_and_loop_us"), samples,
                          case + ".pack_and_loop_us", allow_zero=True)
    shapes = result.get("shapes", {})
    if set(shapes) != set(SHAPES):
        raise ValueError("diagnostic shapes differ")
    for shape in SHAPES:
        item = shapes[shape]
        if item.get("bytes") != 10_368:
            raise ValueError("diagnostic shape byte count differs")
        for metric in ("tiled_total_us", "tiled_submit_us", "tiled_wait_us",
                       "tiled_transfers", "raw_total_us", "raw_submit_us",
                       "raw_wait_us", "raw_transfers"):
            _positive_samples(item.get(metric), samples, shape + "." + metric)
        _positive_samples(item.get("tiled_pack_us"), samples,
                          shape + ".tiled_pack_us", allow_zero=True)
    text = result.get("text_rendering", {})
    if set(text) != set(TEXT_VARIANTS):
        raise ValueError("diagnostic text variants differ")
    for variant in TEXT_VARIANTS:
        _positive_samples(text[variant], samples, "text." + variant)
    emitters = result.get("emitters", {})
    if emitters.get("byte_swap_correct") != [True, True, True]:
        raise ValueError("emitter byte-swap output differs")
    byte_swap = emitters.get("byte_swap", {})
    if set(byte_swap) != {str(size) for size in EMITTER_SWAP_SIZES}:
        raise ValueError("emitter byte-swap sizes differ")
    for size in EMITTER_SWAP_SIZES:
        item = byte_swap[str(size)]
        if not isinstance(item.get("repeats"), int) or item["repeats"] < 1:
            raise ValueError("invalid emitter repeats")
        for metric in ("python_us", "native_us", "viper_us"):
            _positive_samples(
                item.get(metric), samples,
                "emitters.byte_swap.%s.%s" % (size, metric))
    fill_tile = emitters.get("fill_tile", {})
    if (fill_tile.get("bytes") != 15_360 or
            fill_tile.get("same_prefix") is not True):
        raise ValueError("emitter fill output differs")
    for metric in ("python_us", "compiled_us"):
        _positive_samples(
            fill_tile.get(metric), samples, "emitters.fill_tile." + metric)
    lifecycle = result.get("lifecycle", {})
    if (lifecycle.get("iterations") != 10
            or lifecycle.get("allocation_balance") != 0
            or lifecycle.get("final_owner") != "ui"
            or lifecycle.get("transfer_pending") is not False):
        raise ValueError("diagnostic lifecycle result differs")
    _positive_samples(lifecycle.get("heap_free"), 10, "lifecycle.heap_free")


def median_ms(values: list[int | float]) -> float:
    return statistics.median(values) / 1000


def render_section(result: dict) -> str:
    validate_result(result)
    stage_labels = {
        "direct_piece": "DirectCanvas piece",
        "direct_text": "DirectCanvas text",
        "portrait_piece": "PortraitCanvas piece",
        "portrait_text": "PortraitCanvas text",
    }
    stage_rows = []
    for case in STAGE_CASES:
        item = result["stages"][case]
        stage_rows.append(
            "| %s | %.2f | %.2f | %.2f | %.2f | %.0f | %.2f |" % (
                stage_labels[case], median_ms(item["render_us"]),
                median_ms(item["pack_and_loop_us"]),
                median_ms(item["submit_us"]), median_ms(item["wait_us"]),
                statistics.median(item["transfers"]),
                median_ms(item["total_us"])))

    shape_rows = []
    for shape in SHAPES:
        item = result["shapes"][shape]
        shape_rows.append(
            "| %s x %s | %.0f | %.2f | %.2f | %.1fx |" % (
                item["width"], item["height"],
                statistics.median(item["tiled_transfers"]),
                median_ms(item["tiled_total_us"]),
                median_ms(item["raw_total_us"]),
                statistics.median(item["tiled_total_us"]) /
                statistics.median(item["raw_total_us"])))

    text_labels = {
        "direct_native": "DirectCanvas native text",
        "portrait_current": "PortraitCanvas current text",
        "portrait_reused_mask": "PortraitCanvas reusable mask",
        "portrait_cached_sprite": "PortraitCanvas cached sprite",
    }
    text_rows = [
        "| %s | %.2f |" % (
            text_labels[key], median_ms(result["text_rendering"][key]))
        for key in TEXT_VARIANTS
    ]
    emitters = result["emitters"]
    swap_rows = []
    for size in EMITTER_SWAP_SIZES:
        item = emitters["byte_swap"][str(size)]
        python_us = statistics.median(item["python_us"])
        native_us = statistics.median(item["native_us"])
        viper_us = statistics.median(item["viper_us"])
        swap_rows.append(
            "| %s | %.0f | %.0f | %.0f | %.1fx |" % (
                f"{size:,}", python_us, native_us, viper_us,
                python_us / viper_us))
    fill_tile = emitters["fill_tile"]
    fill_python_us = statistics.median(fill_tile["python_us"])
    fill_compiled_us = statistics.median(fill_tile["compiled_us"])
    pack_shares = []
    for case in STAGE_CASES:
        item = result["stages"][case]
        pack_shares.append(
            statistics.median(item["pack_and_loop_us"]) /
            statistics.median(item["show_us"]) * 100)
    wide = result["shapes"]["wide_144x36"]
    tall = result["shapes"]["tall_36x144"]
    shape_ratio = (statistics.median(tall["tiled_total_us"]) /
                   statistics.median(wide["tiled_total_us"]))
    raw_medians = [
        statistics.median(result["shapes"][key]["raw_total_us"])
        for key in SHAPES
    ]
    text = result["text_rendering"]
    portrait_over_direct = (
        statistics.median(text["portrait_current"]) /
        statistics.median(text["direct_native"]))
    current_over_cached = (
        statistics.median(text["portrait_current"]) /
        statistics.median(text["portrait_cached_sprite"]))
    reused_over_current = (
        statistics.median(text["portrait_reused_mask"]) /
        statistics.median(text["portrait_current"]))
    collected = result.get("collection", {}).get("collected_at", "unknown")
    lifecycle = result["lifecycle"]
    heap_change = lifecycle["heap_free"][-1] - lifecycle["heap_free"][0]
    return "\n".join((
        "## Modern slowdown experiments",
        "",
        "All values are medians in milliseconds. The stage experiment separates",
        "framebuffer rendering from `DirectCanvas.show()` row packing, transfer",
        "submission, and synchronous waiting.",
        "",
        "| Case | Render | Pack/loop | Submit | Wait | Transfers | Total |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *stage_rows,
        "",
        "The shape experiment transfers 10,368 bytes in every row. Tiled uses the",
        "canvas's 15,360-byte bounce buffer with adaptive row counts; raw uses one",
        "prepacked `surface.write()`.",
        "",
        "| Physical shape | Tiled transfers | Tiled total | One raw write | Ratio |",
        "| --- | ---: | ---: | ---: | ---: |",
        *shape_rows,
        "",
        "The text experiment measures rendering only, with no display transfer.",
        "The reusable-mask case removes per-line mask allocation while retaining",
        "Python pixel rotation. The cached-sprite case rotates once before timing.",
        "",
        "| Text renderer | Render time |",
        "| --- | ---: |",
        *text_rows,
        "",
        "### Phase 4 emitter experiments",
        "",
        "Byte swapping compares the Python reference, a rejected `native`",
        "candidate, and the validated private Viper path. Times are microseconds.",
        "",
        "| Buffer bytes | Python | Native | Viper | Python/Viper |",
        "| ---: | ---: | ---: | ---: | ---: |",
        *swap_rows,
        "",
        "The 15,360-byte transfer-tile fill took %.0f us in Python and %.0f us" % (
            fill_python_us, fill_compiled_us),
        "with compiled `framebuf.fill()` (%.1fx faster), with matching bytes." % (
            fill_python_us / fill_compiled_us),
        "",
        "### Findings",
        "",
        "- Row packing and loop overhead accounts for %.0f%% to %.0f%% of the" % (
            min(pack_shares), max(pack_shares)),
        "  measured `show()` time in all four slow cases.",
        "- With byte count held constant, the 36 x 144 tiled region took %.1fx" %
        shape_ratio,
        "  as long as the 144 x 36 region. The single-write medians stayed between",
        "  %.2f and %.2f ms, showing that pixel count and the native transfer are" % (
            min(raw_medians) / 1000, max(raw_medians) / 1000),
        "  not the source of that shape-dependent slowdown.",
        "- Current portrait text rendering took %.1fx the native landscape text" %
        portrait_over_direct,
        "  path. Reusing the glyph mask changed the median by only %+.1f%%, while a" %
        ((reused_over_current - 1) * 100),
        "  pre-rotated sprite was %.1fx faster. The Python per-pixel rotation loop," %
        current_over_cached,
        "  rather than mask allocation, is the portrait rendering bottleneck.",
        "- Ten construct/show/close cycles ended with allocation balance %d," %
        lifecycle["allocation_balance"],
        "  owner `%s`, no pending transfer, and heap change %+d bytes." % (
            lifecycle["final_owner"], heap_change),
        "",
        f"Diagnostics collected: `{collected}`",
        "",
    ))


def collect(args: argparse.Namespace) -> None:
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(device_program(args.samples), max(args.timeout, 180))
    finally:
        repl.close()
    result = extract_result(output)
    validate_result(result)
    result["collection"] = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "tool": "tools/drawing_diagnostics.py",
        "device_writes": False,
        "firmware_flash": False,
        "modern_app_source": "working_tree_in_memory",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Raw diagnostics written to {args.output}", file=sys.stderr)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--port", default="COM3")
    result.add_argument("--baudrate", type=int, default=115200)
    result.add_argument("--timeout", type=int, default=30)
    result.add_argument("--samples", type=int, default=7)
    result.add_argument(
        "--output", type=Path,
        default=Path("hardware_test_artifacts/drawing-performance/"
                     "modern-diagnostics.json"))
    return result


def main() -> int:
    args = parser().parse_args()
    collect(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, TimeoutError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
