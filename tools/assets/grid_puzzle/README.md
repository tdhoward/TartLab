# Grid puzzle original art

Original garden-ruin artwork generated for TartLab on 2026-09-11 using the
built-in image generation tool. No external game art, reference images, names,
or layouts were supplied. The prompt specified an overhead gardener in an
orange coat, slate masonry, ochre dirt/banks, turquoise water, and distinct
key/diamond/boulder/hazard silhouettes in an 8-by-8 sprite grid.

- `source.png`: unchanged generated RGBA source, 1254 by 1254 pixels.
- `sheet.png`: canonical editable 128-by-128 RGBA atlas, 16-by-16 tiles,
  fifteen opaque colors and binary transparency.
- `preview.png`: exact 6x nearest-neighbor preview of the canonical sheet.
- `index.json`: every named tile's rectangle, palette, source/RGBA/TS16 hashes.
- Runtime output: `src/files/assets/grid_puzzle.ts16`, **8,232 bytes**.

The import in `tools/build_grid_puzzle_sprites.py` removes thin generated cell
separators, downsamples each terrain tile to 16x16 and each object to 14x14 with
a transparent margin, thresholds alpha, removes magenta, and maps to the fixed
palette. Water's center uses only the three water colors. This makes the import
repeatable; the runtime never decodes the generated source or PNG files.

The canonical sheet can be edited directly. Preserve 16x16 alignment, binary
alpha, the fifteen-color limit, full opaque terrain cells, and the center-water
palette. The builder rejects violations rather than silently discarding sprites
or changing coordinates. It uses the existing `convert_ts16.encode()` encoder.

```powershell
python tools/build_grid_puzzle_sprites.py
python tools/build_grid_puzzle_sprites.py --check
```

To explicitly regenerate the canonical sheet from the retained original:

```powershell
python tools/build_grid_puzzle_sprites.py --from-source
```

Run from any directory. Pillow is a host-only dependency; no API call or asset
generation is needed to rebuild. The supplied hashes record the checked-in
result; rerun `--check` after changing Pillow or conversion tooling.

## Atlas (columns and rows start at zero)

| Row | Columns 0 through 7 |
| --- | --- |
| 0 | floor, wall 0, wall 1, wall 2, wall 3, wall 4, wall 5, wall 6 |
| 1 | wall 7, wall 8, wall 9, dirt 0, dirt 1, dirt 2, dirt 3, dirt 4 |
| 2 | dirt 5, dirt 6, dirt 7, dirt 8, dirt 9, key, diamond, boulder |
| 3 | locked exit, open exit, player N/E/S/W, snake W/E |
| 4 | spider N/E/S/W, emitter N/E/S/W |
| 5 | W0, W1, W2, spear tips N/E/S/W, teleporter/debug ring |
| 6 | W3, W4, W5, shaft N/S, shaft E/W, explosion frames 0/1/2 |
| 7 | W6, W7, W8, five reserved transparent cells |

False walls reuse the exact wall sprite. Teleporters draw ordinary floor during
normal play; the ring is reserved for inspection/experiments. Visual variants
do not change rules. All nine water tiles occupy full impassable cells, including
the parts drawn as banks. Future hazard frames are supplied now; hazard gameplay
remains gated until Phase 4.

`PuzzleArt` in the editable game contains the runtime atlas coordinates and
batch-prepares only the active room's required tiles through `SpriteSheet`.
Prepared RGB565 spans scale by positive integers. Restart retains compatible
sprites; room changes replace the cache, and exit/error clears it. The decoder
is released after preparation. No extra board framebuffer is used. Device heap
and transfer timing still require physical measurement.
