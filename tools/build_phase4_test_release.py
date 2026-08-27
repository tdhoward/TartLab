"""Build a guarded Phase 4 hardware-comparison release.

This CLI overlays the generated PyDevices candidate on a normal legacy
distribution and always marks the result research-only. The promoted release
wrapper imports the shared build function with the additional profile identity
gate enabled.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import makedist
import release
from release_utils import (
    ensure_safe_output,
    file_inventory,
    inventory_identifier,
    read_json,
    sha256_source_file,
    write_json,
)


COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
MPY_VERSION = "v1.23.0"
MPY_COMMIT = "a61c446"
MPY_FORMAT = "mpy v6.3"


def _wsl_path(path):
    path = Path(path).resolve()
    drive = path.drive.rstrip(":").lower()
    if not drive:
        raise ValueError("WSL compiler requires a drive-qualified path: %s" % path)
    relative = path.as_posix().split(":", 1)[1].lstrip("/")
    return "/mnt/%s/%s" % (drive, relative)


def _compiler(mpy_cross):
    mpy_cross = Path(mpy_cross).resolve()
    if not mpy_cross.is_file():
        raise FileNotFoundError(mpy_cross)
    is_elf = mpy_cross.read_bytes()[:4] == b"\x7fELF"
    if is_elf and os.name == "nt":
        return ["wsl", _wsl_path(mpy_cross)], True
    return [str(mpy_cross)], False


def _run(command):
    result = subprocess.run(
        command, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(
            "Command failed (%s):\n%s" % (" ".join(command), result.stdout))
    return result.stdout.strip()


def _valid_compiler_version(version):
    """Accept the pinned release tag or its exact checkout commit identity."""
    return MPY_FORMAT in version and (
        MPY_VERSION in version or MPY_COMMIT in version)


def compile_candidate(runtime, mpy_cross, target_arch):
    """Compile the minified candidate for the exact qualified firmware ABI."""
    runtime = Path(runtime).resolve()
    sources = sorted(runtime.rglob("*.py"), key=lambda item: item.as_posix())
    if not sources:
        raise ValueError("Candidate runtime has no Python sources: %s" % runtime)
    command, via_wsl = _compiler(mpy_cross)
    version = _run(command + ["--version"])
    if not _valid_compiler_version(version):
        raise ValueError(
            "Phase 4 compiler must report %s/%s and %s; got %s" %
            (MPY_VERSION, MPY_COMMIT, MPY_FORMAT, version))

    compiled = runtime.parent / (runtime.name + "-compiled")
    if compiled.exists():
        shutil.rmtree(compiled)
    compiled.mkdir(parents=True)
    compile_commands = []
    for source in sources:
        relative = source.relative_to(runtime)
        destination = compiled / relative.with_suffix(".mpy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_arg = _wsl_path(source) if via_wsl else str(source)
        destination_arg = _wsl_path(destination) if via_wsl else str(destination)
        arguments = [
            "-march=" + target_arch,
            "-s", relative.as_posix(),
            "-o", destination_arg,
            source_arg,
        ]
        if via_wsl:
            compile_commands.append([command[1], *arguments])
        else:
            _run(command + arguments)
    if via_wsl:
        script = "set -eu\n" + "\n".join(
            shlex.join(item) for item in compile_commands)
        _run(["wsl", "sh", "-c", script])

    expected = {
        path.relative_to(runtime).with_suffix(".mpy").as_posix()
        for path in sources
    }
    actual = {
        path.relative_to(compiled).as_posix()
        for path in compiled.rglob("*.mpy")
    }
    if actual != expected:
        raise ValueError("Compiled candidate path set mismatch")
    shutil.rmtree(runtime)
    compiled.rename(runtime)
    inventory = file_inventory(runtime)
    return {
        "compiler_sha256": sha256_source_file(Path(mpy_cross)),
        "compiler_version": version,
        "modules": len(sources),
        "packaged_identifier": inventory_identifier(inventory),
        "target_arch": target_arch,
    }


def build(
        base_dist, candidate, output, version, *, mpy_cross,
        target_arch="xtensawin", clean=False, promote=False):
    base_dist = Path(base_dist).resolve()
    candidate = Path(candidate).resolve()
    output = ensure_safe_output(
        Path(output), (ROOT, base_dist, candidate))
    runtime = candidate / "runtime"
    provenance_path = candidate / "provenance.json"
    size_report_path = candidate / "size-report.json"
    for required in (base_dist, runtime):
        if not required.is_dir():
            raise FileNotFoundError(required)
    for required in (provenance_path, size_report_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    provenance = release.validate_research_vendor(provenance_path, runtime)

    if output.exists():
        if not clean:
            raise FileExistsError(
                "Output already exists; rerun with --clean: %s" % output)
        shutil.rmtree(output)
    output.mkdir(parents=True)
    dist = output / "dist"
    shutil.copytree(base_dist, dist, ignore=COPY_IGNORE)
    target = dist / "lib/pydevices"
    if target.exists():
        shutil.rmtree(target)
    makedist.copy_tree(runtime, target, minify_python=True)
    compilation = compile_candidate(target, mpy_cross, target_arch)

    archives = output / "release"
    metadata = release.build_release(
        dist, archives, version,
        research_vendor_provenance=provenance_path,
        research_vendor_source=runtime,
        promoted_vendor_compilation=(compilation if promote else None),
        require_promoted_vendor=promote,
        allow_dirty=not promote,
        allow_toolchain_mismatch=not promote)
    evidence = {
        "schema": 1,
        "artifact_status": (
            "legacy-release-candidate" if promote else
            "research-only-not-for-promotion"),
        "candidate_profile": provenance["profile"],
        "runtime_identifier": provenance["runtime_identifier"],
        "runtime_transform": "python-minifier-3.2.0+mpy-cross-v1.23.0",
        "mpy_compilation": compilation,
        "provenance_sha256": sha256_source_file(provenance_path),
        "size_report": read_json(size_report_path)["runtime"],
        "size_report_sha256": sha256_source_file(size_report_path),
        "release_build_metadata_sha256": sha256_source_file(
            archives / "build_metadata.json"),
    }
    evidence_name = (
        "vendor_release_metadata.json" if promote else
        "phase4_test_metadata.json")
    write_json(output / evidence_name, evidence)
    return {
        "build": metadata,
        ("vendor" if promote else "phase4"): evidence,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dist", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--mpy-cross", type=Path, required=True,
        help="path to the pinned MicroPython v1.23.0 mpy-cross executable")
    parser.add_argument(
        "--target-arch", default="xtensawin",
        help="mpy-cross native emitter architecture (default: xtensawin)")
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    result = build(
        args.base_dist, args.candidate, args.output, args.version,
        mpy_cross=args.mpy_cross, target_arch=args.target_arch,
        clean=args.clean)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
