"""Declarative board payload for the Elecrow DLE06235B."""


BOARD_CONFIG = {
    "id": "elecrow_dle06235b",
    "pins": (
        {"type": "BACKLIGHT", "number": 41, "active_high": True},
        {"type": "DISPLAY_RESET", "number": 48},
        {"type": "DISPLAY_DC", "number": -1},
        {"type": "DISPLAY_CS", "number": 10},
        {"type": "DISPLAY_SCK", "number": 12},
        {"type": "DISPLAY_DATA_0", "number": 11},
        {"type": "DISPLAY_DATA_1", "number": 13},
        {"type": "DISPLAY_DATA_2", "number": 14},
        {"type": "DISPLAY_DATA_3", "number": 9},
        {"type": "TOUCH_SCL", "number": 39},
        {"type": "TOUCH_SDA", "number": 38},
    ),
    "display": {
        "driver": "st77922.ST77922",
        "adapter": "tartlabutils.modern_st77922",
        "native_size": (320, 480),
        "logical_size": (320, 480),
        "rotation": 0,
        "transfer_rows": 24,
        "reset_state": "STATE_LOW",
        "backlight_state": "STATE_PWM",
        "spi": {
            "host": 2,
            "frequency": 40_000_000,
            "quad": True,
            "quad_pin_types": (
                "DISPLAY_DATA_0",
                "DISPLAY_DATA_1",
                "DISPLAY_DATA_2",
                "DISPLAY_DATA_3",
            ),
        },
    },
    "touch": {
        "driver": "st77922_touch.ST77922Touch",
        "rotation": 0,
        "i2c": {"host": 0, "frequency": 100_000},
    },
}
