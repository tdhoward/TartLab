"""A touch calculator drawn and refreshed as an RGB565 framebuffer."""

from time import sleep_ms

from tartlabutils.modern_app import (
    PortraitCanvas, PortraitTouchGrid, game_surface, rgb565)


surface = game_surface()
canvas = PortraitCanvas(surface)

BACKGROUND = rgb565(16, 24, 32)
BUTTON = rgb565(55, 71, 79)
FUNCTION = rgb565(84, 110, 122)
OPERATOR = rgb565(25, 118, 210)
WHITE = rgb565(255, 255, 255)
STATUS = rgb565(144, 202, 249)

labels = (
    "Sqrt", "%", "+/-", "C",
    "7", "8", "9", "/",
    "4", "5", "6", "*",
    "1", "2", "3", "-",
    "0", ".", "=", "+",
)

columns = 4
rows = 5
keypad_x = 4
keypad_y = 52
keypad_width = canvas.width - keypad_x * 2
keypad_height = canvas.height - keypad_y - 4
cell_width = keypad_width // columns
cell_height = keypad_height // rows
touch = PortraitTouchGrid(
    labels, columns, rows,
    x=keypad_x, y=keypad_y,
    width=keypad_width, height=keypad_height)

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


def draw():
    canvas.fill(BACKGROUND)
    text = state["text"][-24:]
    canvas.text(text, canvas.width - len(text) * 8 - 8, 10, WHITE)
    operation = state["operation"] or ""
    canvas.text(operation, canvas.width - len(operation) * 8 - 8, 30, STATUS)

    for index, label in enumerate(labels):
        column = index % columns
        row = index // columns
        x = keypad_x + column * cell_width + 2
        y = keypad_y + row * cell_height + 2
        width = cell_width - 4
        height = cell_height - 4
        color = BUTTON
        if label in "+-*/=":
            color = OPERATOR
        elif label in ("Sqrt", "%", "+/-", "C"):
            color = FUNCTION
        canvas.fill_rect(x, y, width, height, color)
        canvas.text(
            label,
            x + (width - len(label) * 8) // 2,
            y + (height - 8) // 2,
            WHITE)
    canvas.show()


def press(label):
    try:
        if label in "0123456789":
            state["text"] = label if state["fresh"] else state["text"] + label
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
    except (ValueError, ZeroDivisionError):
        state.update({
            "text": "Error", "value": None,
            "operation": None, "fresh": True})


draw()
while True:
    key = touch.read()
    if key is not None:
        press(key)
        draw()
    sleep_ms(20)
