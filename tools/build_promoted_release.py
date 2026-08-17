"""Build the normal legacy release with the Phase 4 promoted vendor payload."""

import argparse
import json
from pathlib import Path

from build_phase4_test_release import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dist", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mpy-cross", type=Path, required=True)
    parser.add_argument("--target-arch", default="xtensawin")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    result = build(
        args.base_dist, args.candidate, args.output, args.version,
        mpy_cross=args.mpy_cross, target_arch=args.target_arch,
        clean=args.clean, promote=True)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
