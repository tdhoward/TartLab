# Grid puzzle fixtures

`solutions.json` records successful timed solutions for both bundled teaching
rooms. `all_symbols.json` covers version-1 parsing and state construction.

`hazards.json` contains focused original rooms for the Phase 4 engine checks:

| Room | Scripted outcome |
| --- | --- |
| Moving cover | Wait: the spider leaves the snake's row at 150 ms and the player dies immediately. |
| Trapped neighbors | Wait one 10 ms tick: both trapped spiders disappear together; eight blast cells and four diamonds result. |
| Spear lane | Wait: activation at 10 ms, extensions at 50/90/130 ms; the final tip kills and stops before the wall. Moving north at 20 ms instead permits observing the harmless stopped shaft. |
| Blast reveals trap | Wait: a trapped spider clears the protecting boulder at 10 ms; the spear activates at 20 ms and first extends at 60 ms. Diamonds are disabled for this room. |
| Exit blast | Move east on the first tick: the player enters the active exit but the trapped spider's blast kills before completion. |

`test_grid_puzzle_hazards.py` adds small parameterized rooms for individual
blockers, priority orders, teleport contacts, deadlines, and rule overrides.
The MicroPython compatibility check also runs the five JSON scenarios.

Validate the fixture data without claiming successful campaign solutions:

```powershell
python tools/check_grid_puzzle_levels.py --levels tests/fixtures/grid_puzzle/hazards.json --report build/grid_puzzle/phase4-hazards.json
```

For device observation, save `hazards.json` as a separate user JSON file and
point an independent Python copy's `LEVEL_FILE` at it. To start at a specific
scenario, keep that room as the sole entry in the copy's `levels` array.
These are deliberately focused test situations, including unavoidable deaths;
they have not received physical readability/control/fairness acceptance.
