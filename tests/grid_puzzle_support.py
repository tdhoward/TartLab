"""Shared host loader and small JSON-room authoring helpers (no copied rules)."""

from tools.check_grid_puzzle_levels import DEFAULT_ENGINE, DEFAULT_LEVELS, load_engine


ENGINE = load_engine()


def room(cells=None, **fields):
    rows = [[".."] * 16 for _ in range(12)]
    rows[0][0], rows[11][15] = "P.", "E."
    for (x, y), token in (cells or {}).items():
        rows[y][x] = token
    return {"name": "Contract fixture", "map": [" ".join(row) for row in rows], **fields}


def pack(level=None):
    return {"version": 1, "levels": [room() if level is None else level]}


def prepare_art(session, scale=1):
    from unittest.mock import patch
    from tests.image_support import IMAGE_MODULES
    session.art = ENGINE.PuzzleArt(str(DEFAULT_ENGINE.parents[1] / "assets/grid_puzzle.ts16"), scale)
    with patch.dict("sys.modules", IMAGE_MODULES):
        session.art.prepare(session.state.definition)
    return session.art
