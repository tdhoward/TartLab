"""Image-source contracts and pixel-level checks of format-independent sprites."""

import builtins
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.image_support import IMAGE_MODULES, images, qoi, sprites
from tests.test_images import encoded, rgb565


def native(red, green, blue):
    data = rgb565([(red, green, blue)])
    return data[0] | data[1] << 8


class Canvas:
    def __init__(self, width, height, background=1234):
        self.width, self.height = width, height
        self.pixels = [[background] * width for _ in range(height)]

    def hline(self, x, y, width, color):
        if not (0 <= y < self.height and 0 <= x <= self.width - width):
            raise AssertionError("span lies outside canvas")
        self.pixels[y][x:x + width] = [color] * width


class SpriteSourceTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(sys.modules, IMAGE_MODULES))
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def qoi_file(self, width, height, colors, name="image.qoi"):
        payload = encoded(width, height, b"".join(bytes((255,) + c) for c in colors))
        path = self.directory / name
        path.write_bytes(payload)
        return path

    def ts16_file(self, width, height, colors, indices, name="image.ts16"):
        palette = list(colors) + [(0, 0, 0)] * (16 - len(colors))
        packed = bytearray((len(indices) + 1) // 2)
        for position, index in enumerate(indices):
            packed[position // 2] |= index << (0 if position & 1 else 4)
        path = self.directory / name
        path.write_bytes(b"TS16" + struct.pack("<HH", width, height) +
                         rgb565(palette) + packed)
        return path

    def draw(self, frame, background=1234):
        canvas = Canvas(frame.width, frame.height, background)
        frame.draw(canvas, 0, 0, (0, 0, frame.width, frame.height))
        return canvas.pixels

    def test_alpha_cutoff_preserves_source_color_at_128_and_above(self):
        alphas = (0, 1, 127, 128, 254, 255)
        colors = [(239, 117, 63, a) for a in alphas]
        path = self.qoi_file(6, 1, colors)
        sheet = sprites.SpriteSheet(str(path))
        self.assertEqual(self.draw(sheet.sprite(0, 0, 6, 1)),
                         [[1234] * 3 + [native(239, 117, 63)] * 3])
        # The row contract retains alpha; the sprite consumer selects the cutoff.
        rows = list(sheet.image.iter_rows())
        self.assertEqual(bytes(rows[0][2]), bytes(alphas))

    def test_background_composites_original_channels_before_quantization(self):
        colors = [(7, 3, 7, a) for a in (0, 1, 127, 128, 254, 255)]
        background = (213, 97, 165)
        path = self.qoi_file(6, 1, colors)
        sheet = sprites.SpriteSheet(str(path), background=background)
        expected = [native(*tuple((c * a + b * (255 - a) + 127) // 255
                                  for c, b in zip((r, g, blue), background)))
                    for r, g, blue, a in colors]
        self.assertEqual(self.draw(sheet.sprite(0, 0, 6, 1)), [expected])
        self.assertEqual(sheet.color_at(0, 0), native(*background))
        self.assertEqual(bytes(next(sheet.image.iter_rows(background=background))[2]),
                         b"\xff" * 6)

    def test_opaque_black_and_transparent_pixels_with_the_same_rgb_stay_distinct(self):
        qoi_path = self.qoi_file(3, 1, [(0, 0, 0, a) for a in (255, 0, 255)])
        ts16_path = self.ts16_file(3, 1, [(0, 0, 0), (0, 0, 0)], [1, 0, 1])
        for path in (qoi_path, ts16_path):
            with self.subTest(path=path):
                self.assertEqual(self.draw(sprites.SpriteSheet(str(path)).sprite(0, 0, 3, 1)),
                                 [[0, 1234, 0]])
                composite = sprites.SpriteSheet(str(path), background=(0, 0, 255))
                self.assertEqual(self.draw(composite.sprite(0, 0, 3, 1)),
                                 [[0, native(0, 0, 255), 0]])

    def test_formats_match_for_odd_widths_crops_scaling_flips_and_clipping(self):
        palette = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
        indices = [0, 1, 1, 2, 0, 3, 0, 2, 1, 1, 2, 2, 3, 0, 1]
        qoi_path = self.qoi_file(5, 3, [palette[i] + (255 if i else 0,) for i in indices])
        ts16_path = self.ts16_file(5, 3, palette, indices)
        results = []
        for path in (qoi_path, ts16_path):
            sheet = sprites.SpriteSheet(str(path))
            frames = sheet.sprites([(1, 1, 4, 2), (0, 0, 3, 3), (1, 1, 4, 2)],
                                   scale=2, flip_x=True)
            results.append([self.draw(frame) for frame in frames])
            canvas = Canvas(4, 3)
            frames[0].draw(canvas, 0, 0, (3, 1, 4, 3), 3, 1)
            self.assertEqual(canvas.pixels, [row[3:7] for row in results[-1][0][1:4]])
        self.assertEqual(*results)
        expected = [[1234 if i == 0 else native(*palette[i]) for i in indices[y * 5 + 1:y * 5 + 5]]
                    for y in (1, 2)]
        expected = [[pixel for pixel in row[::-1] for _ in range(2)]
                    for row in expected for _ in range(2)]
        self.assertEqual(results[0][0], expected)

    def test_unsorted_overlapping_batch_uses_one_file_pass_and_validates_tail(self):
        path = self.qoi_file(4, 4, [(i * 16, 255 - i * 16, 80, 255) for i in range(16)])
        sheet = sprites.SpriteSheet(str(path))
        regions = [(2, 2, 2, 2), (0, 0, 2, 1), (1, 1, 3, 2)]
        with patch.object(qoi, "open", wraps=builtins.open, create=True) as opened:
            batch = sheet.sprites(regions)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual([self.draw(frame) for frame in batch],
                         [self.draw(sheet.sprite(*crop)) for crop in regions])
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            sheet.sprite(0, 0, 1, 1)

    def test_custom_decoder_requires_no_format_registration(self):
        class Decoder:
            width, height = 2, 1

            def iter_rows(self, x=0, y=0, width=None, height=None, background=None):
                self.arguments = (x, y, width, height, background)
                try:
                    yield 0, b"\xf8\x00\x00\x00", b"\xff\x7f"
                finally:
                    self.closed = True

        image = Decoder()
        sheet = sprites.SpriteSheet(image)
        self.assertEqual(self.draw(sheet.sprite(0, 0, 2, 1)), [[native(255, 0, 0), 1234]])
        self.assertEqual(image.arguments, (0, 0, 2, 1, None))
        self.assertTrue(image.closed)

    def test_decoder_is_closed_if_sprite_preparation_fails(self):
        path = self.qoi_file(2, 2, [(255, 0, 0, 255)] * 4)
        image = qoi.QOIImage.open(str(path))
        stream = io.BytesIO(path.read_bytes())
        with patch.object(qoi, "open", return_value=stream, create=True), \
                patch.object(sprites, "_append_spans", side_effect=MemoryError):
            with self.assertRaises(MemoryError):
                sprites.SpriteSheet(image).sprite(0, 0, 2, 2)
        self.assertTrue(stream.closed)

    def test_cropped_qoi_rows_use_bounded_reads_and_borrow_both_buffers(self):
        path = self.qoi_file(11, 100, [(i % 256, 0, 0, i % 256) for i in range(1100)])
        image = qoi.QOIImage.open(str(path))

        class BoundedStream(io.BytesIO):
            def read(self, size=-1):
                if not 0 <= size <= 512:
                    raise AssertionError("unbounded read")
                return super().read(size)

        stream = BoundedStream(path.read_bytes())
        with patch.object(qoi, "open", return_value=stream, create=True):
            rows = image.iter_rows(3, 70, 2, 2)
            y, pixels, alpha = next(rows)
            saved = bytes(alpha)
            self.assertEqual((y, len(pixels), len(alpha)), (70, 4, 2))
            second_y, second_pixels, second_alpha = next(rows)
            self.assertEqual(second_y, 71)
            self.assertIs(pixels.obj, second_pixels.obj)
            self.assertIs(alpha.obj, second_alpha.obj)
            self.assertNotEqual(saved, bytes(alpha))
            rows.close()
        self.assertTrue(stream.closed)

    def test_detection_uses_magic_and_lazily_imports_only_selected_format(self):
        path = self.qoi_file(1, 1, [(0, 0, 0, 255)], name="actually.ts16")
        indexed = self.ts16_file(1, 1, [(0, 0, 0)], [0], name="actually.qoi")
        with patch.dict(sys.modules):
            sys.modules.pop("tartlabutils.images.qoi", None)
            sys.modules.pop("tartlabutils.images.ts16", None)
            self.assertEqual(type(images.open_image(str(indexed))).__name__, "TS16Image")
            self.assertNotIn("tartlabutils.images.qoi", sys.modules)
            self.assertEqual(type(images.open_image(str(path))).__name__, "QOIImage")
        path.write_bytes(b"nope")
        with self.assertRaisesRegex(ValueError, "unsupported image format"):
            images.open_image(str(path))

    def test_invalid_options_fail_before_decoding_and_empty_batch_does_not_read(self):
        path = self.qoi_file(2, 2, [(0, 0, 0, 255)] * 4)
        sheet = sprites.SpriteSheet(str(path))
        with patch.object(qoi, "open", side_effect=AssertionError("unexpected read"), create=True):
            self.assertEqual(sheet.sprites([]), [])
            for crop in ((-1, 0, 1, 1), (0, 0, 0, 1), (1, 1, 2, 2), (0.5, 0, 1, 1)):
                with self.assertRaises(ValueError):
                    sheet.sprite(*crop)
                with self.assertRaises(ValueError):
                    list(sheet.image.iter_rows(*crop))
            for scale in (0, -1, 1.5, 65536):
                with self.assertRaises(ValueError):
                    sheet.sprite(0, 0, 1, 1, scale=scale)
            for background in ((0, 0), (0, 0, 256), (0, -1, 0), "bad", 42):
                with self.assertRaises(ValueError):
                    sprites.SpriteSheet(sheet.image, background=background)


if __name__ == "__main__":
    unittest.main()
