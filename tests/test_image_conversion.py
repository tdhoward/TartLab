"""Optional Pillow checks of asset conversion, independent of device builds."""

import io
from pathlib import Path
import tempfile
import unittest

from tests.test_images import ROOT, load, qoi, rgb565, sprites

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow is required only for host asset conversion")
class ImageConversionTests(unittest.TestCase):
    def test_warrior_conversion_is_reproducible_and_preserves_transparent_mask(self):
        converter = load("test_ts16_encoder", "tools/convert_ts16.py")
        with Image.open(ROOT / "src/files/assets-legacy/warrior.bmp") as original:
            payload = converter.encode(original, transparent_corner=True)
            pixels = list(original.convert("RGB").getdata())
        self.assertEqual(payload, (ROOT / "src/files/assets/warrior.ts16").read_bytes())
        sheet = sprites.SpriteSheet(str(ROOT / "src/files/assets/warrior.ts16"))
        self.assertEqual([sheet.index_at(x, y) == 0 for y in range(sheet.height)
                          for x in range(sheet.width)], [p == pixels[0] for p in pixels])

    def test_odd_pixel_counts_and_binary_alpha(self):
        converter = load("test_ts16_encoder_odd", "tools/convert_ts16.py")
        source = Image.new("RGBA", (3, 1))
        source.putdata([(255, 0, 0, 255), (0, 255, 0, 0), (0, 0, 255, 255)])
        payload = converter.encode(source)
        self.assertEqual(len(payload), 42)
        self.assertEqual(payload[-1] & 15, 0)
        self.assertEqual(payload[-2] & 15, 0)
        source.putpixel((1, 0), (0, 255, 0, 128))
        with self.assertRaisesRegex(ValueError, "partial|opaque or transparent"):
            converter.encode(source)

    def test_streaming_qoi_matches_independent_pillow_decoder(self):
        path = ROOT / "src/files/assets/test.qoi"
        with Image.open(path) as source:
            pixels = list(source.convert("RGBA").getdata())
        expected = rgb565([tuple((c * a + 127) // 255 for c in (r, g, b))
                           for r, g, b, a in pixels])
        decoded = b"".join(bytes(data) for _, data in qoi.QOIImage.open(str(path)).iter_rgb565(
            rows=7, background=(0, 0, 0)))
        self.assertEqual(decoded, expected)
        # Include nontrivial alpha and many colors using an independent encoder.
        source = Image.new("RGBA", (41, 7))
        colors = [(i % 256, i * 7 % 256, i * 11 % 256, i * 13 % 256)
                  for i in range(41 * 7)]
        source.putdata(colors)
        stream = io.BytesIO()
        source.save(stream, format="QOI")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.qoi"
            path.write_bytes(stream.getvalue())
            actual = b"".join(bytes(data) for _, data in qoi.QOIImage.open(str(path)).iter_rgb565(
                rows=3, background=(0, 0, 0)))
        self.assertEqual(actual, rgb565([tuple((c * a + 127) // 255 for c in (r, g, b))
                                       for r, g, b, a in colors]))


if __name__ == "__main__":
    unittest.main()
