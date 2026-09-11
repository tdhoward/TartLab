"""Native LVGL calculator. Reset returns to the launcher."""


LABELS = (
    "Sqrt", "%", "+/-", "C",
    "7", "8", "9", "/",
    "4", "5", "6", "*",
    "1", "2", "3", "-",
    "0", ".", "=", "+",
)

state = {
    "text": "0",
    "value": None,
    "operation": None,
    "fresh": True,
}


def number(value):
    return int(value) if int(value) == value else value


def calculate(left, operation, right):
    if operation == "+":
        return left + right
    if operation == "-":
        return left - right
    if operation == "*":
        return left * right
    if operation == "/":
        return left / right
    return right


def press(label):
    try:
        if label in "0123456789":
            if not state["fresh"] and len(state["text"]) >= 16:
                return
            state["text"] = label if state["fresh"] or state["text"] == "0" else state["text"] + label
            state["fresh"] = False
        elif label == ".":
            if state["fresh"]:
                state["text"] = "0."
                state["fresh"] = False
            elif "." not in state["text"]:
                state["text"] += "."
        elif label == "C":
            state.update({
                "text": "0", "value": None,
                "operation": None, "fresh": True})
        elif label == "+/-":
            state["text"] = str(number(-float(state["text"])))
        elif label == "%":
            state["text"] = str(number(float(state["text"]) / 100))
            state["fresh"] = True
        elif label == "Sqrt":
            value = float(state["text"])
            if value < 0:
                raise ValueError("negative square root")
            state["text"] = str(number(value ** 0.5))
            state["fresh"] = True
        else:
            right = float(state["text"])
            if state["value"] is not None and state["operation"]:
                right = calculate(state["value"], state["operation"], right)
                state["text"] = str(number(right))
            state["value"] = right
            state["operation"] = None if label == "=" else label
            state["fresh"] = True
    except (ValueError, ZeroDivisionError, OverflowError):
        state.update({
            "text": "Error", "value": None,
            "operation": None, "fresh": True})



def keypad_layout(width, height):
    """Fit the readout and keypad to the current LVGL display orientation."""
    margin = max(4, min(width, height) // 40)
    gap = margin
    if width > height:
        # Five columns leave room for legible keys on short landscape displays.
        keys = ("7", "8", "9", "/", "C",
                "4", "5", "6", "*", "Sqrt",
                "1", "2", "3", "-", "%",
                "0", ".", "=", "+", "+/-")
        columns, rows = 5, 4
    else:
        keys, columns, rows = LABELS, 4, 5
    readout = max(40, height // 5)
    top = margin + readout + gap
    available_width = width - 2 * margin + gap
    available_height = height - top - margin + gap
    boxes = []
    for index, key in enumerate(keys):
        col, row = index % columns, index // columns
        left = margin + col * available_width // columns
        right = margin + (col + 1) * available_width // columns - gap
        y = top + row * available_height // rows
        bottom = top + (row + 1) * available_height // rows - gap
        boxes.append((key, left, y, right - left, bottom - y))
    return margin, readout, boxes


class CalculatorUI:
    def __init__(self, lv, platform):
        self.lv = lv
        self.previous = lv.screen_active()
        self.screen = lv.obj()
        self.focus = None
        self.callbacks = []
        self.platform = platform

    def text(self, parent, value, size, width, height):
        lv = self.lv
        label = lv.label(parent)
        label.set_text(value)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        # Stock modern firmware includes Montserrat 16. Scale that native
        # LVGL font when larger compiled fonts are unavailable.
        font_size = 16
        for candidate in (48, 40, 32, 28, 24, 20, 16):
            font = getattr(lv, "font_montserrat_%d" % candidate, None)
            if candidate <= size and font is not None:
                font_size = candidate
                label.set_style_text_font(font, 0)
                break
        label.update_layout()
        scale = min(size * 256 // font_size,
                    width * 256 // max(1, label.get_width()),
                    height * 256 // max(1, label.get_height()))
        label.set_style_transform_pivot_x(label.get_width() // 2, 0)
        label.set_style_transform_pivot_y(label.get_height() // 2, 0)
        label.set_style_transform_scale_x(scale, 0)
        label.set_style_transform_scale_y(scale, 0)
        label.center()
        return label

    def show(self):
        lv = self.lv
        screen = self.screen
        width, height = self.platform.width, self.platform.height
        screen.set_style_bg_color(lv.color_hex(0x101820), 0)
        screen.set_style_pad_all(0, 0)
        screen.set_style_border_width(0, 0)
        screen.set_scroll_dir(lv.DIR.NONE)
        margin, readout, boxes = keypad_layout(width, height)
        navigation = getattr(self.platform, "navigation", None)
        if navigation is not None:
            self.focus = navigation.page()
        self.readout = lv.obj(screen)
        self.readout.set_pos(margin, margin)
        self.readout.set_size(width - 2 * margin, readout)
        self.readout.set_style_bg_color(lv.color_hex(0x1C2C38), 0)
        self.readout.set_style_border_width(0, 0)
        self.readout.set_style_pad_all(0, 0)
        self.readout.set_style_radius(10, 0)
        self.readout.set_scroll_dir(lv.DIR.NONE)
        self.result = None
        self.result_size = min(40, max(24, readout // 2))
        self.result_width = width - 4 * margin
        self.result_height = readout - 18
        self.status = lv.label(self.readout)
        self.status.set_style_text_color(lv.color_hex(0x90CAF9), 0)
        self.status.align(lv.ALIGN.BOTTOM_RIGHT, -6, -2)
        for key, x, y, w, h in boxes:
            button = lv.button(screen)
            button.set_pos(x, y)
            button.set_size(w, h)
            button.set_style_pad_all(0, 0)
            button.set_style_border_width(0, 0)
            button.set_style_shadow_width(0, 0)
            button.set_style_radius(min(12, h // 3), 0)
            color = 0x37474F
            if key in ("+", "-", "*", "/", "="):
                color = 0x1976D2
            elif key in ("Sqrt", "%", "+/-", "C"):
                color = 0x546E7A
            button.set_style_bg_color(lv.color_hex(color), 0)
            button.set_style_bg_color(lv.color_hex(0x5398C2), lv.STATE.PRESSED)
            self.text(button, key, min(28, max(20, h - 8)), w - 8, h - 6)
            callback = self.on_click(key)
            self.callbacks.append(callback)
            button.add_event_cb(callback, lv.EVENT.CLICKED, None)
            if self.focus is not None:
                self.focus.add(button)
        self.refresh()
        lv.screen_load(screen)

    def on_click(self, key):
        def clicked(event):
            press(key)
            self.refresh()
        return clicked

    def refresh(self):
        if self.result is not None:
            self.result.delete()
        self.result = self.text(self.readout, state["text"], self.result_size,
                                self.result_width, self.result_height)
        self.result.set_y(self.result.get_y() - 7)
        self.status.set_text(state["operation"] or "")

    def close(self):
        if self.focus is not None:
            self.focus.close()
        self.lv.screen_load(self.previous)
        self.screen.delete()
        self.callbacks = []


def run():
    import lvgl as lv
    from time import sleep_ms
    from tartlabutils.platform import get_platform

    platform = get_platform()
    platform.enter_ui_mode()
    ui = CalculatorUI(lv, platform)
    try:
        ui.show()
        # The platform owns LVGL's event loop and pointer input.
        while True:
            sleep_ms(50)
    finally:
        ui.close()


if globals().get("_CALCULATOR_AUTOSTART", True):
    run()
