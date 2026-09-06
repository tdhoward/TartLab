# Racer sprite sheet and difficulty

`isometric-source.png` supplies the animals and objects; `car-topdown-source.png`
supplies the revised car cell. Both were generated with the built-in imagegen
tool. The car points directly away from the player with a higher camera angle,
more roof and a shorter rear face; the animals and objects are preserved.
`source.png` retains the original overhead reference. `sheet.png` previews the
packed atlas. Only `src/files/assets/racer.ts16` is needed on the device:
**7,208 bytes**, including palette and header.

The car is drawn at twice the sheet's pixel size (a 64 by 64 sprite cell),
using integer scaling prepared once at startup. Its collision radius and
steering clearance scale with it; redraw bounds follow the sprite dimensions.
The on-device atlas stays the same size.

The cow also uses 2x integer scaling (a 64 by 64 sprite cell), with matching
collision and redraw bounds. Its spawn clearance keeps it inside the road.

Rebuild with `python tools/build_racer_sprites.py` (host dependency: Pillow).
The packer extracts alpha or magenta color-key bounds, samples at game resolution
without smoothing, quantizes to sixteen colors, and adds road swatches, a lane
marker and Pillow's built-in bitmap font. No runtime image or font dependencies.

Atlas layout (224 by 64 pixels):

- Seven 32 by 32 cells at y=0: car, cow, pylon, oil, coin, capybara, chicken.
- Lane marker at (0, 32), size 7 by 8.
- Solid-color swatches at (9..23, 32) for efficient background fills.
- ASCII 32..95 at y=40, 26 glyphs per row, each 6 by 8.

TS16 contains `TS16`, little-endian 16-bit width and height, sixteen big-endian
RGB565 palette entries, and row-major 4-bit indices (high nibble first). Index
zero is transparent. The reusable loader caches compact horizontal runs, with
mirrored animal variants prepared once at startup. It does no file I/O or
image decoding during animation. Racer owns the atlas coordinates, HUD, game
rules, animal movement, difficulty and layout.

## Difficulty

The HUD's L1-L5 indicator follows elapsed simulation time; crashes pause it and
restarting resets the entire progression. The introduction supplies an easy
coin on the player's line and one cow away from it.

| Level | Starts at | Object cap | Spawn gap (road pixels) | New behavior |
| --- | --- | --- | --- | --- |
| 1 | 0 s | 2 | 220 | Slower road and generous spacing |
| 2 | 20 s | 3 | 160 | More traffic |
| 3 | 45 s | 4 | 120 | Capybaras; more hazards than coins |
| 4 | 70 s | 4 | 96 | Denser replacement traffic |
| 5 | 100 s | 4 | 80 | Chickens join the crossing hazards |

The cap includes coins and animals, excluding the player's car. Animals have
spawn priority once due, with at most one of each type present. Capybaras recur
no sooner than 18 seconds after a spawn; chickens use 12 seconds. An animal
appears at the next available spawn opportunity after its unlock. Both travel
with the road while crossing horizontally and disappear at the opposite road
edge (capybaras) or scroll off the bottom (chickens). Each capybara receives one
constant pace at spawn. Its speed targets 40-70% of the usable road width by the
end of the player's passing window, using the current road speed, road width,
vertical distance and collision radii. This gives individual speed variation
while keeping even the fastest capybara on the road through the encounter.
Chickens choose a new action every 200-650 ms: stop, head left or head right at
48-120 px/s. They reflect at road edges and keep their last facing direction
while stopped. All animal contacts cause a crash.

Road speed increases with distance in five steps: 64, 80, 96, 112 and 128 px/s,
at 0, 1200, 2800, 5200 and 8400 road pixels. The object cap remains four.

## Renderer limit (initial isometric revision)

Retest after animal tuning and the higher-camera car: four objects at the new
maximum road speed of 128 px/s, including both animals and steering, averaged
76.6 ms, with a 97.7 ms 95th percentile and 100.4 ms maximum (24 samples).
On-device encounter checks verified 23/32/41 px/s capybaras in both directions
remaining on the road through the full pass, and chickens staying inside the
road until culled at the bottom. Current evidence is in the ignored
`hardware_test_artifacts/racer-animal-tuning/` directory.

COM18 measurements on the connected Elecrow board, 320 by 480 logical pixels,
dirty-region renderer, 24 samples per workload, final road speed 96 px/s, two
50 ms simulation updates per frame, steering, HUD updates and both animal types:

| Road objects | Mean work | 95th percentile | Maximum |
| --- | --- | --- | --- |
| 2 | 61.7 ms | 84.6 ms | 85.8 ms |
| 4 | 79.3 ms | 98.6 ms | 143.6 ms |
| 5 | 87.9 ms | 109.3 ms | 109.4 ms |
| 6 | 93.3 ms | 110.3 ms | 125.2 ms |

Four is the conservative cap: its 95th percentile fits the 100 ms bounded
simulation budget. These are sampled work times, not a guaranteed frame rate;
the isolated maximum shows that occasional slower frames still occur.
Local measurements and device backups are under the ignored
`hardware_test_artifacts/racer-isometric/` directory.

## Imagegen prompts

Latest higher-camera car adjustment (only the generated car cell is packed):

> Edit ONLY the red CAR in the top-left cell of this game sprite atlas. Keep all six other sprites and every cell position unchanged. Raise the camera above the car: a moderately MORE TOP-DOWN view, approximately 65 degrees looking down toward the road, instead of the current low rear view. The car must point DIRECTLY AWAY from the player toward 12 o'clock, perfectly vertical centerline and symmetric left/right sides. Show substantially more roof and some front windshield toward top, rear window below roof, and a much shorter rear vertical face/bumper at bottom. The rear taillights should be a small strip near bottom, not dominate the sprite. Car sits level on the road, does not look nose-down or tipped forward. Preserve red paint, blue windows, black tires, compact chunky pixel art, no diagonal rotation. Slightly longer north-south silhouette than width. Maintain some rear depth, not completely flat overhead. All background stays uniform magenta #FF00FF, no shadows/checkerboard. No other changes to cow, cone, oil, coin, capybara, chicken. Same 4-column 2-row atlas.

Initial isometric revision:

> Revise this game's sprite art into a consistent ISOMETRIC / elevated three-quarter pixel-art style. Reference image is the existing game's subjects and colors only. Output a new atlas on truly transparent background: exactly FOUR equal columns and TWO equal rows, square cells, total aspect ratio 2:1, ample transparent separation, no labels or grid lines. Seven individual sprites in fixed order: TOP ROW 1 red sports car viewed from ABOVE AND BEHIND, driving away toward upper part of image, clearly show REAR bumper, red tail lights, back window, roof and one side; 2 black-and-white COW facing RIGHT SIDEWAYS in three-quarter side view, distinct four legs, udder, horns and pink muzzle, easy to recognize; 3 orange traffic cone/pylon with white stripe and visible diamond-shaped base in isometric view; 4 dark purple/navy oil slick lying flat in an isometric diamond plane with restrained blue sheen. BOTTOM ROW 1 gold coin standing upright in three-quarter view, visible thickness and embossed star; 2 large brown CAPYBARA walking RIGHT, obvious blunt rectangular snout, small round ears, stocky body, short legs, elevated side view; 3 white CHICKEN walking RIGHT, red comb and wattle, yellow beak and legs, visible wings and tail in elevated side view; 4 EMPTY transparent cell. Each object centered in its cell, occupies 65-75% of cell. Actual retro game pixel art designed to read at 32x32 pixels, bold silhouettes, limited flat colors, chunky clean edges, no fine texture, no gradients, no scenery or text. Car larger visually than chicken, capybara broad. Consistent lighting from upper left. IMPORTANT car faces away, cow faces sideways, all art has visible height/depth rather than a flat overhead view.

Background correction (the first revision baked in a checkerboard):

> Precise background replacement for game sprite atlas. Keep the seven sprite subjects, their positions, the 4-column 2-row grid, and their isometric orientations EXACTLY as in input. Replace the entire white and gray checkerboard background with one perfectly uniform pure MAGENTA #FF00FF color. No checkerboard anywhere. Also remove all cast ground shadows, making them magenta too. Preserve the white parts INSIDE cow, cone, and chicken. Hard, clean pixel-art object boundaries, zero antialias around edges, flat magenta background all around each isolated sprite. Do not add any objects or text. Keep final cell bottom right entirely magenta.

Final car orientation correction:

> Edit ONLY the CAR in the TOP LEFT cell of this sprite atlas. Preserve all six other sprites, grid layout, positions and uniform magenta background unchanged. Critical correction: the red car must drive DIRECTLY AWAY from the viewer, toward 12 o'clock, absolutely no diagonal rotation. Camera is centered behind the car and elevated: see the rear bumper and two symmetric red taillights at the bottom, rear window in the middle, and roof above. Symmetric rear view, both left and right tires equally visible. The car's long centerline is EXACTLY VERTICAL. No view of one side more than the other. No front headlights facing us. Give the car depth with the visible vertical rear face below its sloped back window and roof; not a flat overhead drawing. Crisp chunky pixel art readable at 30x30 pixels. Center this new car in the exact existing top-left square cell. Keep all background uniform magenta #FF00FF, no shadows or checkerboard. Do not change the cow, cone, oil, coin, capybara or chicken.
