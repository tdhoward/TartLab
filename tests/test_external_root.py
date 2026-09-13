"""Failure-path contracts for the experimental removable root bootstrap."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ExternalRootTests(unittest.TestCase):
    def setUp(self):
        self.internal = object()
        self.card = object()
        self.mounts = {"/": self.internal}
        self.operations = []
        self.fail_card_root = False

        def mount(fs=None, path=None):
            if fs is None:
                return [(fs, name) for name, fs in self.mounts.items()]
            if path in self.mounts or (path == "/" and fs is self.card and self.fail_card_root):
                raise OSError("mount failed")
            self.operations.append(("mount", path))
            self.mounts[path] = fs

        def umount(path):
            self.operations.append(("umount", path))
            del self.mounts[path]

        self.fake_os = types.SimpleNamespace(stat=lambda path: (0x8000,), chdir=lambda path: None)
        fake_vfs = types.SimpleNamespace(mount=mount, umount=umount, VfsFat=lambda device: self.card)
        spec = importlib.util.spec_from_file_location("external_root_test", ROOT / "firmware/lvgl-modern/drivers/external_root.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"vfs": fake_vfs, "os": self.fake_os}):
            spec.loader.exec_module(self.module)

    def test_preserves_original_filesystem_at_flash(self):
        result = self.module.activate(object(), required=("main.py",))
        self.assertIs(result, self.card)
        self.assertEqual(self.mounts, {"/flash": self.internal, "/": self.card})

    def test_missing_entrypoint_leaves_internal_root_in_place(self):
        self.fake_os.stat = lambda path: (_ for _ in ()).throw(OSError("missing"))
        with self.assertRaises(OSError):
            self.module.activate(object(), required=("main.py",))
        self.assertEqual(self.mounts, {"/": self.internal})
        self.assertNotIn(("umount", "/"), self.operations)

    def test_directory_cannot_substitute_for_entrypoint(self):
        self.fake_os.stat = lambda path: (0x4000,)
        with self.assertRaisesRegex(ValueError, "not regular"):
            self.module.activate(object(), required=("main.py",))
        self.assertEqual(self.mounts, {"/": self.internal})

    def test_failed_root_mount_restores_original_mount(self):
        self.fail_card_root = True
        with self.assertRaises(OSError):
            self.module.activate(object(), required=("main.py",))
        self.assertEqual(self.mounts, {"/": self.internal})

    def test_existing_external_mount_is_never_unmounted(self):
        self.mounts["/sd"] = self.card
        with self.assertRaises(ValueError):
            self.module.activate(object())
        self.assertEqual(self.operations, [])

    def test_missing_card_releases_native_device(self):
        class Card:
            closed = False

            def ioctl(self, operation, argument):
                return -1

            def deinit(self):
                self.closed = True

        card = Card()
        buses = []

        def create_bus(**kwargs):
            bus = object()
            buses.append(bus)
            return bus

        machine = types.SimpleNamespace(
            SPI=types.SimpleNamespace(Bus=create_bus),
            SDCard=lambda **kwargs: card,
        )
        board = {"pins": [{"type": "SD_" + name, "number": index}
                          for index, name in enumerate(("SCK", "MOSI", "MISO", "CS"))],
                 "storage": {"host": 1, "frequency": 1000000}}
        with patch.dict(sys.modules, {"machine": machine}):
            for attempt in range(2):
                with self.assertRaisesRegex(OSError, "absent or unreadable"):
                    self.module.open_sd(board)
        self.assertTrue(card.closed)
        self.assertEqual(len(buses), 1)

    def test_owned_card_retains_bus_and_propagates_io_failure(self):
        bus = object()
        card = types.SimpleNamespace(readblocks=lambda block, buffer: False,
                                     writeblocks=lambda block, buffer: False,
                                     ioctl=lambda operation, argument: -1)
        owned = self.module._OwnedCard(bus, card)
        self.assertIs(owned.bus, bus)
        self.assertIs(owned.readblocks(0, bytearray(512)), False)
        self.assertIs(owned.writeblocks(0, bytearray(512)), False)
        self.assertEqual(owned.ioctl(1, 0), -1)


if __name__ == "__main__":
    unittest.main()
