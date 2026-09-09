"""Modern hardware integration, selected declaratively through BOARD_CONFIG.

Modules are imported only when selected by the platform factory. Device-specific
behavior belongs here; pins, wiring and panel geometry belong in board payloads.
Firmware-frozen drivers remain owned by their firmware build recipes.
"""
