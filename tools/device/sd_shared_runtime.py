"""Unattended shared-platform SD fixture; physical observations stay separate."""

import gc
import json
import network
import sys
import time

from hdwconfig import BOARD_CONFIG
from external_root import open_sd, activate

_runtime_card = open_sd(BOARD_CONFIG)
activate(_runtime_card, required=('boot.py', 'main.py', 'device/board.json', 'device/hdwconfig.py'))
del sys.modules['hdwconfig']
for _path in ('/lib', '/device'):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from tartlabutils.platform import get_platform

# A raw soft reset can retain the normal IDE's native network interfaces.
# This isolated fixture stops them; the host restores normal startup afterward.
_load_network_before = {
    'ap': network.WLAN(network.AP_IF).active(),
    'station': network.WLAN(network.STA_IF).active()}
network.WLAN(network.STA_IF).active(False)
network.WLAN(network.AP_IF).active(False)
_load_platform = get_platform()
_load_lv = _load_platform.lvgl
if _load_lv._nesting.value != 0:
    raise RuntimeError('LVGL callback nesting retained; hard restart required')
_load_screen = _load_lv.obj()
_load_screen.set_style_bg_color(_load_lv.color_hex(0), 0)
_load_screen.set_style_border_width(3, 0)
_load_screen.set_style_border_color(_load_lv.color_hex(0x00ffff), 0)
_load_title = _load_lv.label(_load_screen)
_load_title.set_text('SD + RGB + Wi-Fi endurance')
_load_title.align(_load_lv.ALIGN.TOP_MID, 0, 25)
_load_status = _load_lv.label(_load_screen)
_load_status.align(_load_lv.ALIGN.CENTER, 0, 0)
_load_touch = _load_lv.label(_load_screen)
_load_touch.set_text('Automated checks running')
_load_touch.align(_load_lv.ALIGN.BOTTOM_MID, 0, -25)
_load_points = []
_load_beats = 0


def _load_pressed(event):
    point = _load_lv.point_t()
    _load_lv.indev_active().get_point(point)
    if len(_load_points) < 200:
        _load_points.append((point.x, point.y))
    _load_touch.set_text('TOUCH %d, %d' % (point.x, point.y))


def _load_heartbeat(timer):
    global _load_beats
    _load_beats += 1


_load_screen.add_event_cb(_load_pressed, _load_lv.EVENT.PRESSED, None)
for _label in (_load_title, _load_status, _load_touch):
    _label.set_style_text_color(_load_lv.color_hex(0xffffff), 0)
    _label.remove_flag(_load_lv.obj.FLAG.CLICKABLE)
_load_lv.screen_load(_load_screen)
_load_timer = _load_lv.timer_create(_load_heartbeat, 100, None)
_load_lv.refr_now(_load_platform.controller._lv_display)
_load_platform.controller.wait_for_transfer()


def _load_refresh(message):
    _load_status.set_text(message)
    time.sleep_ms(2)


def _load_sample():
    gc.collect()
    controller = _load_platform.controller
    # An active UI can legitimately have a flush in flight at any instant.
    # Stop new submissions and require the existing transfer to complete.
    controller._task_handler.disable()
    try:
        controller.wait_for_transfer()
        return {'nesting': _load_lv._nesting.value, 'heartbeats': _load_beats,
                'presses': len(_load_points), 'heap_free': gc.mem_free(),
                'owner': controller.owner, 'pending': controller.transfer_pending}
    finally:
        controller._task_handler.enable()


def _load_handover():
    surface = _load_platform.enter_game_mode()
    buffer = surface.allocate_buffer(1, 1)
    try:
        buffer[0], buffer[1] = 0xf8, 0
        surface.write(buffer, surface.width - 1, surface.height - 1, 1, 1)
        if bytes(buffer) != b'\xf8\x00':
            raise ValueError('Direct source buffer modified')
    finally:
        surface.free_buffer(buffer)
        _load_platform.enter_ui_mode()
    time.sleep_ms(250)
    return _load_sample()


time.sleep_ms(500)
_load_ready = {
    'board': _load_platform.board['id'],
    'pixel_clock_hz': _load_platform.board['display']['rgb']['freq'],
    'sd_frequency_hz': _load_platform.board['storage']['frequency'],
    'network_before_isolation': _load_network_before}
_load_ready.update(_load_sample())
print('SD_SHARED_READY=' + json.dumps(_load_ready))
