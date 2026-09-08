"""TartLab-owned boundary around board-specific startup hardware."""

import sys


BOARD_IDENTITY_FILE = "/device/board.json"
BOARD_RUNTIME_ROOT = "/board"


def board_runtime_path(identity_file=BOARD_IDENTITY_FILE):
    """Return the provisioned board's isolated runtime path, if present."""
    try:
        with open(identity_file, "r") as stream:
            try:
                import ujson as json
            except ImportError:
                import json
            identity = json.load(stream)
    except OSError:
        return None
    board_id = identity.get("board_id") if isinstance(identity, dict) else None
    if not isinstance(board_id, str) or not board_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
            for character in board_id):
        raise ValueError("protected board identity is invalid")
    return BOARD_RUNTIME_ROOT + "/" + board_id


def configure_paths(paths=None):
    """Add the protected board runtime, then the legacy compatibility paths."""
    if paths is None:
        paths = sys.path
    runtime_path = board_runtime_path()
    if runtime_path is not None and runtime_path not in paths:
        # Protected board support must precede release root and student code.
        # /device stays first because it owns the generated selector and local
        # calibration, but /files/user must never be able to shadow its import.
        insert_at = paths.index("/device") + 1 if "/device" in paths else 0
        paths.insert(insert_at, runtime_path)

    from tartlabutils.legacy_platform import configure_legacy_paths
    return configure_legacy_paths(paths)


_current_platform = None


def set_platform(platform):
    global _current_platform
    _current_platform = platform


def get_platform():
    global _current_platform
    if _current_platform is None:
        # Adult provisioning identifies the selected board in protected state.
        # Its isolated runtime is searched before historical /configs modules.
        configure_paths()
        import hdwconfig as hardware
        board = getattr(hardware, "BOARD_CONFIG", None)
        if board is not None:
            from tartlabutils.factory import create_platform
            _current_platform = create_platform(board)
        else:
            factory = getattr(hardware, "create_platform", None)
            if factory is not None:
                _current_platform = factory()
            else:
                from tartlabutils.legacy_platform import LegacyPlatform
                _current_platform = LegacyPlatform(hardware=hardware)
    return _current_platform
