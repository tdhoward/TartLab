import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from panel_scroll_diagnostics import (  # noqa: E402
    MARKER,
    device_program,
    extract_result,
)


class PanelScrollDiagnosticsTests(unittest.TestCase):
    def test_program_injects_sources_without_device_or_firmware_writes(self):
        source = device_program()
        compile(source, "<panel-scroll-diagnostics>", "exec")
        self.assertIn("ST7796DirectRGB565Surface", source)
        self.assertIn("copy_rgb565_rows", source)
        self.assertNotIn("__EMITTER_SOURCE__", source)
        self.assertNotIn("machine.reset", source)
        self.assertNotIn("open(", source)

    def test_extract_result(self):
        expected = {
            "accelerated_bytes": 14208,
            "software_bytes": 213120,
            "buffer_checksums_match": True,
        }
        output = ("noise\r\n" + MARKER + json.dumps(expected) + "\r\n").encode()
        self.assertEqual(extract_result(output), expected)


if __name__ == "__main__":
    unittest.main()
