"""Display-independent recovery console for the legacy MicroPython profile."""

import os
import socket
import time

import machine
import network

try:
    import ujson as json
except ImportError:
    import json


STATE_DIR = "/state"
BOOT_STATE = STATE_DIR + "/boot.json"
UPDATE_STATE = STATE_DIR + "/update.json"
SETTINGS_FILE = STATE_DIR + "/settings.json"
RECOVERY_FLAG = STATE_DIR + "/recovery.flag"
LEGACY_STAGING_MANIFEST = "/tmp/manifest.json"


def _read(path, default):
    try:
        with open(path, "r") as stream:
            return json.load(stream)
    except Exception:
        return default


def _write(path, value):
    temporary = path + ".tmp"
    with open(temporary, "w") as stream:
        json.dump(value, stream)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(temporary, path)


def _redacted_status(reason):
    boot = _read(BOOT_STATE, {})
    update = _read(UPDATE_STATE, {})
    return {
        "mode": "recovery",
        "reason": reason,
        "boot_sequence": boot.get("sequence"),
        "boot_failures": boot.get("consecutive_failures"),
        "update_status": update.get("status", "none"),
        "pending_versions": [item.get("pending_version") for item in update.get("repos", [])],
    }


def _response(client, status, content_type, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    header = "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % (
        status, content_type, len(body))
    client.send(header.encode("utf-8"))
    client.send(body)


def _retry():
    update = _read(UPDATE_STATE, None)
    if isinstance(update, dict):
        if update.get("status") in ("failed", "installing"):
            # Permit one diagnostic boot without allowing a failed install to commit.
            update["status"] = "diagnostic_boot"
        _write(UPDATE_STATE, update)
    boot = _read(BOOT_STATE, {})
    boot["consecutive_failures"] = 0
    boot["health"] = "retrying"
    _write(BOOT_STATE, boot)
    try:
        os.remove(RECOVERY_FLAG)
    except OSError:
        pass
    # A legacy update can lose power after downloading its manifest but before
    # writing the durable update marker.  The early boot gate treats that
    # manifest as an interrupted update, so explicitly abandon that staging
    # trigger when the user chooses to retry the normal boot.
    try:
        os.remove(LEGACY_STAGING_MANIFEST)
    except OSError:
        pass


def _force_ide():
    settings = _read(SETTINGS_FILE, {})
    settings["STARTUP_MODE"] = "IDE"
    _write(SETTINGS_FILE, settings)
    _retry()


def _page(reason):
    status = _redacted_status(reason)
    return """<!doctype html><html><head><meta name=viewport content='width=device-width'>
<title>TartLab Recovery</title></head><body><h1>TartLab Recovery</h1>
<p>Reason: %s</p><p>Boot failures: %s</p><p>Update state: %s</p>
<form method=post action=/retry><button>Retry normal boot</button></form>
<form method=post action=/ide><button>Force IDE on next boot</button></form>
<form method=post action=/update><button>Install latest corrective release</button></form>
<p><a href=/status>Redacted diagnostic status</a></p></body></html>""" % (
        status["reason"], status["boot_failures"], status["update_status"])


def _connect_to_wifi():
    settings = _read(SETTINGS_FILE, None)
    if not isinstance(settings, dict):
        settings = _read("/settings.json", {})
    station = network.WLAN(network.STA_IF)
    station.active(True)
    if station.isconnected():
        return station
    names = settings.get("wifi_ssids", [])
    passwords = settings.get("wifi_passwords", [])
    for index, name in enumerate(names):
        password = passwords[index] if index < len(passwords) else ""
        station.connect(name, password)
        for unused in range(40):
            if station.isconnected():
                return station
            time.sleep(0.25)
        station.disconnect()
    raise OSError("No configured Wi-Fi network was reachable")


def _install_update():
    _connect_to_wifi()
    from recovery_update import update_to_latest
    version = update_to_latest(lambda message: print("Recovery update:", message))
    _retry()
    print("Recovery installed %s; boot health is pending" % version)


def run(reason="requested"):
    print("TartLab recovery mode:", reason)
    access_point = network.WLAN(network.AP_IF)
    access_point.active(True)
    access_point.config(essid="TartLab-Recovery")
    try:
        access_point.config(authmode=network.AUTH_OPEN)
    except Exception:
        pass
    address = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(address)
    server.listen(2)
    print("Recovery Wi-Fi: TartLab-Recovery; open http://192.168.4.1/")
    while True:
        client = None
        try:
            client, unused = server.accept()
            request = client.recv(1024).decode("utf-8")
            first_line = request.split("\r\n", 1)[0]
            method, path, unused_version = first_line.split(" ", 2)
            if method == "GET" and path == "/":
                _response(client, "200 OK", "text/html", _page(reason))
            elif method == "GET" and path == "/status":
                _response(client, "200 OK", "application/json", json.dumps(_redacted_status(reason)))
            elif method == "POST" and path in ("/retry", "/ide"):
                if path == "/ide":
                    _force_ide()
                else:
                    _retry()
                _response(client, "200 OK", "text/plain", "Restarting")
                time.sleep(0.2)
                machine.reset()
            elif method == "POST" and path == "/update":
                _response(client, "200 OK", "text/plain", "Installing update; watch the serial log")
                client.close()
                client = None
                _install_update()
                time.sleep(0.2)
                machine.reset()
            else:
                _response(client, "404 Not Found", "text/plain", "Not found")
        except Exception as error:
            print("Recovery request failed:", error)
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
