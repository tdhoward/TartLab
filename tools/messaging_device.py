"""Check or install the Nearby Chat example on connected MicroPython devices.

check --ports PORT_A PORT_B tests in RAM with an isolated temporary settings
file and saves evidence plus a physical observation form. install copies messaging.py
to user files, verifies its hash, then starts the app. Existing different app
content is backed up in the artifact directory before replacement.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

try:
    from phase1_device import RawRepl
except ImportError:
    from tools.phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/files/help/messaging.py"
REMOTE = "/files/user/messaging.py"


def execute(repl, code):
    return repl.exec(code, timeout=30).decode().strip()


def pause_radio():
    time.sleep(0.15)


def check(ports, artifacts):
    if len(ports) != 2 or ports[0] == ports[1]:
        raise ValueError("check needs two different ports")
    source = SOURCE.read_text()
    devices, reports, transcript = [], [], []
    try:
        for port in ports:
            repl = RawRepl(port)
            devices.append(repl)
            repl.enter()
            # Each run has its own namespace; never overwrite launcher globals.
            execute(repl, "chat_check={'__name__':'chat_check', '_MESSAGING_AUTOSTART':False}\n"
                    "exec(%r, chat_check)" % source)
            def setup(code, r=repl):
                return execute(r, "exec(%r, chat_check)" % code)
            setup("import lvgl as lv\nfrom tartlabutils.platform import get_platform\n"
                  "platform=get_platform()\nplatform.enter_ui_mode()\n"
                  "radio=Radio(platform)\n"
                  "chat=Chat(radio.mac, {'version':1,'nickname':'Probe','groups':[]})\n"
                  "main=chat.join('Chat check', 'test-only')\n"
                  "second=chat.join('Other check', 'second')\n"
                  "ui=None\nprobe_path=None")
            report = json.loads(setup(
                "print(json.dumps({'display':[platform.width,platform.height],"
                "'channel':radio.station.config('channel'),"
                "'espnow_max_payload':__import__('espnow').MAX_DATA_LEN}))"))
            report["port"] = port
            reports.append(report)
        a, b = devices

        def on(repl, code):
            output = execute(repl, "exec(%r, chat_check)" % code)
            if output:
                transcript.append(output)
            return output

        on(a, "chat.send(main,'Hello from first device',time.ticks_ms())\n"
           "packet=chat.pending[-1]['packet']\n"
           "chat.tick(time.ticks_ms(),time.ticks_diff,radio.send)")
        pause_radio()
        on(b, "radio.poll(chat)\nassert main['history'][-1]['text']=='Hello from first device'")
        pause_radio()
        on(a, "radio.poll(chat)\nassert main['history'][-1]['status']=='Peer received'")
        on(a, "radio.send(packet)")
        pause_radio()
        on(b, "radio.poll(chat)\nassert len(main['history'])==1")
        on(b, "chat.send(main,'Hello back',time.ticks_ms())\n"
           "chat.tick(time.ticks_ms(),time.ticks_diff,radio.send)")
        pause_radio()
        on(a, "radio.poll(chat)\nassert main['history'][-1]['text']=='Hello back'")
        pause_radio()
        on(b, "radio.poll(chat)\nassert main['history'][-1]['status']=='Peer received'\n"
           "chat.leave(second)\nsecond=chat.join('Other check','wrong-password')")
        on(a, "chat.send(second,'Second group message',time.ticks_ms())\n"
           "packet2=chat.pending[-1]['packet']\nradio.send(packet2)")
        pause_radio()
        on(b, "radio.poll(chat)\nassert not second['history']\n"
           "chat.leave(second)\nsecond=chat.join('Other check','second')\n"
           "chat.visible=main['id']")
        on(a, "radio.send(packet2)")
        pause_radio()
        on(b, "radio.poll(chat)\nassert second['history'][-1]['text']=='Second group message'\n"
           "assert second['unread']==1")
        pause_radio()
        on(a, "radio.poll(chat)\nassert second['history'][-1]['status']=='Peer received'")
        for repl, report in zip(devices, reports):
            output = on(repl,
                "ui=ChatUI(lv,platform,chat)\nui.show_chat(main)\nui.compose()\n"
                "ui.screen.update_layout()\n"
                "assert ui.keyboard.get_y()+ui.keyboard.get_height()==platform.height\n"
                "assert ui.keyboard.get_height()<=160\n"
                "assert ui.editor.get_y()+ui.editor.get_height()<=ui.keyboard.get_y()\n"
                "ui.editor.set_text('UI send check')\n"
                "ui.keyboard.send_event(lv.EVENT.READY,None)\nui.tick()\n"
                "assert ui.page=='chat'\nassert main['history'][-1]['text']=='UI send check'\n"
                "ui.compose()\nui.editor.set_text('saved draft')\n"
                "ui.keyboard.send_event(lv.EVENT.CANCEL,None)\nui.tick()\n"
                "assert main['draft']=='saved draft'\n"
                "ui.home()\nui.add_group()\nui.editor.set_text('UI group')\n"
                "ui.keyboard.send_event(lv.EVENT.READY,None)\nui.tick()\n"
                "assert ui.page=='edit'\nassert ui.editor.get_password_mode()\n"
                "assert not ui.keyboard.get_popovers()\nui.editor.set_text('ui-password')\n"
                "ui.keyboard.send_event(lv.EVENT.READY,None)\nui.tick()\n"
                "assert ui.group['name']=='UI group'\nui.confirm_leave()\n"
                "ui.callbacks[-1](None)\nui.tick()\n"
                "assert len(chat.groups)==2\n"
                "ui.edit_name()\nui.editor.set_text('New name')\n"
                "ui.keyboard.send_event(lv.EVENT.READY,None)\nui.tick()\n"
                "assert chat.nickname=='New name'\n"
                "print('NATIVE_UI_CHECK=PASS')")
            report["native_ui"] = "pass"
            on(repl,
                "probe_path='/state/chat-check-'+binascii.hexlify(os.urandom(8)).decode()+'.json'\n"
                "probe_store=SettingsStore(probe_path)\n"
                "saved=Chat(radio.mac,probe_store.load('Before'),probe_store)\n"
                "saved.join('Saved group','saved-password')\nsaved.rename('After')\n"
                "restored=Chat(radio.mac,probe_store.load('Fallback'))\n"
                "assert restored.nickname=='After'\nassert restored.groups[0]['name']=='Saved group'\n"
                "saved.leave(saved.groups[0])\nassert not probe_store.load('Fallback')['groups']\n"
                "os.remove(probe_path)\nprobe_path=None\nprint('DEVICE_PERSISTENCE_CHECK=PASS')")
            report["persistence"] = "pass"
        result = {"status": "pass", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  "devices": reports, "checks": {
                      "bidirectional_messages_and_app_ack": "pass",
                      "duplicate_suppression": "pass", "wrong_password_rejection": "pass",
                      "background_group_receive": "pass", "native_keyboard_send_cancel": "pass",
                      "native_group_and_nickname_forms": "pass", "device_persistence": "pass"},
                  "physical_observations": "pending"}
        (artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        (artifacts / "observations.md").write_text(
            "# Nearby Chat physical observations\n\n"
            "Automated radio/UI results are in result.json. Physical results remain pending.\n\n"
            "| Try on each device | Result (pass/fail) | Notes |\n"
            "| --- | --- | --- |\n"
            "| Add the same group name and password using touch | | |\n"
            "| Type, correct, cancel/resume a draft, and send both directions | | |\n"
            "| Read long messages and scroll recent history | | |\n"
            "| Switch groups and read the unread count | | |\n"
            "| Verify keyboard stays within the screen and leaves room above | | |\n"
            "| Exit, relaunch from user files, and verify saved name/groups | | |\n")
        print("PASS: two-way radio, ACKs, deduplication, password rejection, groups, native UI, persistence")
        print("Evidence: " + str(artifacts / "result.json"))
    finally:
        for repl in devices:
            try:
                cleanup = (
                    "if globals().get('ui') is not None: ui.close()\n"
                    "if globals().get('radio') is not None: radio.close()\n"
                    "if globals().get('probe_path') is not None:\n"
                    " for path in (probe_path,probe_path+'.tmp'):\n"
                    "  try: os.remove(path)\n"
                    "  except OSError: pass\n")
                execute(repl, "exec(%r, chat_check)" % cleanup)
            except Exception as error:
                transcript.append("Cleanup: " + repr(error))
            repl.close()
        (artifacts / "transcript.txt").write_text("\n".join(transcript) + "\n")


def install(ports, artifacts):
    content = SOURCE.read_bytes()
    expected = hashlib.sha256(content).hexdigest()
    for port in ports:
        repl = RawRepl(port)
        try:
            repl.enter()
            info = execute(repl,
                "import os, binascii\n"
                "try:\n data=open(%r,'rb').read()\n"
                "except OSError as error:\n"
                " if error.args[0]!=2: raise\n data=None\n"
                "print('MISSING' if data is None else binascii.hexlify(data).decode())" % REMOTE)
            if info != "MISSING":
                before = bytes.fromhex(info)
                if before != content:
                    name = ("".join(c for c in port if c.isalnum()) + "-messaging-before-" +
                            hashlib.sha256(before).hexdigest()[:12] + ".py")
                    (artifacts / name).write_bytes(before)
            if info == "MISSING" or before != content:
                repl.stream_file(REMOTE, content, expected)
            command = "exec(open(%r).read(), {'__name__':'messaging'})\n" % REMOTE
            repl.serial.write(command.encode() + b"\x04")
            response = repl._read_until(b"NEARBY_CHAT_READY", timeout=20)
            time.sleep(0.3)
            response += repl.serial.read(repl.serial.in_waiting)
            if b"\x04" in response or b"Traceback" in response:
                raise RuntimeError(response.decode(errors="replace"))
            print(port + ": verified messaging.py and started Nearby Chat; port released")
        finally:
            repl.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "install"))
    parser.add_argument("--ports", nargs="+", required=True)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "tmp/messaging-check")
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    compile(SOURCE.read_text(), str(SOURCE), "exec")
    status = {"status": "running", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest()}
    if args.action == "check":
        (args.artifacts / "result.json").write_text(json.dumps(status, indent=2) + "\n")
    try:
        {"check": check, "install": install}[args.action](args.ports, args.artifacts)
    except Exception as error:
        import traceback
        (args.artifacts / "error.txt").write_text(traceback.format_exc())
        if args.action == "check":
            status.update(status="fail", error=str(error))
            (args.artifacts / "result.json").write_text(json.dumps(status, indent=2) + "\n")
        print("FAIL: %s; details: %s" % (error, args.artifacts / "error.txt"), file=sys.stderr)
        return 1
    (args.artifacts / "error.txt").write_text("No error in latest %s run.\n" % args.action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
