"""Construct modern platforms from declarative board payloads."""

from tartlabutils.board import (
    import_reference,
    pin_definition,
    pin_number,
    validate_board_config,
)
from tartlabutils.modern import ModernDisplayController, ModernPlatform


def _rotation(lvgl, degrees):
    return getattr(lvgl.DISPLAY_ROTATION, "_" + str(degrees))


def _spi(board, machine, lcd_bus):
    display = board["display"]
    config = display["spi"]
    spi_options = {
        "host": config["host"],
        "sck": pin_number(board, "DISPLAY_SCK", True),
    }
    quad_types = config.get("quad_pin_types")
    if quad_types:
        spi_options["quad_pins"] = tuple(
            pin_number(board, pin_type, True) for pin_type in quad_types)
    else:
        spi_options["mosi"] = pin_number(board, "DISPLAY_MOSI", True)
        spi_options["miso"] = pin_number(board, "DISPLAY_MISO", True)
    spi = machine.SPI.Bus(**spi_options)

    bus_options = {
        "spi_bus": spi,
        "freq": config["frequency"],
        "dc": pin_number(board, "DISPLAY_DC", True),
        "cs": pin_number(board, "DISPLAY_CS", True),
    }
    if config.get("quad"):
        bus_options["quad"] = True
    return spi, lcd_bus.SPIBus(**bus_options)


def _buffers(display, bus, lcd_bus):
    flags = lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA
    width = display["logical_size"][0]
    size = width * display["transfer_rows"] * 2
    first = bus.allocate_framebuffer(size, flags)
    second = bus.allocate_framebuffer(size, flags)
    if first is None or second is None:
        raise MemoryError("unable to allocate dual DMA display buffers")
    return flags, first, second


def _panel(board, bus, buffers, lvgl):
    display = board["display"]
    driver = import_reference(display["driver"])
    driver_module = __import__(
        display["driver"].rsplit(".", 1)[0], None, None, ("*",))
    backlight = pin_definition(board, "BACKLIGHT", True)
    native_width, native_height = display["native_size"]
    offset_x, offset_y = display.get("offset", (0, 0))
    options = {
        "data_bus": bus,
        "display_width": native_width,
        "display_height": native_height,
        "frame_buffer1": buffers[0],
        "frame_buffer2": buffers[1],
        "reset_pin": pin_number(board, "DISPLAY_RESET", True),
        "reset_state": getattr(
            driver_module, display.get("reset_state", "STATE_LOW")),
        "backlight_pin": backlight["number"],
        "color_space": lvgl.COLOR_FORMAT.RGB565_SWAPPED,
        "rgb565_byte_swap": False,
    }
    if offset_x or offset_y:
        options["offset_x"] = offset_x
        options["offset_y"] = offset_y
    backlight_state = display.get("backlight_state")
    if backlight_state is not None:
        options["backlight_on_state"] = getattr(
            driver_module, backlight_state)
    elif hasattr(driver_module, "STATE_HIGH") and hasattr(
            driver_module, "STATE_LOW"):
        options["backlight_on_state"] = getattr(
            driver_module,
            "STATE_HIGH" if backlight.get("active_high", True)
            else "STATE_LOW",
        )
    color_order = display.get("color_order")
    if color_order is not None:
        options["color_byte_order"] = getattr(
            driver_module, "BYTE_ORDER_" + color_order)

    panel = driver(**options)
    panel.set_backlight(0)
    panel.reset()
    panel.init()
    inversion = display.get("inversion")
    if inversion is not None:
        panel.set_color_inversion(inversion)
    panel.set_rotation(_rotation(lvgl, display["rotation"]))
    return panel


def _touch(board, lvgl):
    import i2c

    config = board["touch"]
    driver = import_reference(config["driver"])
    driver_module = __import__(
        config["driver"].rsplit(".", 1)[0], None, None, ("*",))
    bus_config = config["i2c"]
    i2c_bus = i2c.I2C.Bus(
        host=bus_config["host"],
        scl=pin_number(board, "TOUCH_SCL", True),
        sda=pin_number(board, "TOUCH_SDA", True),
        freq=bus_config["frequency"],
        use_locks=False,
    )
    device = i2c.I2C.Device(
        bus=i2c_bus,
        dev_id=getattr(driver_module, config.get("address", "I2C_ADDR")),
        reg_bits=getattr(driver_module, config.get("register_bits", "BITS")),
    )
    options = {"startup_rotation": _rotation(lvgl, config["rotation"])}
    for argument, pin_type in config.get("pin_arguments", {}).items():
        options[argument] = pin_number(board, pin_type, True)
    return i2c_bus, device, driver(device, **options)


def _touch_keep_awake(pointer, config):
    call = config.get("keep_awake")
    if call is None:
        return None
    method = getattr(pointer, call["method"])
    arguments = tuple(call.get("arguments", ()))
    return lambda: method(*arguments)


def create_platform(board):
    """Create a modern platform using only values from ``BOARD_CONFIG``."""
    import lcd_bus
    import lvgl as lv
    import machine
    import task_handler

    validate_board_config(board)
    spi, bus = _spi(board, machine, lcd_bus)
    flags, first, second = _buffers(board["display"], bus, lcd_bus)
    panel = _panel(board, bus, (first, second), lv)
    i2c_bus, touch_device, pointer = _touch(board, lv)
    handler = task_handler.TaskHandler()
    lv_display = lv.display_get_default()

    adapter_reference = board["display"].get("adapter")
    if adapter_reference is None:
        width, height = board["display"]["logical_size"]
        offset_x, offset_y = board["display"].get("offset", (0, 0))
        controller = ModernDisplayController(
            bus, panel, lv_display, lv, handler, pointer,
            width=width, height=height, offset_x=offset_x, offset_y=offset_y,
            allocation_flags=flags,
            buffer_allocator=lcd_bus.allocate_buffer,
            buffer_free=lcd_bus.free_buffer,
        )
        platform_class = ModernPlatform
    else:
        adapter = __import__(adapter_reference, None, None, ("*",))
        controller = adapter.create_controller(
            board, bus, panel, lv_display, lv, handler, pointer, flags,
            lcd_bus)
        platform_class = adapter.Platform

    platform = platform_class(
        controller,
        panel,
        pointer,
        ide_button_pin=pin_number(board, "BUTTON"),
        lvgl=lv,
        touch_keep_awake=_touch_keep_awake(pointer, board["touch"]),
    )
    platform.board = board
    platform._spi_bus = spi
    platform._i2c_bus = i2c_bus
    platform._touch_device = touch_device
    platform.clear_display()
    panel.set_backlight(100)
    return platform
