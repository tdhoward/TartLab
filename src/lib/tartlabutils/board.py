"""Helpers for consuming declarative TartLab board payloads."""


def validate_board_config(board):
    """Validate the common shape shared by modern board payloads."""
    if not isinstance(board, dict):
        raise ValueError("BOARD_CONFIG must be a dictionary")
    required = {"id", "pins", "display", "touch"}
    allowed = required | {"reset", "navigation", "outputs"}
    if not required.issubset(board) or not set(board).issubset(allowed):
        raise ValueError("BOARD_CONFIG has unexpected top-level fields")
    board_id = board["id"]
    if not isinstance(board_id, str) or not board_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in board_id):
        raise ValueError("BOARD_CONFIG id is invalid")

    pin_types = set()
    button_names = set()
    for pin in board["pins"]:
        if not isinstance(pin, dict):
            raise ValueError("board pin entries must be dictionaries")
        pin_type = pin.get("type")
        number = pin.get("number")
        if not isinstance(pin_type, str) or not pin_type:
            raise ValueError("board pin type is invalid")
        name = pin.get("name")
        if pin_type == "BUTTON" and name is not None:
            if not isinstance(name, str) or not name or name in button_names:
                raise ValueError("button names must be unique non-empty strings")
            button_names.add(name)
        if pin_type in pin_types and (pin_type != "BUTTON" or name is None):
            raise ValueError("board defines %s more than once" % pin_type)
        if not isinstance(number, int):
            raise ValueError("board pin %s has an invalid number" % pin_type)
        if "active_high" in pin and not isinstance(pin["active_high"], bool):
            raise ValueError("board pin %s has invalid polarity" % pin_type)
        pin_types.add(pin_type)

    buttons = pin_definitions(board, "BUTTON")
    if len(buttons) > 1 and any(not pin.get("name") for pin in buttons):
        raise ValueError("multiple buttons require unique names")
    navigation = board.get("navigation")
    if navigation is not None:
        if not isinstance(navigation, dict) or set(navigation) != {"next", "activate"}:
            raise ValueError("navigation requires next and activate button names")
        if any(name not in button_names for name in navigation.values()) or \
                navigation["next"] == navigation["activate"]:
            raise ValueError("navigation requires two distinct named buttons")
    for output in board.get("outputs", ()):
        if not isinstance(output, dict) or set(output) != {"pin", "value", "delay_ms"}:
            raise ValueError("invalid board output sequence")
        pin_definition(board, output["pin"], True)
        if output["value"] not in (0, 1) or not isinstance(output["delay_ms"], int) or output["delay_ms"] < 0:
            raise ValueError("invalid board output level or delay")

    for component in ("display", "touch"):
        definition = board[component]
        if component == "touch" and definition is None:
            continue
        if not isinstance(definition, dict):
            raise ValueError("board %s definition must be a dictionary" % component)
        driver = definition.get("driver")
        if not isinstance(driver, str) or "." not in driver:
            raise ValueError("board %s driver reference is invalid" % component)

    reset = board.get("reset", {})
    if not isinstance(reset, dict) or \
            not set(reset).issubset({"soft_reset"}):
        raise ValueError("board reset policy is invalid")
    if reset.get("soft_reset", "native") not in ("native", "hard_reset"):
        raise ValueError("board soft-reset policy is invalid")
    return board


def pin_definitions(board, pin_type):
    """Return all entries of a purpose, in declarative order."""
    return tuple(item for item in board.get("pins", ()) if item.get("type") == pin_type)


def pin_definition(board, pin_type, required=False, name=None):
    """Return the unique typed pin entry from a ``BOARD_CONFIG`` object."""
    matches = [
        item for item in board.get("pins", ())
        if item.get("type") == pin_type and (name is None or item.get("name") == name)
    ]
    if len(matches) > 1:
        raise ValueError("board defines %s more than once" % pin_type)
    if matches:
        return matches[0]
    if required:
        raise ValueError("board does not define required pin %s" % pin_type)
    return None


def pin_number(board, pin_type, required=False):
    """Return a typed pin's GPIO number, or ``None`` when it is optional."""
    definition = pin_definition(board, pin_type, required)
    return definition.get("number") if definition is not None else None


def import_reference(reference):
    """Resolve a ``module.attribute`` reference without importing a board."""
    module_name, attribute = reference.rsplit(".", 1)
    module = __import__(module_name, None, None, (attribute,))
    return getattr(module, attribute)
