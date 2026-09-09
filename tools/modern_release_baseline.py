"""Capture signed platform baselines, assemble distributions and plan testing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

from modern_qualification import (
    ROOT, REPOSITORY, SNAPSHOT, REPORT, BASELINE, component,
    exact, safe_relative, load_baseline, check_candidate,
)
from release_utils import ensure_safe_output, file_inventory, read_json, sha256_file, sha256_source_file, write_json

DEFAULT_PLAN = ROOT / "profiles/modern-release-plan.json"
DEFAULT_ARCHIVES = ROOT / "build/modern-baseline"


def load_plan(path=DEFAULT_PLAN):
    plan = read_json(path)
    exact(plan, ("schema", "mode", "baseline", "resource_limits", "update_sources"), "release plan")
    if plan["schema"] != 1 or plan["mode"] not in ("platform", "app-browser"):
        raise ValueError("Invalid release plan")
    baseline = None
    capsule_path = None
    if plan["baseline"] is not None:
        exact(plan["baseline"], ("path", "sha256"), "baseline pin")
        capsule_path = (ROOT / str(safe_relative(plan["baseline"]["path"]))).resolve()
        if ROOT not in capsule_path.parents:
            raise ValueError("Baseline path escapes the checkout")
        baseline = load_baseline(capsule_path, plan["baseline"]["sha256"])
    if plan["mode"] == "app-browser" and baseline is None:
        raise ValueError("App/browser assembly requires a signed qualified baseline")
    return {k: v for k, v in plan.items() if k != "baseline"}, baseline, capsule_path


def safe_output(output, *sources):
    output = ensure_safe_output(output, (ROOT, *sources))
    for name in ("src", "tools", "boards", "profiles", "tests", "firmware",
                 ".git", ".github", ".agents", ".codex"):
        protected = (ROOT / name).resolve()
        if output == protected or protected in output.parents:
            raise ValueError("Output is inside a protected source directory")
    for source in sources:
        if source.resolve() in output.parents:
            raise ValueError("Output must not be inside its input")
    return output


def assemble(dist, output, baseline=None, archives=DEFAULT_ARCHIVES, *, clean=False):
    """Compose into a new directory, retaining only candidate apps/browser bytes."""
    dist = dist.resolve()
    output = safe_output(output, dist, archives)
    if not dist.is_dir() or any(p.is_symlink() for p in dist.rglob("*")):
        raise ValueError("Distribution must exist and contain no symbolic links")
    platform_bytes = {}
    excluded = []
    if baseline:
        current = {"/" + r["path"]: r for r in file_inventory(dist)}
        expected = baseline["snapshot"]
        protected = expected["contract"]["protected_defaults"]
        import release as release_tools
        actual_protected = {p: r for p, r in current.items() if release_tools.is_protected_path(p)}
        if actual_protected != protected:
            raise ValueError("Protected provisioning defaults differ from baseline")
        # Validate every downloaded TAR before writing the composed distribution.
        found = {}
        for package in expected["contract"]["packages"]:
            filename = package["file_name"]
            safe_relative(filename)
            archive = archives / filename
            if sha256_file(archive) != baseline["checksums"].get(filename):
                raise ValueError("Baseline archive checksum mismatch")
            with tarfile.open(archive, "r:") as tar:
                for member in tar.getmembers():
                    safe_relative(member.name)
                    if not member.isfile():
                        raise ValueError("Baseline archive contains a non-file member")
                    path = package["target"].rstrip("/") + "/" + member.name
                    if path in found or path not in expected["files"]:
                        raise ValueError("Baseline archive path mismatch")
                    data = tar.extractfile(member).read()
                    if hashlib.sha256(data).hexdigest() != expected["files"][path]["sha256"]:
                        raise ValueError("Baseline payload hash mismatch")
                    found[path] = True
                    if component(path) == "platform":
                        platform_bytes[path] = data
        if set(found) != set(expected["files"]):
            raise ValueError("Incomplete baseline archive inventory")
        excluded = sorted(p for p in set(current) | set(expected["files"])
                          if component(p) == "platform" and p not in protected and
                          current.get(p, {}).get("sha256") != expected["files"].get(p, {}).get("sha256"))
    if output.exists():
        if not clean:
            raise FileExistsError("Assembly output exists; use --clean")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for record in file_inventory(dist):
        path = "/" + record["path"]
        if baseline and component(path) == "platform" and path not in protected:
            continue
        target = output / record["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dist / record["path"], target)
    for path, data in platform_bytes.items():
        target = output / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"files": len(file_inventory(output)), "platform_reused": baseline is not None,
            "excluded_platform_changes": excluded}


def capture(release, evidence, output):
    if output.exists():
        raise FileExistsError("Baseline records are immutable; choose a new output")
    # Preserve exact UTF-8 bytes, including line endings, for signature checks.
    def raw(path):
        return path.read_bytes().decode("utf-8")
    capsule = {"schema": 1,
               "documents": {name: raw(release / name) for name in (
                   SNAPSHOT, REPORT, "checksums.json", "promotion_attestation.json")},
               "evidence": raw(evidence),
               "bundle": raw(release / "release-attestation.sigstore.json")}
    # Verify before leaving a baseline record on disk.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="tartlab-capture-") as temporary:
        path = Path(temporary) / BASELINE
        write_json(path, capsule)
        load_baseline(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
    return {"path": str(output), "sha256": sha256_source_file(output)}


def prepare(plan_path, output):
    request, baseline, _ = load_plan(plan_path)
    if not baseline or request["mode"] != "app-browser":
        return {"downloads": 0}
    output = safe_output(output)
    output.mkdir(parents=True, exist_ok=True)
    version = baseline["snapshot"]["version"]
    packages = baseline["snapshot"]["contract"]["packages"]
    for package in packages:
        filename = package["file_name"]
        if len(safe_relative(filename).parts) != 1:
            raise ValueError("Unsafe baseline asset")
        path = output / filename
        if not path.exists():
            subprocess.run(["gh", "release", "download", version, "--repo", REPOSITORY,
                            "--pattern", filename, "--dir", str(output)], check=True)
        if sha256_file(path) != baseline["checksums"].get(filename):
            raise ValueError("Cached/downloaded baseline archive differs from signed checksum")
    return {"downloads": len(packages), "version": version}


def template(release):
    current, analysis = check_candidate(release)
    prior_boards = {}
    if (release / BASELINE).exists():
        prior_boards = json.loads(read_json(release / BASELINE)["evidence"])["boards"]
    pending = lambda: {"status": "pending", "evidence": []}
    result = {"schema": 3, "profile": current["profile"], "version": current["version"],
              "target_repository": REPOSITORY,
              "candidate_checksums_sha256": sha256_file(release / "checksums.json"),
              "report_sha256": sha256_file(release / REPORT), "operator": "",
              "tested_at_utc": "", "checks": {k: pending() for k in analysis["checks"]},
              "boards": {}}
    for board, gates in analysis["boards"].items():
        identity = current["contract"]["compatibility"]["boards"][board]
        observed = {"model": identity["name"], "pcb_revision": "", "chip_revision": "",
                    "flash_size_bytes": identity["flash_size_bytes"],
                    "psram_size_bytes": identity["psram_size_bytes"]}
        prior = prior_boards.get(board)
        if prior and prior["firmware_sha256"] == identity["firmware"]["sha256"]:
            observed = prior["board"]
        outcomes = {}
        for gate, decision in gates.items():
            outcomes[gate] = dict(pending(), mode="fresh") if decision["mode"] == "fresh" else {
                "status": "passed", "mode": "inherited", "baseline_sha256": analysis["baseline_sha256"]}
        result["boards"][board] = {
            "firmware_sha256": identity["firmware"]["sha256"], "board": observed,
            "gates": outcomes}
    return result


def checklist(analysis):
    lines = ["# Qualification for " + analysis["version"], "",
             "Platform changed: " + str(analysis["platform_changed"]).lower(), ""]
    for name, description in analysis["checks"].items():
        lines.append("- [ ] %s: %s" % (name, description))
    for board, gates in analysis["boards"].items():
        lines.extend(("", "## " + board, ""))
        for name, decision in gates.items():
            if decision["mode"] == "fresh":
                lines.append("- [ ] %s: %s" % (name, " ".join(decision["reasons"])))
            else:
                lines.append("- Inherited: %s (baseline %s)" % (name, analysis["baseline_sha256"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    cap = actions.add_parser("capture")
    cap.add_argument("--release", type=Path, required=True)
    cap.add_argument("--evidence", type=Path, required=True)
    cap.add_argument("--output", type=Path, required=True)
    prep = actions.add_parser("prepare")
    prep.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    prep.add_argument("--output", type=Path, default=DEFAULT_ARCHIVES)
    assembly = actions.add_parser("assemble")
    assembly.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    assembly.add_argument("--archives", type=Path, default=DEFAULT_ARCHIVES)
    assembly.add_argument("--dist", type=Path, required=True)
    assembly.add_argument("--output", type=Path, required=True)
    assembly.add_argument("--clean", action="store_true")
    for name in ("report", "template"):
        action = actions.add_parser(name)
        action.add_argument("--release", type=Path, required=True)
        action.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "capture":
        result = capture(args.release, args.evidence, args.output)
    elif args.action == "prepare":
        result = prepare(args.plan, args.output)
    elif args.action == "assemble":
        request, baseline, _ = load_plan(args.plan)
        result = assemble(args.dist, args.output,
                          baseline if request["mode"] == "app-browser" else None,
                          args.archives, clean=args.clean)
    else:
        if args.output.exists() or args.output.resolve().parent == args.release.resolve():
            raise ValueError("Use a new output outside the immutable candidate directory")
        if args.action == "template":
            write_json(args.output, template(args.release))
        else:
            _, analysis = check_candidate(args.release)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(checklist(analysis), encoding="utf-8")
        result = {"output": str(args.output)}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
