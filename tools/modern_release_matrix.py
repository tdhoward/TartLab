"""List or validate every board eligible for a modern candidate release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from board_catalog import load_catalog
from check_modern_release import check as check_release
from release_utils import sha256_file


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "lvgl-modern"
ELIGIBLE_STATUSES = frozenset({"candidate", "qualified"})


def release_boards() -> list[dict[str, Any]]:
    boards = [
        descriptor for descriptor in load_catalog().values()
        if descriptor["runtime_profile"] == PROFILE
        and descriptor["support_status"] in ELIGIBLE_STATUSES
    ]
    boards.sort(key=lambda descriptor: descriptor["id"])
    if not boards:
        raise ValueError("modern catalog has no candidate or qualified boards")
    return boards


def check_matrix(release: Path, *, dist: Path | None = None
                 ) -> dict[str, object]:
    boards = release_boards()
    manifest = json.loads(
        (release / "modern-manifest.json").read_text(encoding="utf-8"))
    declared = manifest.get("compatibility", {}).get("boards")
    expected_ids = [descriptor["id"] for descriptor in boards]
    if not isinstance(declared, dict) or set(declared) != set(expected_ids):
        raise ValueError(
            "modern release board set differs from the eligible catalog")

    results = {}
    for descriptor in boards:
        board_id = descriptor["id"]
        results[board_id] = check_release(
            release, PROFILE, descriptor["firmware"]["sha256"],
            dist=dist, board_id=board_id,
        )
    return {
        "profile": PROFILE,
        "boards": {
            board_id: result["preflight"]["firmware_sha256"]
            for board_id, result in results.items()
        },
        "candidate_checksums_sha256": sha256_file(
            release / "checksums.json"),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    check = actions.add_parser("check")
    check.add_argument("--release", type=Path, required=True)
    check.add_argument("--dist", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "list":
        for descriptor in release_boards():
            print(descriptor["id"])
        return 0
    print(json.dumps(
        check_matrix(args.release, dist=args.dist), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
