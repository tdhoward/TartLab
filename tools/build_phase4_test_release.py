"""Build a guarded Phase 4 hardware-comparison release.

This helper overlays the generated PyDevices candidate on a normal legacy
distribution.  Its artifacts are always marked research-only and cannot pass
the normal legacy inventory/promotion path.
"""

import argparse
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import makedist
import release
from release_utils import ensure_safe_output, read_json, sha256_source_file, write_json


COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def build(base_dist, candidate, output, version, *, clean=False):
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

    archives = output / "release"
    metadata = release.build_release(
        dist, archives, version,
        research_vendor_provenance=provenance_path,
        research_vendor_source=runtime)
    evidence = {
        "schema": 1,
        "artifact_status": "research-only-not-for-promotion",
        "candidate_profile": provenance["profile"],
        "runtime_identifier": provenance["runtime_identifier"],
        "runtime_transform": "python-minifier-3.2.0",
        "provenance_sha256": sha256_source_file(provenance_path),
        "size_report": read_json(size_report_path)["runtime"],
        "size_report_sha256": sha256_source_file(size_report_path),
        "release_build_metadata_sha256": sha256_source_file(
            archives / "build_metadata.json"),
    }
    write_json(output / "phase4_test_metadata.json", evidence)
    return {"build": metadata, "phase4": evidence}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dist", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    result = build(
        args.base_dist, args.candidate, args.output, args.version,
        clean=args.clean)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
