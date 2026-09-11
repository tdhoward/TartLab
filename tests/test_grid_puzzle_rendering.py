import unittest

from tests.grid_puzzle_support import ENGINE as g, room


class RecordingCanvas:
    def __init__(self, *args, **kwargs):
        self.commands = []
        self.closed = False

    def fill(self, *args):
        self.commands.append(("fill", args))

    def rect(self, *args):
        self.commands.append(("rect", args))

    def text(self, *args):
        self.commands.append(("text", args))

    def show(self):
        self.commands.append(("show", ()))

    def close(self):
        self.closed = True


class GridPuzzleLayoutTests(unittest.TestCase):
    def test_layouts_fit_entire_room_hud_and_nonoverlapping_controls(self):
        cases = [(480, 222, 1, "side", 0), (222, 480, 1, "side", 90),
                 (320, 480, 1, "side", 90), (256, 328, 1, "below", 0),
                 (800, 480, 2, "side", 0), (512, 520, 2, "below", 0)]
        for width, height, scale, placement, rotation in cases:
            with self.subTest(size=(width, height)):
                layout = g.choose_layout(width, height)
                self.assertEqual((layout.scale, layout.placement, layout.rotation), (scale, placement, rotation))
                bx, by, bw, bh = layout.board
                self.assertEqual((bw, bh), (256 * scale, 192 * scale))
                self.assertGreaterEqual(by, g.HUD_HEIGHT)
                rectangles = [layout.board] + [rect for _, rect in layout.controls]
                for i, (x, y, w, h) in enumerate(rectangles):
                    self.assertGreaterEqual(min(x, y), 0)
                    self.assertLessEqual(x + w, layout.width)
                    self.assertLessEqual(y + h, layout.height)
                    for x2, y2, w2, h2 in rectangles[i + 1:]:
                        self.assertTrue(x + w <= x2 or x2 + w2 <= x or y + h <= y2 or y2 + h2 <= y)

    def test_unsupported_display_and_input_fail_before_acquisition(self):
        for width, height in ((170, 320), (320, 240), (255, 327)):
            with self.subTest(size=(width, height)), self.assertRaisesRegex(ValueError, "cannot fit"):
                g.choose_layout(width, height)
        with self.assertRaisesRegex(ValueError, "needs touch"):
            g.choose_layout(480, 320, touch=False, button_names=("left", "right"))
        layout = g.choose_layout(320, 240, touch=False, button_names=tuple(g.BUTTON_ACTIONS))
        self.assertEqual(layout.placement, "buttons")
        smallest = g.choose_layout(256, 224, touch=False, button_names=tuple(g.BUTTON_ACTIONS))
        self.assertLessEqual(smallest.board[1] + smallest.board[3], smallest.readout[1])

    def test_touch_round_trip_for_every_cell_and_control_in_both_orientations(self):
        for width, height in ((480, 222), (222, 480), (320, 480), (800, 480)):
            layout = g.choose_layout(width, height)
            bx, by, _, _ = layout.board
            def native(x, y):
                # DirectCanvas's documented native pixel mapping at 90 degrees.
                return (y, height - 1 - x) if layout.rotation else (x, y)
            for cell in range(192):
                x = bx + (cell % 16) * layout.tile_size + layout.tile_size // 2
                y = by + (cell // 16) * layout.tile_size + layout.tile_size // 2
                logical = layout.logical_point(native(x, y), height)
                self.assertEqual(layout.cell_from_point(*logical), cell)
            for action, (x, y, w, h) in layout.controls:
                logical = layout.logical_point(native(x + w // 2, y + h // 2), height)
                self.assertEqual(layout.action_from_point(*logical), action)
                self.assertEqual(layout.cell_from_point(*logical), -1)
            self.assertEqual(layout.cell_from_point(bx - 1, by), -1)
            self.assertEqual(layout.action_from_point(-1, -1), None)

    def test_normal_probe_conceals_false_walls_and_pads_exactly(self):
        layout = g.choose_layout(480, 320)
        hidden = g.create_state(g.validate_level(room({(3, 3): "F4", (4, 3): "T0", (5, 3): "T0"})))
        visible = g.create_state(g.validate_level(room({(3, 3): "#4"})))
        first, second, debug = RecordingCanvas(), RecordingCanvas(), RecordingCanvas()
        g.draw_probe(first, hidden, layout, 0, None)
        g.draw_probe(second, visible, layout, 0, None)
        g.draw_probe(debug, hidden, layout, 0, None, True)
        self.assertEqual(first.commands, second.commands)
        self.assertNotEqual(first.commands, debug.commands)


if __name__ == "__main__":
    unittest.main()
