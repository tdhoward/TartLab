"""Declarative board payload for the LilyGO T-Display-S3 Pro."""


BOARD_CONFIG = {
    "id": "lilygo_t_display_s3_pro",
    "pins": (
        {"type": "BUTTON", "number": 12},
        {"type": "BACKLIGHT", "number": 48, "active_high": True},
        {"type": "DISPLAY_RESET", "number": 47},
        {"type": "DISPLAY_DC", "number": 9},
        {"type": "DISPLAY_CS", "number": 39},
        {"type": "DISPLAY_SCK", "number": 18},
        {"type": "DISPLAY_MOSI", "number": 17},
        {"type": "DISPLAY_MISO", "number": 8},
        {"type": "TOUCH_SCL", "number": 6},
        {"type": "TOUCH_SDA", "number": 5},
        {"type": "TOUCH_RESET", "number": 13},
        {"type": "TOUCH_INTERRUPT", "number": 21},
    ),
    "display": {
        "driver": "st7796.ST7796",
        "adapter": "tartlabutils.modern_st7796",
        "native_size": (222, 480),
        "logical_size": (480, 222),
        "offset": (0, 49),
        "rotation": 270,
        "transfer_rows": 24,
        "reset_state": "STATE_LOW",
        "backlight_state": "STATE_PWM",
        "color_order": "BGR",
        "inversion": True,
        # The ST7796 native vertical-scroll axis becomes logical horizontal at
        # rotation 270. This exact MV=1 configuration passed the focused COM3
        # automated and visual qualification documented in the repository.
        "scroll": {"qualified_rotations": (270,)},
        "spi": {
            "host": 1,
            "frequency": 60_000_000,
        },
    },
    "touch": {
        "driver": "cst226.CST226",
        "rotation": 0,
        "i2c": {"host": 0, "frequency": 100_000},
        "pin_arguments": {
            "reset_pin": "TOUCH_RESET",
            "interrupt_pin": "TOUCH_INTERRUPT",
        },
        # This CST226SE fixture forgets its no-autosleep setting after a long
        # idle. Reassert it while IDE mode owns the touch input.
        "keep_awake": {"method": "_write_reg", "arguments": (0xFE, 0x01)},
    },
}
