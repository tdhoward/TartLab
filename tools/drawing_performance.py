"""Collect a small canvas/display-driver benchmark without flashing firmware.

The collect command sends a temporary program to the device's raw REPL. It
does not copy files to the device, update its filesystem, or invoke a firmware
flashing tool. Raw JSON is stored on the host so that results remain auditable.
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
except ImportError:  # Allow import as ``tools.drawing_performance`` in tests.
    from tools.phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
MARKER = "DRAWING_PERFORMANCE"
SCHEMA = 1
PROFILES = ("legacy", "modern")
WORKLOADS = ("full_grid", "piece_move", "text_redraw")
IMPLEMENTATIONS = {
    "legacy": ("display_drv_landscape", "display_drv_portrait"),
    "modern": ("direct_canvas", "portrait_canvas"),
}
WORKLOAD_LABELS = {
    "full_grid": "Full grid",
    "piece_move": "Piece move",
    "text_redraw": "Text redraw",
}


DEVICE_PROGRAM = r'''
import gc, machine, os, sys, time, ujson
for search_path in reversed(('/device', '/lib', '/', '/files/user')):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)
_MODERN_APP_SOURCE = __MODERN_APP_SOURCE__
if _MODERN_APP_SOURCE is not None:
    import tartlabutils.modern_app as _working_modern_app
    exec(_MODERN_APP_SOURCE, _working_modern_app.__dict__)
from framebuf import FrameBuffer, RGB565
from tartlabutils.platform import get_platform

PROFILE = __PROFILE__
SAMPLES = __SAMPLES__
FULL_GRID_FRAMES = 1
PIECE_MOVE_FRAMES = 30
TEXT_REDRAW_FRAMES = 10
BLOCK_SIZE = 18
BLACK = 0
WHITE = 65535

def ticks():
    return time.ticks_us()

def elapsed(started):
    return time.ticks_diff(ticks(), started)

def class_name(value):
    value_type = type(value)
    return (getattr(value_type, '__module__', '') + '.' +
            getattr(value_type, '__name__', ''))

def measure(draw_frame, frames):
    draw_frame(0)
    values = []
    for sample in range(SAMPLES):
        started = ticks()
        for frame in range(frames):
            draw_frame(sample * frames + frame + 1)
        values.append((elapsed(started) + frames // 2) // frames)
    return values

def make_framebuffer_block(index):
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

platform = get_platform()
capabilities = platform.capabilities
detected_profile = ('modern' if capabilities.get('direct_rgb565', False)
                    else 'legacy')
if detected_profile != PROFILE:
    raise RuntimeError('connected device is %s, expected %s' %
                       (detected_profile, PROFILE))

frame_counts = {
    'full_grid': FULL_GRID_FRAMES,
    'piece_move': PIECE_MOVE_FRAMES,
    'text_redraw': TEXT_REDRAW_FRAMES,
}
results = {}

if PROFILE == 'modern':
    from tartlabutils.modern_app import (
        DirectCanvas, PortraitCanvas, game_surface)

    surface = game_surface()

    def run_modern(key, canvas_type, portrait):
        canvas = canvas_type(surface)
        logical_width = canvas.width if portrait else surface.width
        logical_height = canvas.height if portrait else surface.height
        grid_width = 10 if portrait else 20
        grid_height = 20 if portrait else 10
        field_width = grid_width * BLOCK_SIZE
        field_height = grid_height * BLOCK_SIZE
        field_x = (logical_width - field_width) // 2
        field_y = (logical_height - field_height) // 2
        prepared = []
        for index in range(8):
            data, block = make_framebuffer_block(index)
            prepared.append((data, canvas.prepare_sprite(
                block, BLOCK_SIZE, BLOCK_SIZE)))

        def draw_block(grid_x, grid_y, index):
            canvas.draw_sprite(
                prepared[index][1],
                field_x + grid_x * BLOCK_SIZE,
                field_y + grid_y * BLOCK_SIZE)

        def full_grid(frame):
            for y in range(grid_height):
                for x in range(grid_width):
                    draw_block(x, y, (x + y + frame) % 7 + 1)
            canvas.show((field_x, field_y, field_width, field_height))

        piece_position = [0, (grid_height - 2) // 2]

        def piece_move(frame):
            old_x = piece_position[0]
            max_x = grid_width - 2
            step = frame % (max_x * 2)
            new_x = step if step <= max_x else max_x * 2 - step
            for piece_y in range(2):
                for piece_x in range(2):
                    draw_block(old_x + piece_x,
                               piece_position[1] + piece_y, 0)
                    draw_block(new_x + piece_x,
                               piece_position[1] + piece_y,
                               frame % 7 + 1)
            left = min(old_x, new_x)
            width = abs(new_x - old_x) + 2
            canvas.show((field_x + left * BLOCK_SIZE,
                         field_y + piece_position[1] * BLOCK_SIZE,
                         width * BLOCK_SIZE, 2 * BLOCK_SIZE))
            piece_position[0] = new_x

        text_width = 8 * BLOCK_SIZE
        text_height = 2 * BLOCK_SIZE
        text_x = (logical_width - text_width) // 2
        text_y = (logical_height - text_height) // 2

        def text_redraw(frame):
            canvas.fill_rect(
                text_x, text_y, text_width, text_height, BLACK)
            canvas.text('Frame: %s' % frame, text_x, text_y + 4, WHITE)
            canvas.text('Score: 1,234', text_x, text_y + 12, WHITE)
            canvas.text('Drop: 1000 ms', text_x, text_y + 20, WHITE)
            canvas.show((text_x, text_y, text_width, text_height))

        canvas.fill(BLACK)
        canvas.show()
        results[key] = {
            'api': canvas_type.__name__,
            'orientation': 'portrait' if portrait else 'landscape',
            'logical_width': logical_width,
            'logical_height': logical_height,
            'field_width': field_width,
            'field_height': field_height,
            'full_grid_us': measure(full_grid, FULL_GRID_FRAMES),
            'piece_move_us': measure(piece_move, PIECE_MOVE_FRAMES),
            'text_redraw_us': measure(text_redraw, TEXT_REDRAW_FRAMES),
        }
        canvas.close()
        del canvas
        gc.collect()

    run_modern('direct_canvas', DirectCanvas, False)
    run_modern('portrait_canvas', PortraitCanvas, True)
    platform.enter_ui_mode()
    display_class = class_name(platform.display)
else:
    from hdwconfig import display_drv

    def run_legacy(key, portrait):
        display_drv.rotation = 0
        if portrait and display_drv.width > display_drv.height:
            display_drv.rotation += 90
        elif not portrait and display_drv.width < display_drv.height:
            display_drv.rotation += 90
        grid_width = 10 if portrait else 20
        grid_height = 20 if portrait else 10
        field_width = grid_width * BLOCK_SIZE
        field_height = grid_height * BLOCK_SIZE
        field_x = (display_drv.width - field_width) // 2
        field_y = (display_drv.height - field_height) // 2
        blocks = []
        for index in range(8):
            data, block = make_framebuffer_block(index)
            blocks.append(data)

        def draw_block(grid_x, grid_y, index):
            display_drv.blit_rect(
                blocks[index],
                field_x + grid_x * BLOCK_SIZE,
                field_y + grid_y * BLOCK_SIZE,
                BLOCK_SIZE, BLOCK_SIZE)

        def full_grid(frame):
            for y in range(grid_height):
                for x in range(grid_width):
                    draw_block(x, y, (x + y + frame) % 7 + 1)

        piece_position = [0, (grid_height - 2) // 2]

        def piece_move(frame):
            old_x = piece_position[0]
            max_x = grid_width - 2
            step = frame % (max_x * 2)
            new_x = step if step <= max_x else max_x * 2 - step
            for piece_y in range(2):
                for piece_x in range(2):
                    draw_block(old_x + piece_x,
                               piece_position[1] + piece_y, 0)
                    draw_block(new_x + piece_x,
                               piece_position[1] + piece_y,
                               frame % 7 + 1)
            piece_position[0] = new_x

        text_width = 8 * BLOCK_SIZE
        text_height = 2 * BLOCK_SIZE
        text_x = (display_drv.width - text_width) // 2
        text_y = (display_drv.height - text_height) // 2
        text_data = bytearray(text_width * text_height * 2)
        text_canvas = FrameBuffer(
            text_data, text_width, text_height, RGB565)

        def text_redraw(frame):
            text_canvas.fill(BLACK)
            text_canvas.text('Frame: %s' % frame, 0, 4, WHITE)
            text_canvas.text('Score: 1,234', 0, 12, WHITE)
            text_canvas.text('Drop: 1000 ms', 0, 20, WHITE)
            display_drv.blit_rect(
                text_data, text_x, text_y, text_width, text_height)

        display_drv.disable_auto_byteswap(False)
        display_drv.fill(BLACK)
        results[key] = {
            'api': 'display_drv',
            'orientation': 'portrait' if portrait else 'landscape',
            'logical_width': display_drv.width,
            'logical_height': display_drv.height,
            'field_width': field_width,
            'field_height': field_height,
            'full_grid_us': measure(full_grid, FULL_GRID_FRAMES),
            'piece_move_us': measure(piece_move, PIECE_MOVE_FRAMES),
            'text_redraw_us': measure(text_redraw, TEXT_REDRAW_FRAMES),
        }
        gc.collect()

    run_legacy('display_drv_landscape', False)
    run_legacy('display_drv_portrait', True)
    display_class = class_name(display_drv)

result = {
    'schema': 1,
    'profile': PROFILE,
    'runtime': {
        'sys_version': sys.version,
        'implementation': repr(sys.implementation),
        'uname': repr(os.uname()),
        'machine_frequency_hz': machine.freq(),
        'platform_class': class_name(platform),
        'display_class': display_class,
    },
    'matrix': {
        'samples': SAMPLES,
        'frame_counts': frame_counts,
        'block_size': BLOCK_SIZE,
        'blocks_per_grid': 200,
        'colors': 'black-and-white-rgb565-byte-order-invariant',
    },
    'implementations': results,
}
print('DRAWING_PERFORMANCE=' + ujson.dumps(result))
'''


def device_program(profile: str, samples: int) -> str:
    """Return the temporary MicroPython benchmark program."""
    if profile not in PROFILES:
        raise ValueError("profile must be legacy or modern")
    if samples < 3:
        raise ValueError("samples must be at least 3")
    modern_app_source = None
    if profile == "modern":
        modern_app_source = (ROOT / "src/lib/tartlabutils/modern_app.py").read_text(
            encoding="utf-8")
    return (DEVICE_PROGRAM
            .replace("__PROFILE__", repr(profile))
            .replace("__SAMPLES__", str(samples))
            .replace("__MODERN_APP_SOURCE__", repr(modern_app_source)))


def extract_result(output: bytes) -> dict:
    prefix = MARKER + "="
    decoded = output.decode("utf-8", "replace")
    for line in decoded.splitlines():
        if line.startswith(prefix):
            value = json.loads(line[len(prefix):])
            if not isinstance(value, dict):
                break
            return value
    raise ValueError(f"device output did not contain {MARKER}")


def validate_result(result: dict, expected_profile: str | None = None) -> None:
    """Validate identity and the small locked workload matrix."""
    if result.get("schema") != SCHEMA:
        raise ValueError("unsupported drawing benchmark schema")
    profile = result.get("profile")
    if profile not in PROFILES:
        raise ValueError("benchmark profile must be legacy or modern")
    if expected_profile is not None and profile != expected_profile:
        raise ValueError(
            f"connected device is {profile}, expected {expected_profile}")
    matrix = result.get("matrix", {})
    if not isinstance(matrix.get("samples"), int) or matrix["samples"] < 3:
        raise ValueError("benchmark requires at least three samples")
    if matrix.get("frame_counts") != {
            "full_grid": 1, "piece_move": 30, "text_redraw": 10}:
        raise ValueError("benchmark frame counts differ")
    if (matrix.get("block_size"), matrix.get("blocks_per_grid")) != (18, 200):
        raise ValueError("benchmark geometry differs")

    implementations = result.get("implementations", {})
    if set(implementations) != set(IMPLEMENTATIONS[profile]):
        raise ValueError("benchmark implementations differ")
    expected_apis = (("display_drv", "display_drv") if profile == "legacy"
                     else ("DirectCanvas", "PortraitCanvas"))
    for index, key in enumerate(IMPLEMENTATIONS[profile]):
        item = implementations[key]
        portrait = item.get("orientation") == "portrait"
        expected_size = (222, 480) if portrait else (480, 222)
        expected_field = (180, 360) if portrait else (360, 180)
        if (item.get("logical_width"), item.get("logical_height")) != expected_size:
            raise ValueError(f"wrong logical geometry for {key}")
        if (item.get("field_width"), item.get("field_height")) != expected_field:
            raise ValueError(f"wrong field geometry for {key}")
        if item.get("api") != expected_apis[index]:
            raise ValueError(f"wrong API for {key}")
        for workload in WORKLOADS:
            values = item.get(workload + "_us")
            if (not isinstance(values, list)
                    or len(values) != matrix["samples"]
                    or any(not isinstance(value, (int, float)) or value <= 0
                           for value in values)):
                raise ValueError(f"invalid {workload} samples for {key}")


def _same_matrix(legacy: dict, modern: dict) -> None:
    validate_result(legacy, "legacy")
    validate_result(modern, "modern")
    if legacy["matrix"] != modern["matrix"]:
        raise ValueError("legacy and modern benchmark matrices differ")


def _median_ms(item: dict, workload: str) -> str:
    value = statistics.median(item[workload + "_us"]) / 1000
    return f"{value:.2f}"


def render_report(modern: dict, legacy: dict | None = None,
                  diagnostics: dict | None = None) -> str:
    """Render the intentionally compact results table."""
    validate_result(modern, "modern")
    if legacy is not None:
        _same_matrix(legacy, modern)

    rows = []
    order = (
        (legacy, "display_drv_landscape", "display_drv", "Landscape"),
        (modern, "direct_canvas", "DirectCanvas", "Landscape"),
        (legacy, "display_drv_portrait", "display_drv", "Portrait"),
        (modern, "portrait_canvas", "PortraitCanvas", "Portrait"),
    )
    for source, key, api, orientation in order:
        if source is None:
            cells = ("pending device swap",) * len(WORKLOADS)
        else:
            item = source["implementations"][key]
            cells = tuple(_median_ms(item, workload) for workload in WORKLOADS)
        rows.append(
            f"| {api} | {orientation} | {cells[0]} | {cells[1]} | {cells[2]} |")

    modern_date = modern.get("collection", {}).get("collected_at", "unknown")
    modern_source = modern.get("collection", {}).get(
        "modern_app_source", "device filesystem")
    legacy_date = (legacy.get("collection", {}).get("collected_at", "unknown")
                   if legacy is not None else "pending device swap")
    rendered = "\n".join((
        "# Drawing performance",
        "",
        "The implementation plan is documented in",
        "[`MODERN_DISPLAY_CLASS_PROJECT.md`](../MODERN_DISPLAY_CLASS_PROJECT.md).",
        "",
        "Median end-to-end time per frame on the connected modern and legacy test",
        "devices; lower is faster.",
        "The benchmark uses a 200-block grid, a moving 2 x 2 piece, and a three-line",
        "text region. Black/white RGB565 assets keep byte order from affecting the",
        "comparison.",
        "",
        "| API | Orientation | Full grid (ms) | Piece move (ms) | Text redraw (ms) |",
        "| --- | --- | ---: | ---: | ---: |",
        *rows,
        "",
        f"- Modern collected: `{modern_date}`",
        f"- Legacy collected: `{legacy_date}`",
        f"- Modern app source: `{modern_source}`",
        "",
        "Collection runs temporary code through raw REPL. Modern collection injects",
        "the working-tree module in memory; it does not flash firmware or write to",
        "the device filesystem. Raw result JSON stays in the ignored",
        "`hardware_test_artifacts/drawing-performance` directory.",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe tools/drawing_performance.py collect --port COM3 --profile modern",
        "# Physically swap in a legacy-firmware device; do not flash the fixture.",
        ".\\.venv\\Scripts\\python.exe tools/drawing_performance.py collect --port COM6 --profile legacy",
        ".\\.venv\\Scripts\\python.exe tools/drawing_diagnostics.py --port COM3",
        ".\\.venv\\Scripts\\python.exe tools/drawing_performance.py report",
        "```",
        "",
    ))
    if diagnostics is not None:
        from drawing_diagnostics import render_section
        rendered += "\n" + render_section(diagnostics)
    return rendered


def collect(args: argparse.Namespace) -> None:
    program = device_program(args.profile, args.samples)
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
        "tool": "tools/drawing_performance.py",
        "device_writes": False,
        "firmware_flash": False,
    }
    if args.profile == "modern":
        result["collection"]["modern_app_source"] = "working_tree_in_memory"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Raw {args.profile} result written to {args.output}", file=sys.stderr)


def report(args: argparse.Namespace) -> None:
    modern = json.loads(args.modern.read_text(encoding="utf-8"))
    legacy = (json.loads(args.legacy.read_text(encoding="utf-8"))
              if args.legacy.exists() else None)
    diagnostics = (json.loads(args.diagnostics.read_text(encoding="utf-8"))
                   if args.diagnostics.exists() else None)
    rendered = render_report(modern, legacy, diagnostics)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    artifact_dir = Path("hardware_test_artifacts/drawing-performance")

    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--port", default="COM3")
    collect_parser.add_argument("--baudrate", type=int, default=115200)
    collect_parser.add_argument("--timeout", type=int, default=30)
    collect_parser.add_argument("--profile", choices=PROFILES, required=True)
    collect_parser.add_argument("--samples", type=int, default=7)
    collect_parser.add_argument("--output", type=Path)
    collect_parser.set_defaults(func=collect)

    report_parser = commands.add_parser("report")
    report_parser.add_argument("--modern", type=Path,
                               default=artifact_dir / "modern.json")
    report_parser.add_argument("--legacy", type=Path,
                               default=artifact_dir / "legacy.json")
    report_parser.add_argument(
        "--diagnostics", type=Path,
        default=artifact_dir / "modern-diagnostics.json")
    report_parser.add_argument("--output", type=Path,
                               default=Path("tests/DRAWING_PERFORMANCE.md"))
    report_parser.set_defaults(func=report)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "collect" and args.output is None:
        args.output = Path("hardware_test_artifacts/drawing-performance") / (
            args.profile + ".json")
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, TimeoutError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
