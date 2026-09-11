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
print("PASS: grid puzzle definitions, all symbols, fresh state, pairing and layouts")
