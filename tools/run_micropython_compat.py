"""Compile and exercise TartLab with the pinned MicroPython host tools."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "v1.23.0"
EXPECTED_COMMIT = "a61c446"


def executable(value: str) -> str:
    path = Path(value)
    if path.exists():
        return str(path.resolve())
    resolved = shutil.which(value)
    if resolved:
        return resolved
    raise FileNotFoundError("Executable not found: %s" % value)


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(
            "Command failed (%s):\n%s" % (" ".join(command), result.stdout))
    return result


def require_version(command: str, arguments: list[str], label: str) -> str:
    output = run([command, *arguments]).stdout.strip()
    expected = (r"\bv1\.23\.0\b", r"\ba61c446\b")
    if not any(re.search(pattern, output) for pattern in expected):
        raise RuntimeError(
            "%s must be %s / %s; reported:\n%s" %
            (label, EXPECTED_VERSION, EXPECTED_COMMIT, output))
    return output


def compile_distribution(
        mpy_cross: str, dist: Path, output: Path, target_arch: str) -> int:
    sources = sorted(dist.rglob("*.py"), key=lambda item: item.as_posix())
    if not sources:
        raise ValueError("No Python runtime files found under %s" % dist)
    for source in sources:
        destination = output / source.relative_to(dist).with_suffix(".mpy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        run([
            mpy_cross, "-march=" + target_arch,
            "-o", str(destination), str(source),
        ])
    return len(sources)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run TartLab's pinned MicroPython 1.23 compatibility tier")
    parser.add_argument("--micropython", required=True,
                        help="path or command name for MicroPython v1.23.0")
    parser.add_argument("--mpy-cross", required=True,
                        help="path or command name for mpy-cross v1.23.0")
    parser.add_argument("--dist", default="build/one/dist",
                        help="generated runtime distribution to compile")
    parser.add_argument(
        "--candidate-runtime",
        default="build/vendor/pydevices-candidate/runtime",
        help="generated Phase 4 PyDevices runtime to compile and probe")
    parser.add_argument(
        "--target-arch", default="xtensawin",
        help="mpy-cross native emitter architecture (default: xtensawin)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    micropython = executable(args.micropython)
    mpy_cross = executable(args.mpy_cross)
    dist = (ROOT / args.dist).resolve()
    if not dist.is_dir():
        raise FileNotFoundError(
            "Generated distribution not found: %s" % dist)
    candidate_runtime = (ROOT / args.candidate_runtime).resolve()
    if not candidate_runtime.is_dir():
        raise FileNotFoundError(
            "Generated PyDevices candidate not found: %s" % candidate_runtime)

    micropython_version = require_version(
        micropython, ["-c", "import sys; print(sys.version)"], "MicroPython")
    cross_version = require_version(mpy_cross, ["--version"], "mpy-cross")

    with tempfile.TemporaryDirectory(prefix="tartlab-mp123-") as temp:
        temporary = Path(temp)
        compiled = compile_distribution(
            mpy_cross, dist, temporary / "compiled", args.target_arch)
        candidate_compiled = compile_distribution(
            mpy_cross, candidate_runtime,
            temporary / "candidate-compiled", args.target_arch)
        device = temporary / "device"
        device.mkdir()
        probe = run([
            micropython,
            str(ROOT / "tests/micropython_compat.py"),
            str(ROOT),
            str(device),
        ]).stdout.strip()
        candidate_probe = run([
            micropython,
            str(ROOT / "tests/pydevices_candidate_compat.py"),
            str(candidate_runtime),
            str(ROOT / "src/files/assets/test.qoi"),
        ]).stdout.strip()

    if "MICROPYTHON_COMPAT_OK" not in probe:
        raise RuntimeError("Compatibility probe did not report success:\n" + probe)
    if "PYDEVICES_CANDIDATE_COMPAT_OK" not in candidate_probe:
        raise RuntimeError(
            "PyDevices candidate probe did not report success:\n"
            + candidate_probe)
    print("MicroPython:", micropython_version)
    print("mpy-cross:", cross_version)
    print("Target architecture:", args.target_arch)
    print("Compiled runtime modules:", compiled)
    print("Compiled PyDevices candidate modules:", candidate_compiled)
    print(probe)
    print(candidate_probe)


if __name__ == "__main__":
    main()
