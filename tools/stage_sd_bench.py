"""Stage a built distribution plus an explicit SD-root diagnostic, without formatting.

The original boot.py/main.py are retained under /.tartlab-bench/packaged-*.
The diagnostic tests root startup, SD imports and paths, and standalone RGB.
It does not enable the unintegrated TartLab platform or qualify the board.
"""

import argparse
import hashlib
import json
from pathlib import Path
import uuid

from board_catalog import select_board
from phase1_device import RawRepl


ROOT = Path(__file__).resolve().parents[1]


def check_collision(path, actual, expected, journal, marker_matches):
    if actual is None or actual == expected:
        return
    resumable = (marker_matches and not journal["complete"] and
                 path in journal["owned"] and path not in journal["verified"])
    if not resumable:
        raise ValueError("existing SD file differs; preserved: " + path)


def stage(args):
    board = select_board(args.board)
    source = args.distribution.resolve()
    for required in ("boot.py", "main.py", "lib/tartlabutils/__init__.py",
                     "board/" + args.board + "/" + board["selector"]["module"] + ".py"):
        if not (source / required).is_file():
            raise ValueError("incomplete distribution: " + required)
    if not any((source / ("ide/www/" + name)).is_file() for name in ("index.html", "index.html.gz")):
        raise ValueError("incomplete distribution: IDE web assets")
    files = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            if relative in ("boot.py", "main.py"):
                relative = ".tartlab-bench/packaged-" + relative
            files[relative] = path.read_bytes()
    for destination, fixture in (("boot.py", "sd_root_boot.py"), ("main.py", "sd_root_smoke.py"),
                                 (".tartlab-bench/rgb_smoke.py", "rgb_smoke.py")):
        files[destination] = (ROOT / "tools/device" / fixture).read_bytes()
    files["device/board.json"] = (json.dumps({"schema": 1, "board_id": args.board}) + "\n").encode()
    files["device/hdwconfig.py"] = (
        "# Bench selector, not a qualified installation.\nfrom %s import *\n" % board["selector"]["module"]).encode()
    inventory = {path: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                 for path, data in files.items()}
    args.session.mkdir(parents=True, exist_ok=True)
    journal_path = args.session / "sd-stage.json"
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())
        if journal["inventory"] != inventory or journal["board"] != args.board:
            raise ValueError("session belongs to a different payload")
    else:
        journal = {"board": args.board, "inventory": inventory, "owned": [], "verified": [],
                   "complete": False, "token": uuid.uuid4().hex}

    def save():
        journal_path.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")

    repl = RawRepl(args.port, timeout=20)
    mounted = False
    try:
        repl.enter()
        repl.exec("import os, vfs, hashlib, binascii, json\nfrom external_root import open_sd\n"
                  "from hdwconfig import BOARD_CONFIG\n"
                  "assert BOARD_CONFIG['id'] == %r\n" % args.board +
                  "assert [p for f,p in vfs.mount()] == ['/']\n"
                  "_stage_card = open_sd(BOARD_CONFIG)\n"
                  "try:\n vfs.mount(vfs.VfsFat(_stage_card), '/sd')\n"
                  "except Exception:\n _stage_card.deinit()\n raise\n")
        mounted = True
        repl.exec("def _stage_hash(path):\n"
                  " try:\n  stream=open(path,'rb')\n"
                  " except OSError as error:\n"
                  "  if error.args[0] == 2: return None\n"
                  "  raise\n"
                  " digest=hashlib.sha256()\n"
                  " with stream:\n"
                  "  while True:\n   chunk=stream.read(4096)\n   if not chunk: break\n   digest.update(chunk)\n"
                  " return binascii.hexlify(digest.digest()).decode()\n")
        # Bind resumed partial writes to a marker on this card. A completed
        # installation is verified without replacing later user modifications.
        token = journal.get("token")
        marker_path = "/sd/.tartlab-bench/install-id"
        marker_hash = json.loads(repl.exec("print(json.dumps(_stage_hash(%r)))" % marker_path).decode())
        expected_marker = hashlib.sha256(token.encode()).hexdigest() if token else None
        marker_matches = token is not None and marker_hash == expected_marker
        if token and ((journal["owned"] and not marker_matches) or
                      (marker_hash is not None and not marker_matches)):
            raise ValueError("SD card does not match this staging session; preserved")
        # Inspect every collision before writing anything to the volume.
        order = sorted(files, key=lambda path: (path == "device/hdwconfig.py", path))
        existing = {}
        for path in order:
            value = json.loads(repl.exec("print(json.dumps(_stage_hash(%r)))" % ("/sd/" + path)).decode())
            existing[path] = value
            check_collision(path, value, inventory[path]["sha256"], journal, marker_matches)
        save()
        if token and not marker_matches:
            repl.exec("try:\n os.mkdir('/sd/.tartlab-bench')\nexcept OSError as error:\n"
                      " if error.args[0] != 17: raise\n")
            repl.stream_file(marker_path, token.encode(), expected_marker)
            repl.exec("os.sync()")
        for index, path in enumerate(order, 1):
            if existing[path] != inventory[path]["sha256"]:
                directories = list(Path(path).parents)[:-1]
                for directory in reversed(directories):
                    remote = "/sd/" + directory.as_posix()
                    repl.exec("try:\n os.mkdir(%r)\nexcept OSError as error:\n"
                              " if error.args[0] != 17: raise\n" % remote)
                if path not in journal["owned"]:
                    journal["owned"].append(path)
                save()
                repl.stream_file("/sd/" + path, files[path], inventory[path]["sha256"])
                repl.exec("os.sync()")
            if path not in journal["verified"]:
                journal["verified"].append(path)
            save()
            if index % 10 == 0 or index == len(order):
                print("SD_STAGE %d/%d files verified" % (index, len(order)), flush=True)
        journal["complete"] = True
        save()
    finally:
        try:
            if mounted:
                repl.exec("os.sync()\nvfs.umount('/sd')\n_stage_card.deinit()")
        finally:
            repl.close()
    print(json.dumps({"files": len(files), "bytes": sum(len(data) for data in files.values()),
                      "evidence": str(journal_path), "startup": "diagnostic"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--board", required=True)
    parser.add_argument("--distribution", required=True, type=Path)
    parser.add_argument("--session", required=True, type=Path)
    stage(parser.parse_args())


if __name__ == "__main__":
    main()
