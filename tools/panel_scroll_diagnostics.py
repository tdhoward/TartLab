"""Run the temporary ST7796 panel-scroll experiment through raw REPL.

The probe injects working-tree sources in memory. It does not flash firmware or
write the device filesystem, and it restores neutral scanout before returning.
Visual correctness still requires observing the connected display.
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
MARKER = "PANEL_SCROLL_DIAGNOSTICS="


DEVICE_PROGRAM = r'''
import gc, sys, time, uhashlib, ujson
for search_path in reversed(('/device', '/lib', '/', '/files/user')):
    if search_path not in sys.path:
        sys.path.insert(0, search_path)

adapter_scope = {'__name__': 'tartlabutils.modern_st7796_probe'}
exec(__ADAPTER_SOURCE__, adapter_scope)
import tartlabutils._modern_emitters as modern_emitters
exec(__EMITTER_SOURCE__, modern_emitters.__dict__)
modern_app = sys.modules.get('tartlabutils.modern_app')
if modern_app is None:
    import tartlabutils.modern_app as modern_app
exec(__MODERN_APP_SOURCE__, modern_app.__dict__)
board_scope = {'__name__': 't_display_s3_pro_modern_probe'}
exec(__BOARD_SOURCE__, board_scope)

from tartlabutils.platform import get_platform
DirectCanvas = modern_app.DirectCanvas
FrameBuffer = modern_app.FrameBuffer
RGB565 = modern_app.RGB565
BaseSurface = adapter_scope['ST7796DirectRGB565Surface']

def ticks():
    return time.ticks_us()

def elapsed(started):
    return time.ticks_diff(ticks(), started)

def digest(buffer):
    algorithm = uhashlib.sha256()
    algorithm.update(buffer)
    value = algorithm.digest()
    return ''.join('{:02x}'.format(byte) for byte in value)

class CountingSurface(BaseSurface):
    def __init__(self, *args, **kwargs):
        self.sent_bytes = 0
        self.sent_regions = []
        BaseSurface.__init__(self, *args, **kwargs)

    def _send(self, buffer, x, y, width, height, wait):
        self.sent_bytes += len(buffer)
        self.sent_regions.append((x, y, width, height))
        return BaseSurface._send(self, buffer, x, y, width, height, wait)

    def reset_counts(self):
        self.sent_bytes = 0
        self.sent_regions = []

platform = get_platform()
board = board_scope['BOARD_CONFIG']
display = board['display']
visual_hold_ms = __VISUAL_HOLD_MS__
if display['driver'] != 'st7796.ST7796':
    raise RuntimeError('panel-scroll diagnostics require the ST7796 board')
original = platform.enter_game_mode()
controller = platform.controller
width, height = display['logical_size']
offset_x, offset_y = display.get('offset', (0, 0))

def make_surface(qualified):
    return CountingSurface(
        controller, controller._bus, platform.display,
        width, height, offset_x, offset_y, display['transfer_rows'],
        original._allocation_flags, original._buffer_allocator,
        original._buffer_free,
        {'qualified_rotations': (display['rotation'],) if qualified else ()},
        display['native_size'][1], display['rotation'])

def seed(canvas):
    colors = (0x00F8, 0xE007, 0x1F00, 0xFFFF, 0x0000, 0xE0FF)
    stripe = 40
    canvas.fill(0)
    x = 0
    index = 0
    while x < canvas.width:
        canvas.fill_rect(
            x, 0, min(stripe, canvas.width - x), canvas.height,
            colors[index % len(colors)])
        x += stripe
        index += 1
    canvas.text('ST7796 SCROLL', 8, 8, 0xFFFF)

def make_replacement(canvas, area, dx, dy):
    exposed = DirectCanvas._exposed_regions(*area, dx, dy)
    if len(exposed) != 1:
        raise ValueError('replacement diagnostic requires one exposed band')
    unused_x, unused_y, width, height = exposed[0]
    data = bytearray(width * height * 2)
    band = FrameBuffer(data, width, height, RGB565)
    band.fill(0xE007)
    road_left = width // 6
    band.fill_rect(road_left, 0, width - road_left * 2, height, 0x0000)
    band.vline(width // 2, 0, height, 0xFFFF)
    return canvas.prepare_sprite(band, width, height)

def run_case(name, area, dx=0, dy=0, rotation=0,
             replacement=False, seam=False):
    accelerated_surface = None
    accelerated_canvas = None
    software_surface = None
    software_canvas = None
    try:
        accelerated_surface = make_surface(True)
        accelerated_canvas = DirectCanvas(
            accelerated_surface, rotation=rotation)
        if visual_hold_ms and name == 'visual_confirmation':
            accelerated_canvas.fill(0xE0FF)
            accelerated_canvas.show()
            time.sleep_ms(2000)
        seed(accelerated_canvas)
        accelerated_canvas.show()
        accelerated_surface.reset_counts()
        accelerated_band = make_replacement(
            accelerated_canvas, area, dx, dy) if replacement else None
        started = ticks()
        accelerated_canvas.scroll_region(
            area, dx=dx, dy=dy, fill=0x0000,
            exposed=accelerated_band)
        accelerated_us = elapsed(started)
        accelerated_bytes = accelerated_surface.sent_bytes
        accelerated_regions = tuple(accelerated_surface.sent_regions)
        accelerated_digest = digest(accelerated_canvas.buffer)
        if visual_hold_ms and name == 'visual_confirmation':
            time.sleep_ms(visual_hold_ms)
            accelerated_surface.reset_scroll()
            accelerated_canvas.fill(0x1F00)
            accelerated_canvas.show()
            time.sleep_ms(2000)
        seam_regions = ()
        if seam:
            # With dx=-32 the active seam appears at visible x=448.
            accelerated_surface.reset_counts()
            accelerated_canvas.fill_rect(440, 40, 24, 24, 0xFFFF)
            accelerated_canvas.show((440, 40, 24, 24))
            seam_regions = tuple(accelerated_surface.sent_regions)
        accelerated_canvas.close()
        accelerated_canvas = None
        accelerated_surface.free_resources()
        accelerated_surface = None

        software_surface = make_surface(False)
        software_canvas = DirectCanvas(software_surface, rotation=rotation)
        seed(software_canvas)
        software_surface.reset_counts()
        software_band = make_replacement(
            software_canvas, area, dx, dy) if replacement else None
        started = ticks()
        software_canvas.scroll_region(
            area, dx=dx, dy=dy, fill=0x0000,
            exposed=software_band)
        software_us = elapsed(started)
        software_bytes = software_surface.sent_bytes
        software_digest = digest(software_canvas.buffer)
        if visual_hold_ms and name == 'visual_confirmation':
            time.sleep_ms(visual_hold_ms)
            software_canvas.fill(0)
            software_canvas.text('VISUAL TEST COMPLETE', 160, 107, 0xFFFF)
            software_canvas.show()
            time.sleep_ms(3000)
        return {
            'name': name,
            'area': area,
            'dx': dx,
            'dy': dy,
            'rotation': rotation,
            'replacement': replacement,
            'accelerated_us': accelerated_us,
            'software_us': software_us,
            'accelerated_bytes': accelerated_bytes,
            'software_bytes': software_bytes,
            'accelerated_regions': accelerated_regions,
            'seam_regions': seam_regions,
            'buffer_checksums_match': accelerated_digest == software_digest,
        }
    finally:
        if accelerated_canvas is not None:
            try:
                accelerated_canvas.close()
            except Exception:
                pass
        if accelerated_surface is not None:
            try:
                accelerated_surface.free_resources()
            except Exception:
                pass
        if software_canvas is not None:
            try:
                software_canvas.close()
            except Exception:
                pass
        if software_surface is not None:
            try:
                software_surface.free_resources()
            except Exception:
                pass

try:
    full_area = (0, 0, width, height)
    cases = (
        run_case('negative_full', full_area, dx=-32, seam=True),
        run_case('positive_full', full_area, dx=32),
        run_case('fixed_sides', (40, 0, width - 80, height), dx=16),
        run_case(
            'fixed_sides_negative', (40, 0, width - 80, height), dx=-16),
        run_case(
            'portrait_fixed_header', (0, 24, height, width - 24),
            dy=4, rotation=90, replacement=True),
        run_case('negative_full_repeat', full_area, dx=-32),
    )
    visual_case = None
    if visual_hold_ms:
        visual_case = run_case(
            'visual_confirmation', full_area, dx=-32)
    result = {
        'board': board['id'],
        'panel_rotation': display['rotation'],
        'axis': 'x',
        'cases': cases,
        'all_buffer_checksums_match': all(
            item['buffer_checksums_match'] for item in cases),
        'repeat_regions_match': (
            cases[0]['accelerated_regions'] ==
            cases[5]['accelerated_regions']),
        'visual_case': visual_case,
        'scanout_restored': True,
        'visual_confirmation_required': True,
        'heap_free': gc.mem_free(),
    }
    print('PANEL_SCROLL_DIAGNOSTICS=' + ujson.dumps(result))
finally:
    platform.enter_ui_mode()
'''


def device_program(visual_hold_seconds: int = 0) -> str:
    adapter = (ROOT / "src/lib/tartlabutils/modern_st7796.py").read_text(
        encoding="utf-8")
    emitters = (ROOT / "src/lib/tartlabutils/_modern_emitters.py").read_text(
        encoding="utf-8")
    modern_app = (ROOT / "src/lib/tartlabutils/modern_app.py").read_text(
        encoding="utf-8")
    return DEVICE_PROGRAM.replace(
        "__VISUAL_HOLD_MS__", str(max(0, visual_hold_seconds) * 1000)).replace(
        "__ADAPTER_SOURCE__", repr(adapter)).replace(
        "__EMITTER_SOURCE__", repr(emitters)).replace(
        "__MODERN_APP_SOURCE__", repr(modern_app)).replace(
        "__BOARD_SOURCE__", repr((
            ROOT / "boards/lilygo_t_display_s3_pro/runtime/"
            "t_display_s3_pro_modern.py").read_text(encoding="utf-8")))


def extract_result(output: bytes) -> dict:
    text = output.decode("utf-8", "replace")
    for line in text.splitlines():
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    raise ValueError("panel-scroll diagnostics marker was not returned")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--visual-hold", type=int, default=0, metavar="SECONDS",
        help="hold accelerated and software reference frames for observation")
    args = parser.parse_args()
    if args.visual_hold:
        print(
            "Watch COM3: yellow cue, hardware stripes, blue separator, "
            "software stripes, then TEST COMPLETE. The striped holds "
            "should be pixel-identical.", file=sys.stderr)
    repl = RawRepl(args.port, args.baudrate, args.timeout)
    try:
        repl.enter()
        output = repl.exec(
            device_program(args.visual_hold),
            max(args.timeout, 180 + args.visual_hold * 2))
    finally:
        repl.close()
    print(json.dumps(extract_result(output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
