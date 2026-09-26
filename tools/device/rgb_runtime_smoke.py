"""Bounded shared-platform RGB visual/ownership fixture; no SD file writes.

Run after creating the normal platform on a clean interpreter. Machine results
do not imply a visual pass; record the operator's observation separately.
"""


def rgb_runtime_smoke(platform, direct_ms=40000, touch_ms=80000):
    import gc
    import time

    width, height = platform.width, platform.height
    rows = platform.board['display']['transfer_rows']
    surface = platform.enter_game_mode()
    buffer = surface.allocate_buffer(width, rows)
    view = memoryview(buffer)
    writes = 0

    def rectangle(x, y, w, h, color):
        nonlocal writes
        for offset in range(0, h, rows):
            count = min(rows, h - offset)
            size = w * count * 2
            for index in range(0, size, 2):
                buffer[index], buffer[index + 1] = color >> 8, color & 255
            surface.write(view[:size], x, y + offset, w, count)
            assert buffer[0] == color >> 8 and buffer[1] == color & 255
            writes += 1

    colors = (0xF800, 0x07E0, 0x001F, 0xFFFF, 0x8410, 0)
    try:
        rectangle(0, 0, width, height, 0)
        for index, color in enumerate(colors):
            start, end = index * width // len(colors), (index + 1) * width // len(colors)
            rectangle(start, 0, end - start, height, color)
        corner = max(8, min(width, height) // 20)
        for x, y, color in ((0, 0, 0xFFE0), (width-corner, 0, 0x07FF),
                            (0, height-corner, 0xF81F), (width-corner, height-corner, 0xFFE0)):
            rectangle(x, y, corner, corner, color)
        started = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), started) < direct_ms:
            time.sleep_ms(20)
    finally:
        surface.free_buffer(buffer)
        platform.enter_ui_mode()

    lv = platform.lvgl
    screen = lv.obj()
    screen.set_style_bg_color(lv.color_hex(0), 0)
    screen.set_style_border_width(2, 0)
    screen.set_style_border_color(lv.color_hex(0x00FFFF), 0)
    title = lv.label(screen)
    title.set_text('TartLab RGB runtime - tap with one finger')
    title.align(lv.ALIGN.TOP_MID, 0, 30)
    counter = lv.label(screen)
    counter.align(lv.ALIGN.CENTER, 0, 0)
    remaining = lv.label(screen)
    remaining.align(lv.ALIGN.BOTTOM_MID, 0, -30)
    points = []

    def pressed(unused_event):
        point = lv.point_t()
        lv.indev_active().get_point(point)
        points.append((point.x, point.y))
        counter.set_text('TOUCH %d, %d | %d presses' % (point.x, point.y, len(points)))

    for label in (title, counter, remaining):
        label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        label.remove_flag(lv.obj.FLAG.CLICKABLE)
    screen.add_event_cb(pressed, lv.EVENT.PRESSED, None)
    lv.screen_load(screen)
    started = time.ticks_ms()
    second = -1
    while time.ticks_diff(time.ticks_ms(), started) < touch_ms:
        left = (touch_ms - time.ticks_diff(time.ticks_ms(), started) + 999) // 1000
        if left != second:
            remaining.set_text('%ds remaining' % left)
            second = left
        time.sleep_ms(20)
    # Exercise ownership repeatedly after the physical observation window.
    for unused in range(5):
        platform.enter_game_mode()
        platform.enter_ui_mode()
    remaining.set_text('Runtime checks complete')
    gc.collect()
    return {'width': width, 'height': height, 'direct_writes': writes,
            'source_preserved': True, 'ownership_cycles': 6,
            'touch_points': points, 'heap_free': gc.mem_free(),
            'owner': platform.controller.owner,
            'pending': platform.controller.transfer_pending,
            'visual_pass': None}
