"""Run with the pinned MicroPython Unix executable; no device shims needed.

micropython tests/grid_puzzle_compat.py /absolute/path/to/TartLab
"""

import sys


root = sys.argv[1] if len(sys.argv) > 1 else "."
namespace = {"_GRID_PUZZLE_AUTOSTART": False}
with open(root + "/src/files/help/grid_puzzle.py") as source:
    exec(source.read(), namespace)
load = namespace["load_level_pack"]
create = namespace["create_state"]
for name in ("src/files/help/grid_puzzle_levels.json", "tests/fixtures/grid_puzzle/all_symbols.json"):
    pack = load(root + "/" + name)
    for definition in pack["levels"]:
        first = create(definition)
        assert len(first.terrain) == 192
        first.objects[0] = namespace["BOULDER"]
        fresh = create(definition)
        assert fresh.objects[0] == definition["objects"][0]
        assert fresh.elapsed_ms == 0
        for cell, twin in enumerate(definition["twins"]):
            if twin >= 0:
                assert definition["twins"][twin] == cell
                assert fresh.terrain[cell] == namespace["FLOOR"]
        assert fresh.remaining_keys == sum(1 for obj in fresh.objects if obj == namespace["KEY"])
choose_layout = namespace["choose_layout"]
assert choose_layout(480, 222).scale == 1
assert choose_layout(320, 480).rotation == 90
assert choose_layout(800, 480).scale == 2
import json
pack = load(root + "/src/files/help/grid_puzzle_levels.json")
namespace["validate_playable_pack"](pack)
with open(root + "/tests/fixtures/grid_puzzle/solutions.json") as stream:
    recordings = json.load(stream)["solutions"]
for recording in recordings:
    session = namespace["Session"](pack, recording["room"])
    events, index = recording["events"], 0
    for elapsed in range(0, recording["end_ms"], namespace["UPDATE_MS"]):
        while index < len(events) and events[index]["at_ms"] <= elapsed:
            event = events[index]
            if event["action"] == "press":
                session.direction = namespace["ACTION_DIRECTIONS"][event["direction"]]
            elif event["action"] == "release":
                session.direction = None
            elif event["action"] == "dismiss":
                assert namespace["dismiss_message"](session.state)
                session.direction = None
            index += 1
        session.advance(1)
    state = session.state
    expected = recording["expected"]
    assert state.status == namespace["COMPLETED"]
    assert state.score == expected["score"]
    assert state.bonus == expected["bonus"]
    assert state.elapsed_ms == expected["elapsed_ms"]
    assert session.banked_score == state.score + state.bonus
    session.restart()
    assert session.banked_score == 0
    assert session.state.elapsed_ms == 0
    assert session.state.remaining_keys == 1
controls = namespace["Controls"]()
layout = choose_layout(480, 222)
controls.poll(None, (), layout)
controls.poll(None, (("right", True),), layout)
assert controls.direction() == namespace["EAST"]
controls.reset()
controls.poll(None, (("right", False),), layout)
assert controls.direction() is None
# Exercise real autonomous steps and generated sprites on the same interpreter.
hazards = load(root + "/tests/fixtures/grid_puzzle/hazards.json")
for definition, duration, status, diamonds in zip(hazards["levels"],
        (150, 10, 130, 60, 10), ("DEAD", "PLAYING", "DEAD", "PLAYING", "DEAD"), (0, 4, 0, 0, 1)):
    state = create(definition)
    for elapsed in range(0, duration, namespace["UPDATE_MS"]):
        namespace["step"](state, namespace["EAST"] if definition["name"] == "Exit blast" else None)
    assert state.elapsed_ms == duration
    assert state.status == namespace[status]
    assert sum(obj == namespace["DIAMOND"] for obj in state.objects) == diamonds
    fresh = create(definition)
    assert all(actor.alive for actor in fresh.actors)
    assert not any(fresh.blast_until)
    assert not any(cell != -1 for cell in fresh.spear_at)
# Load only the real image/sprite package. The normal top-level package imports
# device updater/network services that do not belong in this Unix host check.
sys.path.insert(0, root + "/tests/fixtures/grid_puzzle/host_lib")
import tartlabutils
tartlabutils.__path__ = root + "/src/lib/tartlabutils"
for scale in (1, 2):
    art = namespace["PuzzleArt"](root + "/src/files/assets/grid_puzzle.ts16", scale)
    for definition in pack["levels"] + hazards["levels"]:
        art.prepare(definition)
        assert art.sprites[namespace["ART_PLAYER"]].width == 16 * scale
        cached = art.sprites[namespace["ART_PLAYER"]]
        art.prepare(definition)
        assert art.sprites[namespace["ART_PLAYER"]] is cached
    art.close()
    assert not art.sprites
print("PASS: definitions, all symbols, layouts, solutions, rollback, controls, autonomous hazards and 1x/2x art")
