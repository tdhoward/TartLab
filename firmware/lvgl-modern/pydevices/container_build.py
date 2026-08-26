"""Apply tracked build overlays, run cmods, and restore source inputs."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess


BOARD_NAME = "TARTLAB_T_DISPLAY_S3_PRO"
ESP_IDF_COMMIT = "fcae32885b0296b32044cb99ecbdc50d98dddb83"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--micropython", type=Path,
                        default=Path("/workspace/micropython"))
    parser.add_argument("--tartlab", type=Path, default=Path("/tartlab"))
    parser.add_argument("--displayif", type=Path,
                        default=Path("/workspace/displayif"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    source = args.tartlab / "firmware/lvgl-modern/pydevices"
    displayif_patch = source / "patches/displayif-mperrno.patch"
    board_source = source / "board"
    board_target = (
        args.micropython / "ports/esp32/boards" / BOARD_NAME
    )
    build_target = (
        args.micropython / "ports/esp32" / f"build-{BOARD_NAME}"
    )
    mpy_cross_build = args.micropython / "mpy-cross/build"
    manifest_target = args.workspace / "manifest-user.py"
    python_env_source = Path("/opt/esp/python_env")
    python_env_target = Path.home() / ".espressif/python_env"
    actual_idf_commit = subprocess.run(
        ["git", "-C", "/opt/esp/idf", "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual_idf_commit != ESP_IDF_COMMIT:
        raise RuntimeError(
            f"ESP-IDF commit is {actual_idf_commit}, expected {ESP_IDF_COMMIT}"
        )
    # ESP-IDF 5.5.1's esp32s3 timing CMakeLists exports an intentionally empty
    # include directory that Git cannot represent. The official container does
    # not pre-create it, while CMake requires every exported include to exist.
    Path(
        "/opt/esp/idf/components/esp_hw_support/mspi_timing_tuning/"
        "port/esp32s3/include"
    ).mkdir(parents=True, exist_ok=True)

    if board_target.exists():
        raise RuntimeError(f"refusing to replace existing board: {board_target}")
    if manifest_target.exists():
        raise RuntimeError(
            f"refusing to replace existing manifest: {manifest_target}"
        )
    expected_build_parent = (args.micropython / "ports/esp32").resolve()
    if build_target.resolve().parent != expected_build_parent:
        raise RuntimeError(f"unexpected build target: {build_target}")
    if build_target.exists():
        shutil.rmtree(build_target)
    expected_mpy_cross_parent = (args.micropython / "mpy-cross").resolve()
    if mpy_cross_build.resolve().parent != expected_mpy_cross_parent:
        raise RuntimeError(
            f"unexpected mpy-cross build target: {mpy_cross_build}"
        )
    if mpy_cross_build.exists():
        shutil.rmtree(mpy_cross_build)
    if not python_env_source.is_dir():
        raise RuntimeError(
            f"ESP-IDF Python environment not found: {python_env_source}"
        )
    python_env_target.parent.mkdir(parents=True, exist_ok=True)
    if not python_env_target.exists():
        os.symlink(python_env_source, python_env_target,
                   target_is_directory=True)

    subprocess.run(
        ["git", "-C", str(args.displayif), "apply", "--check",
         "--ignore-space-change", "--ignore-whitespace",
         str(displayif_patch)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(args.displayif), "apply",
         "--ignore-space-change", "--ignore-whitespace",
         str(displayif_patch)],
        check=True,
    )
    try:
        shutil.copytree(board_source, board_target)
        shutil.copyfile(source / "manifest-user.py", manifest_target)
        # A Windows host may materialize the checked-out shell file with CRLF
        # even though the pinned Git blob is LF. Execute the exact blob so the
        # recipe is host-independent and the upstream checkout stays clean.
        build_script = subprocess.run(
            ["git", "-C", str(args.workspace), "show", "HEAD:build_mp.sh"],
            check=True, capture_output=True,
        ).stdout
        build_environment = os.environ.copy()
        build_environment["WORKSPACE_DIR"] = str(args.workspace)
        subprocess.run(
            [
                "bash", "-s", "--",
                "--port", "esp32",
                "--board", BOARD_NAME,
            ],
            cwd=args.workspace,
            env=build_environment,
            input=build_script,
            check=True,
        )
    finally:
        manifest_target.unlink(missing_ok=True)
        shutil.rmtree(board_target, ignore_errors=True)
        subprocess.run(
            ["git", "-C", str(args.displayif), "apply", "--reverse",
             "--ignore-space-change", "--ignore-whitespace",
             str(displayif_patch)],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
