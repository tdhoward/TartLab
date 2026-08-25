"""Prepare the pinned ESP-IDF container for lvgl_micropython's merger."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def prepare_python_environment(source: Path, target: Path) -> None:
    """Expose the official container's Python environment at the expected path."""
    if not source.is_dir():
        raise ValueError(f"ESP-IDF Python environment not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if target.resolve() != source.resolve():
            raise ValueError(f"unexpected existing Python environment link: {target}")
        return
    if target.exists():
        raise ValueError(f"Python environment target already exists: {target}")
    os.symlink(source, target, target_is_directory=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-env", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a build command is required after --")

    expected = Path.home() / ".espressif/python_env"
    prepare_python_environment(args.python_env, expected)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
