"""Protocol, delivery, persistence and layout checks for the chat example."""

import hashlib
import hmac
import json
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


APP = Path(__file__).resolve().parents[1] / "src/files/help/messaging.py"
app = runpy.run_path(str(APP), init_globals={"_MESSAGING_AUTOSTART": False})
Chat = app["Chat"]
MAC_A, MAC_B, MAC_C = b"aaaaaa", b"bbbbbb", b"cccccc"


def client(mac, nickname="Guest", store=None):
    return Chat(mac, {"version": 1, "nickname": nickname, "groups": []}, store)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = client(MAC_A, "Alice"), client(MAC_B, "Bob")
        self.ga = self.a.join("TartLab", "hello")
        self.gb = self.b.join("TartLab", "hello")

    def packet(self, text="Hi Bob"):
        self.a.send(self.ga, text, 0)
        return self.a.pending[-1]["packet"]

    def test_signature_matches_standard_hmac(self):
        key = bytes(range(32))
        for message in (b"", b"Hello", bytes(range(250))):
            self.assertEqual(app["signature"](key, message),
                             hmac.new(key, message, hashlib.sha256).digest()[:16])

    def test_two_way_delivery_acknowledges_only_after_app_receives(self):
        packet = self.packet()
        sent = []
        self.a.tick(0, lambda a, b: a - b, sent.append)
        self.assertEqual(sent, [packet])
        self.assertEqual(self.ga["history"][0]["status"], "Sending")
        ack = self.b.receive(MAC_A, packet)
        self.assertEqual(self.gb["history"][0]["text"], "Hi Bob")
        self.assertEqual(self.gb["history"][0]["nickname"], "Alice")
        self.assertEqual(self.gb["unread"], 1)
        self.a.receive(MAC_B, ack)
        self.assertEqual(self.a.pending, [])
        self.assertEqual(self.ga["history"][0]["status"], "Peer received")
        self.b.send(self.gb, "Hello Alice", 0)
        self.a.receive(MAC_B, self.b.pending[0]["packet"])
        self.assertEqual(self.ga["history"][-1]["text"], "Hello Alice")

    def test_wrong_password_other_groups_tampering_and_spoofed_source_drop(self):
        wrong = client(MAC_C)
        bad = wrong.join("TartLab", "wrong")
        other = wrong.join("Another group", "hello")
        packet = self.packet()
        self.assertIsNone(wrong.receive(MAC_A, packet))
        self.assertFalse(bad["history"] or other["history"])
        self.assertIsNone(self.b.receive(MAC_C, packet))
        for offset in range(len(packet)):
            changed = bytearray(packet)
            changed[offset] ^= 1
            self.assertIsNone(self.b.receive(MAC_A, bytes(changed)))
        self.assertFalse(self.gb["history"])

    def test_malformed_and_truncated_packets_are_ignored(self):
        packet = self.packet()
        for end in range(len(packet)):
            self.assertIsNone(self.b.receive(MAC_A, packet[:end]))
        for payload in (b"", b"\x00bad", b"\x11name", b"\x01a", b"\x01\xfftext"):
            content = packet[:26] + payload
            signed = content + app["signature"](self.ga["key_bytes"], content)
            self.assertIsNone(self.b.receive(MAC_A, signed))
        for value in (b"x" * 251, b"TC1" + b"x" * 100):
            self.assertIsNone(self.b.receive(MAC_A, value))

    def test_duplicate_is_shown_once_but_acknowledged_again(self):
        packet = self.packet()
        first = self.b.receive(MAC_A, packet)
        self.assertEqual(self.b.receive(MAC_A, packet), first)
        self.assertEqual(len(self.gb["history"]), 1)
        self.assertEqual(self.gb["unread"], 1)
        self.assertIsNone(self.a.receive(MAC_A, packet))

    def test_all_joined_groups_receive_while_one_is_visible(self):
        ga2 = self.a.join("Second", "two")
        gb2 = self.b.join("Second", "two")
        self.b.visible = self.gb["id"]
        self.b.receive(MAC_A, self.packet())
        self.a.send(ga2, "Background", 0)
        self.b.receive(MAC_A, self.a.pending[-1]["packet"])
        self.assertEqual(self.gb["unread"], 0)
        self.assertEqual(gb2["unread"], 1)
        self.assertEqual(gb2["history"][0]["text"], "Background")

    def test_utf8_limits_are_bytes_and_fit_v1_packet(self):
        self.a.rename("N" * 16)
        packet = self.packet("\u00e9" * 80)
        self.assertLessEqual(len(packet), 250)
        self.assertIsNotNone(self.b.receive(MAC_A, packet))
        self.assertEqual(self.gb["history"][-1]["text"], "\u00e9" * 80)
        for text in ("\u00e9" * 81, " ", "bad\nline", "bad\x00text"):
            with self.assertRaises(ValueError):
                self.a.send(self.ga, text, 0)

    def test_history_and_dedup_cache_are_bounded(self):
        for number in range(90):
            packet = app["encode_packet"](self.ga, b"M", number.to_bytes(8, "big"),
                                           MAC_A, "Alice", str(number))
            self.b.receive(MAC_A, packet)
        self.assertEqual(len(self.gb["history"]), 20)
        self.assertEqual(self.gb["history"][0]["text"], "70")
        self.assertEqual(len(self.b.seen), 64)

    def test_retries_are_bounded_and_no_reply_is_not_delivery(self):
        packet = self.packet()
        sent = []
        for now in (0, 799, 800, 1000, 1600, 2399):
            self.a.tick(now, lambda a, b: a - b, sent.append)
        self.assertEqual(sent, [packet] * 3)
        self.a.tick(2400, lambda a, b: a - b, sent.append)
        self.assertFalse(self.a.pending)
        self.assertEqual(self.ga["history"][-1]["status"], "No reply")

    def test_radio_errors_retry_and_clock_wrap_is_supported(self):
        self.a.send(self.ga, "Wrap", 4090)
        transmit = Mock(side_effect=OSError("radio busy"))
        diff = lambda a, b: ((a - b + 2048) % 4096) - 2048
        for now in (4090, 794, 1594, 2394):
            self.a.tick(now, diff, transmit)
        self.assertEqual(transmit.call_count, 3)
        self.assertEqual(self.ga["history"][-1]["status"], "No reply")

    def test_ack_for_other_group_or_wrong_key_does_not_confirm(self):
        packet = self.packet()
        group = self.b.join("Elsewhere", "hello")
        self.a.join("Elsewhere", "hello")
        ack = app["encode_packet"](group, b"A", packet[12:20], MAC_B)
        self.a.receive(MAC_B, ack)
        self.assertEqual(len(self.a.pending), 1)
        wrong = client(MAC_C)
        group = wrong.join("TartLab", "wrong")
        self.a.receive(MAC_C, app["encode_packet"](group, b"A", packet[12:20], MAC_C))
        self.assertEqual(len(self.a.pending), 1)

    def test_pending_limit_and_leaving_cancel_outgoing_messages(self):
        for index in range(4):
            self.packet(str(index))
        with self.assertRaises(ValueError):
            self.packet("fifth")
        self.a.leave(self.ga)
        self.assertFalse(self.a.pending or self.a.groups)
        with self.assertRaises(ValueError):
            self.a.send(self.ga, "left", 0)


class SettingsTests(unittest.TestCase):
    def test_roundtrip_preserves_membership_not_history_or_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.json"
            store = app["SettingsStore"](str(path))
            chat = Chat(MAC_A, store.load("Guest"), store)
            group = chat.join("Group one", "distinctive-secret")
            chat.rename("Alice")
            chat.send(group, "temporary history", 0)
            reloaded = Chat(MAC_A, store.load("Other"))
            self.assertEqual(reloaded.nickname, "Alice")
            self.assertEqual(reloaded.groups[0]["key"], group["key"])
            self.assertFalse(reloaded.groups[0]["history"])
            self.assertNotIn("distinctive-secret", path.read_text())
            self.assertNotIn("temporary history", path.read_text())
            chat.leave(group)
            self.assertFalse(store.load("Guest")["groups"])

    def test_failed_save_does_not_change_membership_or_name(self):
        store = Mock()
        chat = client(MAC_A, store=store)
        store.save.side_effect = OSError("full")
        with self.assertRaises(OSError):
            chat.join("Group", "secret")
        self.assertFalse(chat.groups)
        with self.assertRaises(OSError):
            chat.rename("Changed")
        self.assertEqual(chat.nickname, "Guest")

    def test_interrupted_replace_leaves_previous_settings_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = app["SettingsStore"](str(Path(directory) / "chat.json"))
            old = {"version": 1, "nickname": "Old", "groups": []}
            store.save(old)
            with patch("os.replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    store.save(dict(old, nickname="New"))
            self.assertEqual(store.load("Default"), old)

    def test_corrupt_settings_are_reported_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.json"
            path.write_text('{"version": 99}')
            with self.assertRaises(ValueError):
                app["SettingsStore"](str(path)).load("Guest")
            self.assertEqual(json.loads(path.read_text()), {"version": 99})

    def test_group_limit_duplicate_join_and_password_change(self):
        chat = client(MAC_A)
        group = chat.join(" Same ", "password")
        self.assertIs(chat.join("Same", "password"), group)
        with self.assertRaises(ValueError):
            chat.join("Same", "different")
        for index in range(7):
            chat.join(str(index), "password")
        with self.assertRaises(ValueError):
            chat.join("ninth", "password")


class LayoutTests(unittest.TestCase):
    def test_editors_fit_and_do_not_stretch_on_tall_screens(self):
        for width, height in ((480, 222), (320, 480), (320, 240), (240, 320)):
            layout = app["editor_layout"](width, height)
            x, y, w, h = layout["keyboard"]
            self.assertEqual(x, 0)
            self.assertEqual(w, width)
            self.assertLessEqual(h, 160)
            self.assertEqual(y + h, height)
            dx, dy, dw, dh = layout["draft"]
            self.assertGreaterEqual(dy, 28)
            self.assertLessEqual(dy + dh, y)
            self.assertLessEqual(dx + dw, width)


class RadioTests(unittest.TestCase):
    def radio_fixture(self, fail=False, active=False):
        class WLAN:
            PM_NONE = 0

            def __init__(self, connected=False):
                self.enabled = True
                self.connected = connected
                self.values = {"pm": 2, "channel": 11, "mac": MAC_A}

            def active(self, value=None):
                if value is not None:
                    self.enabled = value
                return self.enabled

            def isconnected(self):
                return self.connected

            def disconnect(self):
                self.connected = False

            def connect(self):
                self.connected = True

            def config(self, name=None, **values):
                self.values.update(values)
                if name is not None:
                    return self.values[name]

        station, ap = WLAN(True), WLAN()
        esp = Mock()
        esp.active.return_value = active
        if fail:
            esp.add_peer.side_effect = OSError("out of memory")
        platform = SimpleNamespace(station_interface=lambda: station,
                                   access_point_interface=lambda: ap)
        return station, ap, esp, platform

    def test_radio_acquires_channel_and_restores_previous_wifi(self):
        station, ap, esp, platform = self.radio_fixture()
        with patch.dict("sys.modules", {"espnow": SimpleNamespace(ESPNow=lambda: esp)}):
            radio = app["Radio"](platform)
        self.assertFalse(ap.enabled or station.connected)
        self.assertEqual(station.values["channel"], 6)
        self.assertEqual(station.values["pm"], 0)
        radio.send(b"frame")
        esp.send.assert_called_once_with(b"\xff" * 6, b"frame", False)
        radio.close()
        self.assertTrue(ap.enabled and station.enabled and station.connected)
        self.assertEqual(station.values["channel"], 11)
        self.assertEqual(station.values["pm"], 2)
        calls = esp.active.call_count
        radio.close()
        self.assertEqual(esp.active.call_count, calls)

    def test_failed_initialization_restores_interfaces(self):
        station, ap, esp, platform = self.radio_fixture(fail=True)
        with patch.dict("sys.modules", {"espnow": SimpleNamespace(ESPNow=lambda: esp)}):
            with self.assertRaises(OSError):
                app["Radio"](platform)
        self.assertTrue(ap.enabled and station.connected)
        self.assertEqual(station.values["channel"], 11)

    def test_existing_espnow_owner_is_not_disrupted(self):
        station, ap, esp, platform = self.radio_fixture(active=True)
        with patch.dict("sys.modules", {"espnow": SimpleNamespace(ESPNow=lambda: esp)}):
            with self.assertRaises(RuntimeError):
                app["Radio"](platform)
        self.assertTrue(ap.enabled and station.connected)
        self.assertEqual(station.values["channel"], 11)
        esp.active.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
