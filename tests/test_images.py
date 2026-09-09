"""Image format and example checks without a board or display server."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tests.image_support import IMAGE_MODULES, qoi, sprites


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


END = b"\x00" * 7 + b"\x01"


def encoded(width, height, chunks, channels=4, colorspace=0):
    return b"qoif" + struct.pack(">IIBB", width, height, channels, colorspace) + chunks + END


def rgb565(colors):
    return b"".join(struct.pack(">H", ((r & 248) << 8) |
                               ((g & 252) << 3) | (b >> 3)) for r, g, b in colors)


class QOIImageTests(unittest.TestCase):
    def image(self, payload):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "image.qoi"
        path.write_bytes(payload)
        return qoi.QOIImage.open(str(path))

    def test_all_opcodes_across_strip_boundaries_and_alpha_compositing(self):
        first_index = (10 * 3 + 20 * 5 + 30 * 7 + 255 * 11) & 63
        chunks = bytes((254, 10, 20, 30, 0x7A, 0xA5, 0x97,
                        first_index, 0xC2, 255, 80, 160, 240, 128))
        image = self.image(encoded(4, 2, chunks))
        strips = [(y, bytes(pixels)) for y, pixels in image.iter_rgb565(
            rows=1, background=(20, 40, 60))]
        colors = [(10, 20, 30), (11, 20, 30), (17, 25, 34)]
        colors += [(10, 20, 30)] * 4 + [(50, 100, 150)]
        self.assertEqual([y for y, _ in strips], [0, 1])
        self.assertEqual(b"".join(pixels for _, pixels in strips), rgb565(colors))

    def test_runs_cross_strips_and_cache_initial_black(self):
        black_index = (255 * 11) & 63
        image = self.image(encoded(2, 3, bytes((0xC3, 254, 255, 0, 0, black_index))))
        strips = [(y, bytes(pixels)) for y, pixels in image.iter_rgb565(rows=2)]
        self.assertEqual([y for y, _ in strips], [0, 2])
        self.assertEqual([len(p) for _, p in strips], [8, 4])
        self.assertEqual(b"".join(p for _, p in strips),
                         rgb565([(0, 0, 0)] * 4 + [(255, 0, 0), (0, 0, 0)]))

    def test_delta_arithmetic_wraps_and_rgb_header_does_not_disable_alpha(self):
        image = self.image(encoded(1, 1, b"\x40", channels=3))
        self.assertEqual(bytes(next(image.iter_rgb565())[1]), rgb565([(254, 254, 254)]))
        image = self.image(encoded(1, 1, bytes((255, 255, 0, 0, 0)), channels=3))
        with self.assertRaisesRegex(ValueError, "explicit background"):
            list(image.iter_rgb565())
        self.assertEqual(bytes(next(image.iter_rgb565(background=(0, 0, 255)))[1]),
                         rgb565([(0, 0, 255)]))

    def test_strips_reuse_storage_and_closing_iterator_closes_input(self):
        payload = encoded(2, 2, bytes((254, 255, 0, 0, 0xC0,
                                     254, 0, 255, 0, 0xC0)))
        image = self.image(payload)
        stream = io.BytesIO(payload)
        with patch.object(qoi, "open", return_value=stream, create=True):
            iterator = image.iter_rgb565(rows=1)
            first = next(iterator)[1]
            saved = bytes(first)
            second = next(iterator)[1]
            self.assertNotEqual(saved, bytes(first))
            self.assertIs(first.obj, second.obj)
            iterator.close()
        self.assertTrue(stream.closed)

    def test_reads_are_bounded_independently_of_compressed_file_size(self):
        payload = encoded(1, 1024, bytes((254, 255, 0, 0)) * 1024)
        image = self.image(payload)

        class BoundedStream(io.BytesIO):
            def read(self, size=-1):
                if not 0 <= size <= 512:
                    raise AssertionError("unbounded image read")
                return super().read(size)

        with patch.object(qoi, "open", return_value=BoundedStream(payload), create=True):
            self.assertEqual(sum(len(p) for _, p in image.iter_rgb565(rows=3)), 2048)

    def test_rejects_malformed_headers_runs_chunks_and_end_markers(self):
        for payload in (b"", encoded(0, 1, b""), encoded(1, 1, b"", channels=2),
                        encoded(1, 1, b"", colorspace=2)):
            with self.subTest(header=payload):
                with self.assertRaises(ValueError):
                    self.image(payload)
        for payload in (encoded(1, 1, b"\xC1"),
                        encoded(1, 1, b"\xFE")[:-8],
                        encoded(1, 1, b"\xC0")[:-1],
                        encoded(1, 1, b"\xC0")[:-1] + b"\x02"):
            with self.subTest(stream=payload):
                with self.assertRaises(ValueError):
                    list(self.image(payload).iter_rgb565())

    def test_strip_options_are_validated(self):
        image = self.image(encoded(1, 1, b"\xC0"))
        for rows in (0, -1, 1.5):
            with self.assertRaises(ValueError):
                list(image.iter_rgb565(rows=rows))
        for background in ((0, 0), (0, 0, 256), (0, -1, 0)):
            with self.assertRaises(ValueError):
                list(image.iter_rgb565(background=background))

    def test_shipped_qoi_decodes_identically_with_different_strip_sizes(self):
        image = qoi.QOIImage.open(str(ROOT / "src/files/assets/test.qoi"))
        results = []
        for rows in (1, 8, image.height):
            digest = hashlib.sha256()
            count = 0
            for _, pixels in image.iter_rgb565(rows, background=(0, 0, 0)):
                digest.update(pixels)
                count += len(pixels)
            self.assertEqual(count, image.width * image.height * 2)
            results.append(digest.hexdigest())
        self.assertEqual(len(set(results)), 1)


class ImageAssetsTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict("sys.modules", IMAGE_MODULES))

    def test_legacy_assets_contain_only_the_preserved_bitmap(self):
        paths = list((ROOT / "src/files/assets-legacy").iterdir())
        self.assertEqual([p.name for p in paths], ["warrior.bmp"])
        self.assertEqual(paths[0].stat().st_size, 73866)
        self.assertFalse((ROOT / "src/files/assets/warrior.bmp").exists())

    def test_warrior_sheet_has_twelve_frames_and_transparent_background(self):
        sheet = sprites.SpriteSheet(str(ROOT / "src/files/assets/warrior.ts16"))
        self.assertEqual((sheet.width, sheet.height), (144, 256))
        self.assertEqual(sheet.index_at(0, 0), 0)
        for row in range(4):
            for column in range(3):
                sprite = sheet.sprite(column * 48, row * 64, 48, 64)
                self.assertGreater(len(sprite.spans), 0)

    def test_help_assets_exist_for_both_profiles(self):
        import re
        for suffix in ("", "-legacy"):
            help_root = ROOT / ("src/files/help" + suffix)
            assets = ROOT / ("src/files/assets" + suffix)
            manifest = json.loads((help_root / "manifest.json").read_text())
            for folder in manifest["folders"]:
                for entry in folder["entries"]:
                    self.assertTrue((help_root / entry["file"]).is_file())
            for path in help_root.glob("*.py"):
                for asset in re.findall(r'files/assets/([\w.-]+)', path.read_text()):
                    self.assertTrue((assets / asset).is_file(), str(path) + ": " + asset)


if __name__ == "__main__":
    unittest.main()
