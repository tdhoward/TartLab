"""Host checks for the native LVGL calculator's arithmetic and layouts."""
from pathlib import Path
import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


APP = Path(__file__).resolve().parents[1] / "src/files/help/calculator.py"


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.app = runpy.run_path(str(APP), init_globals={
            "_CALCULATOR_AUTOSTART": False})

    def enter(self, *keys):
        for key in keys:
            self.app["press"](key)
        return self.app["state"]["text"]

    def test_arithmetic_and_unary_operations(self):
        for keys, expected in (
                (("1", "2", "+", "3", "="), "15"),
                (("9", "-", "2", "="), "7"),
                (("6", "*", "7", "="), "42"),
                (("7", "/", "2", "="), "3.5"),
                (("9", "Sqrt"), "3"),
                (("5", "0", "%"), "0.5"),
                (("2", "+/-"), "-2"),
                ((".", "5", ".", "+", "1", "="), "1.5")):
            with self.subTest(keys=keys):
                self.enter("C")
                self.assertEqual(self.enter(*keys), expected)

    def test_errors_recover_and_entry_is_bounded(self):
        self.assertEqual(self.enter("8", "/", "0", "="), "Error")
        self.assertEqual(self.enter("2"), "2")
        self.assertEqual(self.enter("+/-", "Sqrt"), "Error")
        self.assertEqual(self.enter("C"), "0")
        self.assertEqual(self.enter("0", "0", "3"), "3")
        self.enter(*(["9"] * 30))
        self.assertEqual(len(self.app["state"]["text"]), 16)

    def test_lvgl_clicks_update_result_and_close_restores_screen(self):
        lv = MagicMock()
        lv.STATE.PRESSED = 32
        lv.font_montserrat_16 = object()
        for size in (20, 24, 28, 32, 40, 48):
            setattr(lv, "font_montserrat_%d" % size, None)
        buttons = []

        def button(parent):
            widget = MagicMock()
            buttons.append(widget)
            return widget

        def label(parent):
            widget = MagicMock()
            widget.get_width.return_value = 32
            widget.get_height.return_value = 16
            widget.get_y.return_value = 20
            return widget

        lv.button.side_effect = button
        lv.label.side_effect = label
        navigation = MagicMock()
        ui = self.app["CalculatorUI"](lv, SimpleNamespace(
            width=240, height=320, navigation=navigation))
        previous = ui.previous
        ui.show()
        self.assertEqual(len(buttons), 20)
        self.assertEqual(navigation.page.return_value.add.call_count, 20)
        keys = self.app["LABELS"]
        for key in ("7", "+", "2", "="):
            callback, event, data = buttons[keys.index(key)].add_event_cb.call_args.args
            self.assertEqual(event, lv.EVENT.CLICKED)
            callback(None)
        ui.result.set_text.assert_called_once_with("9")
        ui.close()
        navigation.page.return_value.close.assert_called_once()
        lv.screen_load.assert_called_with(previous)
        ui.screen.delete.assert_called_once()

    def test_keypads_fit_and_cover_all_operations(self):
        for width, height in ((320, 170), (240, 320), (320, 240),
                              (480, 320), (320, 480)):
            with self.subTest(size=(width, height)):
                margin, readout, boxes = self.app["keypad_layout"](width, height)
                self.assertEqual({box[0] for box in boxes}, set(self.app["LABELS"]))
                self.assertEqual(len(boxes), 20)
                for key, x, y, w, h in boxes:
                    self.assertGreaterEqual(x, margin)
                    self.assertGreaterEqual(y, margin + readout)
                    self.assertGreaterEqual(w, 40)
                    self.assertGreaterEqual(h, 24)
                    self.assertLessEqual(x + w, width - margin)
                    self.assertLessEqual(y + h, height - margin)


if __name__ == "__main__":
    unittest.main()
