"""Minimal frozen Python payload for the Phase 5 PyDevices comparison."""

# Keep the alternative honest and reproducible: freeze only the runtime files
# used by the T-Display-S3 Pro adapter, not the complete PyDevices repository.
freeze(
    "/sources/pydevices/lib",
    (
        "appdev/__init__.py",
        "appdev/_hostloop.py",
        "appdev/app.py",
        "appdev/devices.py",
        "displaydev/__init__.py",
        "displaydev/busdisplay.py",
        "multimer/__init__.py",
        "multimer/_async_timer.py",
        "multimer/_asyncio_loader.py",
        "multimer/_core.py",
        "multimer/_schedule.py",
        "multimer/_ticks.py",
        "multimer/auto.py",
        "multimer/machine.py",
    ),
    opt=3,
)
module("events.py", base_path="/sources/pydevices/lib", opt=3)
module("keys.py", base_path="/sources/pydevices/lib", opt=3)
module("st7796.py", base_path="/sources/pydevices/drivers/display", opt=3)
module("cst226.py", base_path="/sources/pydevices/drivers/touch", opt=3)
