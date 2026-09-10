"""Run modern image examples against the public drawing API on host surfaces."""

import builtins
import sys
import time
import types
import unittest
from unittest.mock import patch

from tests.test_app import FakeSurface, FakeSeedSurface, load_app
from tests.test_images import IMAGE_MODULES, ROOT, qoi, sprites


class ImageExampleTests(unittest.TestCase):
    def run_example(self, name, surface, touch=True):
        button_events = iter([[], [('A', True)], [('A', False)]])
        platform = types.SimpleNamespace(
            enter_game_mode=lambda: surface,
            capabilities={'touch': touch, 'buttons': not touch},
            read_button_events=lambda: next(button_events))
        app = load_app(platform)
        touches = iter([None, "stop"])
        app.TouchGrid = lambda *args: types.SimpleNamespace(read=lambda: next(touches))
        real_open = builtins.open

        def open_asset(path, *args, **kwargs):
            if isinstance(path, str) and path.startswith("files/assets/"):
                path = ROOT / "src" / path
            return real_open(path, *args, **kwargs)

        modules = {**IMAGE_MODULES, "tartlabutils.app": app, "tartlabutils.sprites": sprites,
                   "tartlabutils.platform": types.SimpleNamespace(get_platform=lambda: platform),
                   "tartlabutils.images.qoi": qoi, "bmp565": None,
                   "qoi_reader": None, "pydevices": None}
        path = ROOT / "src/files/help" / name
        scope = {"__name__": "__main__"}
        with patch.dict(sys.modules, modules), \
                patch("builtins.open", side_effect=open_asset), \
                patch.object(time, "sleep_ms", lambda _: None, create=True), \
                patch("random.choice", return_value="down"):
            exec(compile(path.read_bytes(), str(path), "exec"), scope)
        return scope

    def test_sprite_stops_on_button_release_without_touch(self):
        surface = FakeSurface(width=320, height=170)
        result = self.run_example('sprite.py', surface, touch=False)
        self.assertIsNone(result['stop_button'])
        self.assertTrue(surface.writes)
        self.assertEqual(result['unused'], 2)
        result['canvas'].close()

    def test_ts16_sheet_and_animation_render_on_both_surface_types(self):
        for surface_class, size in ((FakeSurface, (480, 222)),
                                    (FakeSeedSurface, (320, 480))):
            for example in ("display_ts16.py", "sprite.py"):
                with self.subTest(surface=surface_class, example=example):
                    surface = surface_class(width=size[0], height=size[1])
                    result = self.run_example(example, surface)
                    self.assertTrue(surface.writes)
                    canvas = result["canvas"]
                    background = bytes(canvas.buffer[:2])
                    self.assertNotEqual(canvas.buffer, background * (size[0] * size[1]))
                    for pixels, x, y, width, height in surface.writes:
                        self.assertEqual(len(pixels), width * height * 2)
                        self.assertTrue(0 <= x <= size[0] - width)
                        self.assertTrue(0 <= y <= size[1] - height)
                    canvas.close()

    def test_qoi_example_covers_image_once_in_small_strips(self):
        for surface_class in (FakeSurface, FakeSeedSurface):
            surface = surface_class(width=480, height=480)
            result = self.run_example("display_qoi.py", surface)
            image = result["image"]
            writes = [entry for entry in surface.writes if entry[3] == image.width]
            self.assertEqual(sum(entry[4] for entry in writes), image.height)
            self.assertTrue(all(entry[4] <= 8 for entry in writes))
            reference = qoi.QOIImage.open(str(ROOT / "src/files/assets/test.qoi"))
            expected = b"".join(bytes(pixels) for _, pixels in reference.iter_rgb565(
                rows=1, background=(0, 0, 0)))
            self.assertEqual(b"".join(entry[0] for entry in writes), expected)


if __name__ == "__main__":
    unittest.main()
