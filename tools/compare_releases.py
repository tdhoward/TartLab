"""Fail unless two independently built release directories are byte-identical."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from release_utils import file_inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    args = parser.parse_args()
    first = file_inventory(args.first)
    second = file_inventory(args.second)
    if not first or not second:
        raise SystemExit("Release directory is empty")
    if first != second:
        first_map = {item["path"]: item for item in first}
        second_map = {item["path"]: item for item in second}
        for path in sorted(set(first_map) | set(second_map)):
            if first_map.get(path) != second_map.get(path):
                raise SystemExit("Release builds differ at %s" % path)
        raise SystemExit("Release builds differ")
    print("Releases are byte-identical (%s files)" % len(first))


if __name__ == "__main__":
    main()
