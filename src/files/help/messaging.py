"""Nearby Chat: ESP-NOW group messaging for modern touch displays.

Copy this example to user files and run it on each device. Add the same group
name and password on each device. No router is needed; chat uses radio channel
6 while open. Reset/Exit returns to the launcher and its normal Wi-Fi setup.

Passwords authenticate messages; message contents are NOT encrypted. This is
a small, local, just-for-fun example, not secure messaging. Memberships and
nicknames survive reset; the last 20 messages per group live only in RAM.
"""

import binascii
import hashlib
import json
import os
import time


CHANNEL = 6
STATE_PATH = "/state/espnow_chat.json"
MAX_GROUPS = 8
MAX_HISTORY = 20
MAX_TEXT = 160  # UTF-8 bytes, leaving room for packet metadata and signature.
MAGIC = b"TC1"
BROADCAST = b"\xff" * 6


def text_value(value, limit, label, strip=True):
    if not isinstance(value, str):
        raise ValueError("Invalid " + label)
    value = value.strip() if strip else value
    if not value.strip() or len(value.encode()) > limit:
        raise ValueError("%s: use 1-%d bytes" % (label, limit))
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(label + ": no control characters")
    return value


def group_id(name):
    return hashlib.sha256(b"Nearby Chat group\x00" + name.encode()).digest()[:8]


def make_group(name, password):
    name = text_value(name, 32, "Group")
    password = text_value(password, 64, "Password", strip=False)
    # Lightweight derivation for this demo, deliberately not a password vault.
    key = hashlib.sha256(b"Nearby Chat key\x00" + name.encode() +
                         b"\x00" + password.encode()).digest()
    return {"name": name, "key": binascii.hexlify(key).decode()}


def signature(key, message):
    """HMAC-SHA256, truncated to 128 bits; key is a 32-byte group key."""
    key = key + b"\x00" * (64 - len(key))
    inner = hashlib.sha256(bytes(byte ^ 0x36 for byte in key) + message).digest()
    return hashlib.sha256(bytes(byte ^ 0x5C for byte in key) + inner).digest()[:16]


def equal_tag(left, right):
    difference = len(left) ^ len(right)
    for a, b in zip(left, right):
        difference |= a ^ b
    return difference == 0


def encode_packet(group, kind, message_id, sender, nickname="", text=""):
    if kind not in (b"M", b"A") or len(message_id) != 8 or len(sender) != 6:
        raise ValueError("Invalid packet header")
    payload = b""
    if kind == b"M":
        nick = text_value(nickname, 16, "Name").encode()
        body = text_value(text, MAX_TEXT, "Message").encode()
        payload = bytes((len(nick),)) + nick + body
    packet = MAGIC + kind + group["id"] + message_id + sender + payload
    packet += signature(group["key_bytes"], packet)
    if len(packet) > 250:
        raise ValueError("Message too long")
    return packet


def decode_packet(groups, sender, packet):
    """Drop malformed, foreign, unauthenticated, or incorrectly sourced data."""
    if not 42 <= len(packet) <= 250 or packet[:3] != MAGIC:
        return None
    kind, gid, message_id = packet[3:4], packet[4:12], packet[12:20]
    group = next((g for g in groups if g["id"] == gid), None)
    if group is None or packet[20:26] != sender or kind not in (b"M", b"A"):
        return None
    if not equal_tag(signature(group["key_bytes"], packet[:-16]), packet[-16:]):
        return None
    payload = packet[26:-16]
    nickname, text = "", ""
    try:
        if kind == b"A":
            if payload:
                return None
        else:
            if not payload or not 1 <= payload[0] <= 16:
                return None
            nickname = text_value(payload[1:1 + payload[0]].decode(), 16, "Name")
            text = text_value(payload[1 + payload[0]:].decode(), MAX_TEXT, "Message")
    except (ValueError, UnicodeError):
        return None
    return group, kind, message_id, nickname, text


def validate_settings(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Invalid chat settings")
    nickname = text_value(value.get("nickname"), 16, "Name")
    groups = value.get("groups")
    if not isinstance(groups, list) or len(groups) > MAX_GROUPS:
        raise ValueError("Invalid saved groups")
    result, names = [], set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Invalid saved group")
        name = text_value(group.get("name"), 32, "Group")
        key = group.get("key")
        if name in names or not isinstance(key, str) or len(key) != 64 or any(
                char not in "0123456789abcdef" for char in key):
            raise ValueError("Invalid saved group key")
        names.add(name)
        result.append({"name": name, "key": key})
    return {"version": 1, "nickname": nickname, "groups": result}


class SettingsStore:
    def __init__(self, path=STATE_PATH):
        self.path = path

    def load(self, default_name):
        try:
            with open(self.path) as stream:
                value = json.load(stream)
        except OSError as error:
            if error.args[0] != 2:
                raise
            value = {"version": 1, "nickname": default_name, "groups": []}
        return validate_settings(value)

    def save(self, value):
        value = validate_settings(value)
        temporary = self.path + ".tmp"
        with open(temporary, "w") as stream:
            json.dump(value, stream)
            stream.flush()
        sync = getattr(os, "sync", None)
        if sync is not None:
            sync()
        # LittleFS rename atomically replaces the destination; os.replace is
        # the equivalent on the host used by the persistence tests.
        replace = getattr(os, "replace", os.rename)
        replace(temporary, self.path)
        if sync is not None:
            sync()


class Chat:
    """App rules, bounded history, authentication, acknowledgments and retries."""

    def __init__(self, mac, settings, store=None, random_bytes=None):
        self.mac = mac
        self.store = store
        self.random_bytes = random_bytes or os.urandom
        settings = validate_settings(settings)
        self.nickname = settings["nickname"]
        self.groups = [self._group(g) for g in settings["groups"]]
        self.visible = None
        self.pending = []
        self.seen = []
        self.revision = 0

    def _group(self, saved):
        return {"name": saved["name"], "key": saved["key"],
                "id": group_id(saved["name"]),
                "key_bytes": binascii.unhexlify(saved["key"]),
                "history": [], "unread": 0, "draft": ""}

    def _save(self, nickname, groups):
        if self.store is not None:
            self.store.save({"version": 1, "nickname": nickname,
                             "groups": [{"name": g["name"], "key": g["key"]}
                                        for g in groups]})

    def rename(self, nickname):
        nickname = text_value(nickname, 16, "Name")
        self._save(nickname, self.groups)
        self.nickname = nickname
        self.revision += 1

    def join(self, name, password):
        saved = make_group(name, password)
        for group in self.groups:
            if group["name"] == saved["name"]:
                if group["key"] != saved["key"]:
                    raise ValueError("Leave group to change password")
                return group
        if len(self.groups) >= MAX_GROUPS:
            raise ValueError("Maximum 8 groups; leave one first")
        group = self._group(saved)
        self._save(self.nickname, self.groups + [group])
        self.groups.append(group)
        self.revision += 1
        return group

    def leave(self, group):
        remaining = [g for g in self.groups if g is not group]
        self._save(self.nickname, remaining)
        self.groups = remaining
        self.pending = [p for p in self.pending if p["group"] is not group]
        self.seen = [key for key in self.seen if key[0] != group["id"]]
        self.revision += 1

    def _append(self, group, entry):
        group["history"].append(entry)
        if len(group["history"]) > MAX_HISTORY:
            group["history"].pop(0)
        self.revision += 1

    def send(self, group, text, now):
        if len(self.pending) >= 4:
            raise ValueError("Please wait for pending messages")
        if group not in self.groups:
            raise ValueError("Join the group first")
        message_id = self.random_bytes(8)
        text = text_value(text, MAX_TEXT, "Message")
        packet = encode_packet(group, b"M", message_id, self.mac, self.nickname, text)
        entry = {"nickname": self.nickname, "text": text,
                 "own": True, "status": "Sending"}
        self.pending.append({"group": group, "id": message_id, "packet": packet,
                             "entry": entry, "last": now, "attempts": 0})
        self._append(group, entry)
        return message_id

    def receive(self, sender, packet):
        if sender == self.mac:
            return None
        decoded = decode_packet(self.groups, sender, packet)
        if decoded is None:
            return None
        group, kind, message_id, nickname, text = decoded
        if kind == b"A":
            for pending in self.pending[:]:
                if pending["id"] == message_id and pending["group"] is group:
                    pending["entry"]["status"] = "Peer received"
                    self.pending.remove(pending)
                    self.revision += 1
            return None
        key = (group["id"], bytes(sender), message_id)
        if key not in self.seen:
            self.seen.append(key)
            if len(self.seen) > 64:
                self.seen.pop(0)
            self._append(group, {"nickname": nickname, "text": text,
                                 "own": False, "status": ""})
            if self.visible != group["id"]:
                group["unread"] = min(999, group["unread"] + 1)
        # A duplicate still needs an ACK: the previous ACK may have been lost.
        return encode_packet(group, b"A", message_id, self.mac)

    def tick(self, now, ticks_diff, transmit):
        for pending in self.pending[:]:
            if pending["attempts"] and ticks_diff(now, pending["last"]) < 800:
                continue
            if pending["attempts"] >= 3:
                pending["entry"]["status"] = "No reply"
                self.pending.remove(pending)
                self.revision += 1
                continue
            pending["attempts"] += 1
            pending["last"] = now
            try:
                transmit(pending["packet"])
            except OSError:
                pending["entry"]["status"] = "Radio busy; retrying"
                self.revision += 1


class Radio:
    """Own the radio for the duration of this app, using the platform's WLANs."""

    def __init__(self, platform):
        import espnow
        self.station = platform.station_interface()
        self.ap = platform.access_point_interface()
        self.esp = espnow.ESPNow()
        if self.esp.active():
            raise RuntimeError("ESP-NOW is already in use")
        self.was_station = self.station.active()
        self.was_ap = self.ap.active()
        self.was_connected = self.station.isconnected()
        self.old_channel = self.station.config("channel")
        self.old_pm = self.station.config("pm")
        self.closed = False
        try:
            self.ap.active(False)
            self.station.active(False)
            self.station.active(True)
            self.station.disconnect()
            self.station.config(channel=CHANNEL, pm=self.station.PM_NONE)
            self.mac = bytes(self.station.config("mac"))
            self.esp.config(rxbuf=2048)
            self.esp.active(True)
            self.esp.add_peer(BROADCAST)
        except Exception:
            self.close()
            raise

    def send(self, packet):
        self.esp.send(BROADCAST, packet, False)

    def poll(self, chat):
        # Bound work per frame so a burst cannot starve the keyboard.
        for unused in range(6):
            sender, packet = self.esp.irecv(0)
            if sender is None:
                break
            reply = chat.receive(bytes(sender), bytes(packet))
            if reply is not None:
                self.send(reply)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.esp.active(False)
        finally:
            self.station.disconnect()
            if self.old_channel:
                self.station.config(channel=self.old_channel)
            self.station.config(pm=self.old_pm)
            self.station.active(self.was_station)
            self.ap.active(self.was_ap)
            if self.was_connected:
                self.station.connect()


def editor_layout(width, height):
    keyboard_height = min(160, height - 70)
    top = height - keyboard_height
    return {"keyboard": (0, top, width, keyboard_height),
            "draft": (4, top - 42, width - 8, 38)}


class ChatUI:
    def __init__(self, lv, platform, chat):
        self.lv, self.platform, self.chat = lv, platform, chat
        self.width, self.height = platform.width, platform.height
        self.previous = lv.screen_active()
        self.screen = lv.obj()
        self.screen.set_style_pad_all(0, 0)
        self.screen.set_style_border_width(0, 0)
        self.screen.set_style_bg_color(lv.color_hex(0x101820), 0)
        self.screen.set_scroll_dir(lv.DIR.NONE)
        self.action = None
        self.callbacks = []
        self.page = None
        self.group = None
        self.revision = -1
        self.editor = None
        self.exit_requested = False
        self.home()
        lv.screen_load(self.screen)

    def label(self, parent, text, x, y, width, color=0xFFFFFF, wrap=False):
        lv = self.lv
        widget = lv.label(parent)
        widget.set_pos(x, y)
        widget.set_width(width)
        widget.set_style_text_color(lv.color_hex(color), 0)
        widget.set_long_mode(lv.label.LONG_MODE.WRAP if wrap else lv.label.LONG_MODE.DOTS)
        widget.set_text(text)
        return widget

    def bind(self, widget, event, action):
        def callback(unused):
            if self.action is None:
                self.action = action
        self.callbacks.append(callback)
        widget.add_event_cb(callback, event, None)

    def button(self, parent, title, x, y, width, action, height=34):
        lv = self.lv
        widget = lv.button(parent)
        widget.set_pos(x, y)
        widget.set_size(width, height)
        widget.set_style_pad_all(0, 0)
        widget.set_style_shadow_width(0, 0)
        widget.set_style_radius(6, 0)
        label = self.label(widget, title, 4, 0, width - 8)
        label.center()
        self.bind(widget, lv.EVENT.CLICKED, action)
        return label

    def clear(self, page):
        self.page = page
        self.editor = None
        self.chat.visible = None
        self.screen.clean()
        self.callbacks = []

    def panel(self, y, height):
        panel = self.lv.obj(self.screen)
        panel.set_pos(4, y)
        panel.set_size(self.width - 8, height)
        panel.set_style_pad_all(4, 0)
        panel.set_style_border_width(0, 0)
        panel.set_style_bg_color(self.lv.color_hex(0x1C2C38), 0)
        panel.set_scroll_dir(self.lv.DIR.VER)
        return panel

    def home(self):
        self.clear("home")
        self.group = None
        self.label(self.screen, "Chat - " + self.chat.nickname, 6, 6, self.width - 76)
        self.button(self.screen, "Exit", self.width - 64, 2, 60, self.exit, 28)
        self.notice = self.label(self.screen, "Nearby groups | channel %d" % CHANNEL,
                                 6, 32, self.width - 12, 0x90CAF9)
        panel = self.panel(56, self.height - 102)
        self.group_labels = []
        for index, group in enumerate(self.chat.groups):
            label = self.button(panel, "", 0, index * 40, self.width - 28,
                                lambda g=group: self.show_chat(g))
            self.group_labels.append((group, label))
        if not self.chat.groups:
            self.label(panel, "Add a group on each device.\nUse the same name and password.",
                       0, 0, self.width - 28, wrap=True)
        half = (self.width - 12) // 2
        self.button(self.screen, "Add group", 4, self.height - 40, half, self.add_group)
        self.button(self.screen, "My name", half + 8, self.height - 40, half, self.edit_name)
        self.refresh()

    def show_chat(self, group):
        self.clear("chat")
        self.group = group
        self.chat.visible = group["id"]
        group["unread"] = 0
        self.button(self.screen, "Home", 4, 2, 72, self.home, 30)
        self.notice = self.label(self.screen, group["name"], 84, 7, self.width - 156, 0x90CAF9)
        self.button(self.screen, "Leave", self.width - 64, 2, 60, self.confirm_leave, 30)
        self.history_panel = self.panel(38, self.height - 84)
        self.history_label = self.label(self.history_panel, "", 0, 0, self.width - 28, wrap=True)
        self.button(self.screen, "Write message", 4, self.height - 40,
                    self.width - 8, self.compose)
        self.refresh()

    def refresh(self):
        if self.page == "home":
            for group, label in self.group_labels:
                suffix = " (%d new)" % group["unread"] if group["unread"] else ""
                label.set_text(group["name"] + suffix)
        elif self.page == "chat":
            at_bottom = self.history_panel.get_scroll_bottom() <= 8
            lines = []
            for item in self.group["history"]:
                who = "Me [%s]" % item["status"] if item["own"] else item["nickname"]
                lines.append(who + ": " + item["text"])
            self.history_label.set_text("\n\n".join(lines) or "No messages yet. Say hello!")
            self.history_panel.update_layout()
            if at_bottom:
                self.history_panel.scroll_to_y(self.history_panel.get_scroll_y() +
                                               self.history_panel.get_scroll_bottom(), False)
        self.revision = self.chat.revision

    def edit(self, title, value, limit, done, cancel, password=False):
        self.clear("edit")
        lv = self.lv
        self.notice = self.label(self.screen, title, 6, 5, self.width - 84, 0x90CAF9)
        self.button(self.screen, "Cancel", self.width - 78, 1, 74, cancel, 26)
        layout = editor_layout(self.width, self.height)
        self.editor = lv.textarea(self.screen)
        x, y, w, h = layout["draft"]
        self.editor.set_pos(x, y)
        self.editor.set_size(w, h)
        self.editor.set_one_line(True)
        self.editor.set_max_length(limit)
        self.editor.set_style_pad_all(6, 0)
        self.editor.set_password_mode(password)
        self.editor.set_text(value)
        if y >= 88:
            self.label(self.screen, "Use the checkmark to continue.\nCancel keeps your message draft.",
                       8, 42, self.width - 16, 0x90CAF9, wrap=True)
        self.keyboard = lv.keyboard(self.screen)
        x, y, w, h = layout["keyboard"]
        self.keyboard.set_size(w, h)
        self.keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.keyboard.set_textarea(self.editor)
        self.keyboard.set_popovers(not password)
        self.bind(self.keyboard, lv.EVENT.READY, lambda: done(self.editor.get_text()))
        self.bind(self.keyboard, lv.EVENT.CANCEL, cancel)

    def edit_name(self):
        def done(value):
            self.chat.rename(value)
            self.home()
        self.edit("Your name", self.chat.nickname, 16, done, self.home)

    def add_group(self):
        def named(value):
            name = text_value(value, 32, "Group")
            def joined(password):
                group = self.chat.join(name, password)
                self.show_chat(group)
            self.edit("Password for " + name, "", 64, joined, self.add_group, password=True)
        self.edit("Group name (case matters)", "", 32, named, self.home)

    def compose(self):
        group = self.group
        def cancel():
            group["draft"] = self.editor.get_text()
            self.show_chat(group)
        def send(value):
            self.chat.send(group, value, time.ticks_ms())
            group["draft"] = ""
            self.show_chat(group)
        self.edit("Message to " + group["name"], group["draft"], MAX_TEXT, send, cancel)

    def confirm_leave(self):
        group = self.group
        self.clear("leave")
        self.notice = self.label(self.screen, "Leave " + group["name"] + "?", 8, 8,
                                 self.width - 16, wrap=True)
        self.label(self.screen, "This removes this device's membership\nand recent messages.",
                   8, 60, self.width - 16, wrap=True)
        half = (self.width - 12) // 2
        def leave():
            self.chat.leave(group)
            self.home()
        self.button(self.screen, "Cancel", 4, self.height - 40, half,
                    lambda: self.show_chat(group))
        self.button(self.screen, "Leave group", half + 8, self.height - 40, half, leave)

    def exit(self):
        self.exit_requested = True

    def tick(self):
        # Defer screen deletion until the native LVGL event callback returns.
        if self.action is not None:
            action, self.action = self.action, None
            try:
                action()
            except ValueError as error:
                self.notice.set_text(str(error))
            except OSError:
                self.notice.set_text("Could not save; try again")
        if self.chat.revision != self.revision:
            self.refresh()

    def close(self):
        self.lv.screen_load(self.previous)
        self.screen.delete()
        self.callbacks = []


def run():
    import lvgl as lv
    from tartlabutils.platform import get_platform, InputUnavailableError
    platform = get_platform()
    if not platform.capabilities.get("touch"):
        raise InputUnavailableError("Nearby Chat needs a touch display")
    platform.enter_ui_mode()
    radio, ui = None, None
    try:
        radio = Radio(platform)
        store = SettingsStore()
        default_name = "Guest-" + binascii.hexlify(radio.mac[-2:]).decode()
        chat = Chat(radio.mac, store.load(default_name), store)
        ui = ChatUI(lv, platform, chat)
        print("NEARBY_CHAT_READY")
        while not ui.exit_requested:
            try:
                radio.poll(chat)
            except OSError:
                ui.notice.set_text("Radio busy; waiting")
            chat.tick(time.ticks_ms(), time.ticks_diff, radio.send)
            ui.tick()
            time.sleep_ms(40)
    finally:
        if ui is not None:
            ui.close()
        if radio is not None:
            radio.close()
    if ui is not None and ui.exit_requested:
        import machine
        machine.reset()


if globals().get("_MESSAGING_AUTOSTART", True):
    run()
