"""Display a compact 15-color sprite sheet with transparent pixels."""

from tartlabutils.app import DirectCanvas, game_surface, rgb565
from tartlabutils.sprites import SpriteSheet


surface = game_surface()
canvas = DirectCanvas(surface)
sheet = SpriteSheet("files/assets/warrior.ts16")
canvas.fill(rgb565(30, 40, 50))

# Center the sheet. A smaller display clips its edges.
x = (canvas.width - sheet.width) // 2
y = (canvas.height - sheet.height) // 2
clip = (0, 0, canvas.width, canvas.height)
# Prepare and draw a row at a time rather than retaining a whole sheet of runs.
for row in range(sheet.height):
    sheet.sprite(0, row, sheet.width, 1).draw(canvas, x, y + row, clip)
canvas.show()
