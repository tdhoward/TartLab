"""Release-triggered LVGL keypad input and page-owned focus groups."""


class ButtonNavigation:
    def __init__(self, lvgl, buttons, mapping):
        self._lv = lvgl
        self._buttons = buttons
        self._mapping = {mapping["next"]: lvgl.KEY.NEXT,
                         mapping["activate"]: lvgl.KEY.ENTER}
        self._listeners = []
        self._armed = set()
        self._pending = []
        self._release = False
        self._key = lvgl.KEY.ENTER
        self._enabled = True
        self._group = None
        self._indev = lvgl.indev_create()
        self._indev.set_type(lvgl.INDEV_TYPE.KEYPAD)
        self._indev.set_read_cb(self._read)

    def add_activity_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_activity_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def discard(self):
        self._buttons.reset()
        self._armed.clear()
        self._pending = []
        self._release = False
        self._indev.reset(None)

    def enable(self, enabled):
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self.discard()
        self._indev.enable(enabled)

    def _read(self, unused_indev, data):
        data.state = self._lv.INDEV_STATE.RELEASED
        data.key = self._key
        data.continue_reading = False
        if not self._enabled:
            return
        for name, pressed in self._buttons.poll():
            if name not in self._mapping:
                continue
            if pressed:
                consumed = False
                for callback in tuple(self._listeners):
                    consumed = bool(callback()) or consumed
                if not consumed:
                    self._armed.add(name)
            elif name in self._armed:
                self._armed.remove(name)
                # Bound the queue to the number of physical keys.
                if len(self._pending) < len(self._mapping):
                    self._pending.append(self._mapping[name])
        if self._release:
            self._release = False
            return
        if self._pending and self._group is not None:
            self._key = self._pending.pop(0)
            data.key = self._key
            data.state = self._lv.INDEV_STATE.PRESSED
            self._release = True

    def page(self):
        if self._group is not None:
            raise RuntimeError("close the previous focus page first")
        self.discard()
        self._group = self._lv.group_create()
        self._group.set_wrap(True)
        self._indev.set_group(self._group)
        return FocusPage(self, self._group)

    def close(self):
        self.enable(False)
        self._indev.set_group(None)
        if self._group is not None:
            self._group.delete()
            self._group = None
        self._indev.delete()
        self._listeners = []


class FocusPage:
    """A focus group whose widgets and callbacks belong to one UI page."""

    def __init__(self, navigation, group):
        self._navigation = navigation
        self._group = group

    def add(self, widget):
        lv = self._navigation._lv
        widget.add_flag(lv.obj.FLAG.SCROLL_ON_FOCUS)
        widget.set_style_outline_width(3, lv.STATE.FOCUSED)
        widget.set_style_outline_color(lv.color_hex(0xFFD54F), lv.STATE.FOCUSED)
        widget.set_style_outline_pad(0, lv.STATE.FOCUSED)
        self._group.add_obj(widget)

    def focus(self, widget):
        self._navigation._lv.group_focus_obj(widget)

    def close(self):
        if self._group is None:
            return
        navigation = self._navigation
        navigation.discard()
        navigation._indev.set_group(None)
        self._group.remove_all_objs()
        self._group.delete()
        if navigation._group is self._group:
            navigation._group = None
        self._group = None
