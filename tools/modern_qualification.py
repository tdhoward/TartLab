"""Content-based modern release qualification; no device or board-model logic.

Snapshots are signed release subjects. Baseline capsules retain the exact signed
JSON bytes, so promotion can verify their origin without trusting a local cache.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from urllib.parse import urlsplit

from release_utils import canonical_source_bytes, read_json, sha256_file, sha256_source_file, write_json

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PROFILE = "lvgl-modern"
REPOSITORY = "tdhoward/TartLab-modern-releases"
GATES = ("adult_provisioning", "hardware", "ota", "recovery", "release_feed_isolation")
SNAPSHOT = "qualification-snapshot.json"
REPORT = "qualification-report.json"
BASELINE = "platform-baseline.json"
REQUEST = "qualification-request.json"
TAG = re.compile(r"modern-v\d+\.\d+(?:\.\d+)?$")
HASH = re.compile(r"[0-9a-f]{64}$")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Invalid %s fields" % label)


def require_hash(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Expected a lowercase SHA-256")
    return value


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Unsafe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError("Unsafe relative path")
    return path


def component(path):
    if path.startswith("/ide/www/"):
        return "browser"
    if path.startswith(("/files/help/", "/files/assets/")):
        return "apps"
    return "platform"


def build_inputs(root=ROOT):
    """Record host behavior separately from device bytes and browser inputs."""
    paths = {root / name for name in (
        "makedist.py", "release.py", "requirements-build.txt")}
    paths.update((root / "tools").glob("*.py"))
    host = {p.relative_to(root).as_posix(): hashlib.sha256(
        canonical_source_bytes(p)).hexdigest() for p in sorted(paths) if p.is_file()}
    try:
        minifier = importlib.metadata.version("python-minifier")
    except importlib.metadata.PackageNotFoundError:
        minifier = None
    host["toolchain"] = {"python": sys.version.split()[0], "python_minifier": minifier}
    browser = {}
    for name in ("package.json", "package-lock.json", "webpack.config.js"):
        path = root / "src/ide/www" / name
        if path.is_file():
            browser[name] = hashlib.sha256(canonical_source_bytes(path)).hexdigest()
    # JavaScript behavior changes must not be mistaken for cosmetic CSS edits
    # merely because webpack emits both into the same bundle.
    for path in sorted((root / "src/ide/www/js").rglob("*.js")):
        browser[path.relative_to(root / "src/ide/www").as_posix()] = hashlib.sha256(
            canonical_source_bytes(path)).hexdigest()
    # HTML can introduce inline scripts and device commands as well as labels.
    for path in sorted((root / "src/ide/www").glob("*.html")):
        browser[path.name] = hashlib.sha256(canonical_source_bytes(path)).hexdigest()
    try:
        browser["node"] = subprocess.check_output(
            ["node", "--version"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        browser["node"] = None
    return {"host": host, "browser": browser}


def payload_files(release, manifest, epoch):
    """Read archives without extracting; reject aliases, links and overlaps."""
    import release as release_tools
    files = {}
    contracts = []
    sizes = {}
    names = set()
    for package in manifest["packages"]:
        name = package["name"]
        if name in names:
            raise ValueError("Duplicate package")
        names.add(name)
        filename = package["file_name"]
        if len(safe_relative(filename).parts) != 1:
            raise ValueError("Unsafe package filename")
        target = package["target"]
        if target != "/":
            safe_relative(target.removeprefix("/"))
        if not target.startswith("/") or type(package["clear_first"]) is not bool:
            raise ValueError("Invalid package installation contract")
        archive = release / filename
        if sha256_file(archive) != package["sha256"] or \
                archive.stat().st_size != package["archive_size"]:
            raise ValueError("Package hash or size mismatch")
        # Preserve order: installation order is part of the update contract.
        contracts.append({k: v for k, v in package.items() if k not in (
            "sha256", "archive_size", "expanded_size", "selected_expanded_sizes")})
        expanded = 0
        per_board = {}
        with tarfile.open(archive, "r:") as tar:
            for member in tar.getmembers():
                safe_relative(member.name)
                if not member.isfile() or member.uid != 0 or member.gid != 0 or \
                        member.mtime != epoch:
                    raise ValueError("Unsupported archive member or metadata")
                installed = target.rstrip("/") + "/" + member.name
                if installed in files:
                    raise ValueError("Duplicate or overlapping installed path")
                if release_tools.is_protected_path(installed):
                    raise ValueError("Archive targets protected path")
                data = tar.extractfile(member).read()
                normalized = data
                if installed.startswith("/ide/www/") and installed.endswith(".gz"):
                    gzip.decompress(data)  # Validate the stream before normalizing.
                    # Only the four gzip MTIME bytes are non-content metadata.
                    normalized = data[:4] + b"\0" * 4 + data[8:]
                files[installed] = {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "content_sha256": hashlib.sha256(normalized).hexdigest(),
                    "size": len(data), "package": name, "mode": member.mode,
                }
                expanded += len(data)
                if package.get("selection") == "board-id-subtree":
                    board = member.name.split("/")[0]
                    per_board[board] = per_board.get(board, 0) + len(data)
        if expanded != package["expanded_size"]:
            raise ValueError("Expanded package size mismatch")
        if per_board and per_board != package.get("selected_expanded_sizes"):
            raise ValueError("Selected board sizes mismatch")
        sizes[name] = {"archive": archive.stat().st_size, "expanded": expanded,
                       "selected": per_board}
    # A file may not be an ancestor of another file, even across packages.
    for path in files:
        if any(str(p) in files for p in PurePosixPath(path).parents):
            raise ValueError("Installed file/directory collision")
    return files, contracts, sizes


def snapshot(release, inputs):
    manifest = read_json(release / "modern-manifest.json")
    metadata = read_json(release / "build_metadata.json")
    if manifest.get("profile") != PROFILE or manifest.get("channel") != {
            "repository": REPOSITORY, "manifest": "modern-manifest.json"} or \
            not TAG.fullmatch(manifest.get("version", "")):
        raise ValueError("Unexpected release identity")
    files, packages, sizes = payload_files(release, manifest, metadata["source_date_epoch"])
    boards = manifest["compatibility"]["boards"]
    if not isinstance(boards, dict) or not boards:
        raise ValueError("Qualification requires an explicit board matrix")
    usage = {}
    for board in boards:
        usage[board] = {"archive_bytes": sum(p["archive"] for p in sizes.values()),
                        "expanded_bytes": sum(p["selected"].get(board, 0)
                            if p["selected"] else p["expanded"] for p in sizes.values())}
    protected = {"/" + item["path"]: item for item in read_json(
        release / "dist_inventory.json") if "/" + item["path"] not in files}
    contract = {"compatibility": manifest["compatibility"], "packages": packages,
                "support_window": read_json(release / "support-window.json"),
                "protected_defaults": protected}
    platform = {p: v for p, v in files.items() if component(p) == "platform"}
    common_compatibility = {k: v for k, v in manifest["compatibility"].items()
                            if k not in ("boards", "firmware", "default_board_id")}
    board_identities = {}
    for board, board_contract in boards.items():
        selected_files = {p: v for p, v in platform.items()
                          if not p.startswith("/board/") or p.startswith("/board/" + board + "/")}
        board_identities[board] = digest({
            "files": selected_files, "host": inputs["host"],
            "contract": dict(contract, compatibility=dict(common_compatibility, board=board_contract))})
    return {"schema": 1, "profile": PROFILE, "version": manifest["version"],
            "contract": contract, "files": files, "usage": usage, "inputs": inputs,
            "board_platform_sha256": board_identities,
            "platform_sha256": digest({"files": platform, "contract": contract,
                                        "host": inputs["host"]})}


def request_for(current, request=None):
    request = request if request is not None else {
        "schema": 1, "mode": "platform", "resource_limits": current["usage"],
        "update_sources": {}}
    exact(request, ("schema", "mode", "resource_limits", "update_sources"), "request")
    if request["schema"] != 1 or request["mode"] not in ("platform", "app-browser"):
        raise ValueError("Unsupported qualification request")
    limits = request["resource_limits"] or current["usage"]
    exact(limits, current["usage"], "resource board set")
    for board, usage in current["usage"].items():
        exact(limits[board], usage, "resource limits")
        for key, amount in usage.items():
            if type(limits[board][key]) is not int or limits[board][key] < amount:
                raise ValueError("Candidate exceeds requested resource limits for " + board)
    sources = request["update_sources"]
    if not isinstance(sources, dict):
        raise ValueError("Update sources must map release tags to platform hashes")
    for version, identity in sources.items():
        if not TAG.fullmatch(version):
            raise ValueError("Invalid supported update source tag")
        require_hash(identity)
    return dict(request, resource_limits=limits)


def report(current, baseline=None, request=None):
    request = request_for(current, request)
    old = baseline["snapshot"] if baseline else None
    baseline_hash = baseline["sha256"] if baseline else None
    changed = []
    metadata_only = []
    if old:
        for path in sorted(set(old["files"]) | set(current["files"])):
            before, after = old["files"].get(path), current["files"].get(path)
            if before == after:
                continue
            if before and after and {k: v for k, v in before.items() if k != "sha256"} == \
                    {k: v for k, v in after.items() if k != "sha256"}:
                metadata_only.append(path)
            else:
                changed.append({"path": path, "component": component(path),
                                "change": "added" if before is None else
                                "removed" if after is None else "modified"})
    else:
        changed = [{"path": p, "component": component(p), "change": "unqualified"}
                   for p in sorted(current["files"])]
    platform_changed = not old or current["platform_sha256"] != old["platform_sha256"]
    # This deliberately treats any shared platform change conservatively. No
    # inferred dependency graph is allowed to silently reduce hardware coverage.
    if request["mode"] == "app-browser" and platform_changed:
        raise ValueError("App/browser release changed the qualified platform or host contract")
    categories = {c["component"] for c in changed}
    browser_behavior = old is None or current["inputs"]["browser"] != old["inputs"]["browser"]
    checks = {"automated": "Run build, compatibility, integrity and update/recovery suites.",
              "resources": "Verify download/staging/install space and the declared resource envelope.",
              "update_paths": "Verify each declared installed source and future update access."}
    if "browser" in categories or browser_behavior:
        checks["browser"] = "Check browser editing, saving, commands and update controls as affected."
    boards = {}
    for board in current["usage"]:
        reasons = {gate: [] for gate in GATES}
        board_changed = not old or current["board_platform_sha256"][board] != \
            old["board_platform_sha256"].get(board)
        if board_changed:
            for gate in GATES:
                reasons[gate].append("New or changed platform, board, build inputs or installation contract.")
        else:
            if "apps" in categories:
                reasons["hardware"].append("Focused app play/input/rendering/resource and exit-to-IDE checks.")
            if browser_behavior:
                reasons["hardware"].append("Browser/device integration smoke for changed JavaScript or dependencies.")
            old_limits = baseline["report"]["request"]["resource_limits"].get(board, {})
            if any(request["resource_limits"][board][k] > old_limits.get(k, -1)
                   for k in current["usage"][board]):
                for gate in ("adult_provisioning", "ota", "recovery"):
                    reasons[gate].append("The requested storage envelope exceeds qualified limits.")
            qualified_sources = set(baseline["report"]["request"]["update_sources"].values())
            sources = set(request["update_sources"].values())
            if not sources or not sources.issubset(qualified_sources):
                for gate in ("ota", "recovery"):
                    reasons[gate].append("Supported installed updater contracts need fresh source-path evidence.")
        reasons["release_feed_isolation"].append("Check the new release's authenticated subjects and feed isolation.")
        boards[board] = {gate: {"mode": "fresh" if reasons[gate] else "inherited",
                               "reasons": reasons[gate]} for gate in GATES}
    return {"schema": 1, "profile": PROFILE, "version": current["version"],
            "snapshot_sha256": digest(current), "baseline_sha256": baseline_hash,
            "request": request, "platform_changed": platform_changed,
            "changed_files": changed, "gzip_timestamp_only": metadata_only,
            "checks": checks, "boards": boards}


def _signed_documents(capsule):
    exact(capsule, ("schema", "documents", "evidence", "bundle"), "baseline capsule")
    if capsule["schema"] != 1:
        raise ValueError("Unsupported baseline capsule")
    exact(capsule["documents"], (SNAPSHOT, REPORT, "checksums.json",
                                 "promotion_attestation.json"), "signed documents")
    return {name: json.loads(raw) for name, raw in capsule["documents"].items()}


def verify_signatures(capsule, version):
    """Always verify the release signer, never the qualification signer."""
    from check_modern_release_authenticity import (
        load_json, DEFAULT_POLICY, validate_policy, verification_command)
    policy = load_json(DEFAULT_POLICY)
    validate_policy(policy)
    with tempfile.TemporaryDirectory(prefix="tartlab-baseline-") as temporary:
        root = Path(temporary)
        bundle = root / "release-attestation.sigstore.json"
        bundle.write_bytes(capsule["bundle"].encode("utf-8"))
        for name, raw in capsule["documents"].items():
            path = root / name
            path.write_bytes(raw.encode("utf-8"))
            subprocess.run(verification_command(path, policy, bundle=bundle,
                source_ref="refs/tags/" + version, purpose="release"),
                check=True, stdout=subprocess.DEVNULL)


def load_baseline(path, expected_sha256=None):
    if expected_sha256 and sha256_source_file(path) != require_hash(expected_sha256):
        raise ValueError("Pinned baseline capsule hash mismatch")
    capsule = read_json(path)
    docs = _signed_documents(capsule)
    current, analysis = docs[SNAPSHOT], docs[REPORT]
    promotion = docs["promotion_attestation.json"]
    version = current.get("version", "")
    if not TAG.fullmatch(version) or current.get("profile") != PROFILE or \
            promotion.get("profile") != PROFILE or promotion.get("target_repository") != REPOSITORY or \
            promotion.get("tartlab_version") != version:
        raise ValueError("Baseline is not a promoted modern release")
    for name in (SNAPSHOT, REPORT):
        raw_hash = hashlib.sha256(capsule["documents"][name].encode()).hexdigest()
        if docs["checksums.json"].get(name) != raw_hash:
            raise ValueError("Baseline signed checksum mismatch")
    candidate_hash = hashlib.sha256(capsule["documents"]["checksums.json"].encode()).hexdigest()
    if promotion.get("candidate_checksums_sha256") != candidate_hash or \
            promotion.get("hardware_evidence_sha256") != hashlib.sha256(
                capsule["evidence"].encode()).hexdigest():
        raise ValueError("Baseline promotion/evidence binding mismatch")
    if analysis.get("snapshot_sha256") != digest(current) or analysis.get("version") != version:
        raise ValueError("Baseline report/snapshot mismatch")
    board_hashes = {b: r["firmware"]["sha256"] for b, r in
                    current["contract"]["compatibility"]["boards"].items()}
    if promotion.get("boards") != board_hashes:
        raise ValueError("Baseline promotion board set mismatch")
    # The release signer attests that inherited claims were validated at its
    # promotion; do not recursively download an unbounded ancestry chain.
    evidence = json.loads(capsule["evidence"])
    validate_results(evidence, analysis, current, candidate_hash,
                     hashlib.sha256(capsule["documents"][REPORT].encode()).hexdigest())
    verify_signatures(capsule, version)
    return {"sha256": sha256_source_file(path), "snapshot": current, "report": analysis,
            "capsule": capsule, "checksums": docs["checksums.json"]}


def _references(value):
    if not isinstance(value, list) or not value:
        raise ValueError("Fresh test results require evidence references")
    for record in value:
        exact(record, ("url", "sha256"), "evidence reference")
        require_hash(record["sha256"])
        url = urlsplit(record["url"])
        if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Evidence needs a durable public HTTPS URL")


def validate_results(evidence, analysis, current, candidate_hash, report_hash):
    exact(evidence, ("schema", "profile", "version", "target_repository",
        "candidate_checksums_sha256", "report_sha256", "operator", "tested_at_utc",
        "checks", "boards"), "schema-3 qualification")
    if evidence["schema"] != 3 or evidence["profile"] != PROFILE or \
            evidence["target_repository"] != REPOSITORY or evidence["version"] != current["version"] or \
            evidence["candidate_checksums_sha256"] != require_hash(candidate_hash) or \
            evidence["report_sha256"] != require_hash(report_hash):
        raise ValueError("Qualification candidate/report identity mismatch")
    if not isinstance(evidence["operator"], str) or not evidence["operator"].strip():
        raise ValueError("Qualification requires an operator")
    stamp = evidence["tested_at_utc"]
    if not isinstance(stamp, str) or not stamp.endswith("Z"):
        raise ValueError("Qualification requires a UTC test timestamp")
    datetime.fromisoformat(stamp[:-1] + "+00:00")
    exact(evidence["checks"], analysis["checks"], "qualification checks")
    for result in evidence["checks"].values():
        exact(result, ("status", "evidence"), "check result")
        if result["status"] != "passed":
            raise ValueError("Required qualification check has not passed")
        _references(result["evidence"])
    exact(evidence["boards"], analysis["boards"], "qualification board set")
    identities = current["contract"]["compatibility"]["boards"]
    for board, result in evidence["boards"].items():
        exact(result, ("firmware_sha256", "board", "gates"), "board result")
        if result["firmware_sha256"] != identities[board]["firmware"]["sha256"]:
            raise ValueError("Qualification firmware mismatch")
        observed = result["board"]
        exact(observed, ("model", "pcb_revision", "chip_revision", "flash_size_bytes",
                         "psram_size_bytes"), "physical board observation")
        expected = identities[board]
        if observed["model"] != expected["name"] or \
                observed["pcb_revision"] not in expected["revisions"] or \
                not isinstance(observed["chip_revision"], str) or not observed["chip_revision"].strip() or \
                any(type(observed[k]) is not int or observed[k] != expected[k]
                    for k in ("flash_size_bytes", "psram_size_bytes")):
            raise ValueError("Physical board observation differs from compatible hardware")
        exact(result["gates"], GATES, "board gates")
        for gate, outcome in result["gates"].items():
            mode = analysis["boards"][board][gate]["mode"]
            exact(outcome, ("status", "mode", "baseline_sha256") if mode == "inherited"
                  else ("status", "mode", "evidence"), "gate result")
            if outcome["status"] != "passed" or outcome["mode"] != mode:
                raise ValueError("Required fresh/inherited gate result mismatch")
            if mode == "inherited":
                if not analysis["baseline_sha256"] or outcome["baseline_sha256"] != analysis["baseline_sha256"]:
                    raise ValueError("Inherited gate baseline mismatch")
            else:
                _references(outcome["evidence"])
    return {"profile": PROFILE, "version": current["version"],
            "candidate_checksums_sha256": candidate_hash,
            "boards": {b: r["firmware"]["sha256"] for b, r in identities.items()},
            "passed_gates": list(GATES)}


def check_candidate(release):
    checksums = read_json(release / "checksums.json")
    for name, expected in checksums.items():
        if len(safe_relative(name).parts) != 1 or sha256_file(release / name) != require_hash(expected):
            raise ValueError("Candidate checksum mismatch")
    for name in (SNAPSHOT, REPORT, REQUEST, "modern-manifest.json",
                 "build_metadata.json", "dist_inventory.json", "support-window.json"):
        if name not in checksums:
            raise ValueError("Candidate is missing qualification metadata")
    for package in read_json(release / "modern-manifest.json")["packages"]:
        if package["file_name"] not in checksums:
            raise ValueError("Candidate checksums omit a package")
    stored = read_json(release / SNAPSHOT)
    current = snapshot(release, stored["inputs"])
    if current != stored:
        raise ValueError("Candidate snapshot differs from actual installed content")
    baseline = None
    if (release / BASELINE).exists():
        if BASELINE not in checksums:
            raise ValueError("Unauthenticated baseline capsule")
        baseline = load_baseline(release / BASELINE)
    analysis = report(current, baseline, read_json(release / REQUEST))
    if analysis != read_json(release / REPORT):
        raise ValueError("Candidate qualification report was altered or is stale")
    return current, analysis


def write_candidate_metadata(release, request=None, baseline=None, inputs=None):
    current = snapshot(release, inputs if inputs is not None else build_inputs())
    analysis = report(current, baseline, request)
    write_json(release / SNAPSHOT, current)
    write_json(release / REQUEST, analysis["request"])
    write_json(release / REPORT, analysis)
    if baseline:
        # Copy original capsule bytes elsewhere in the builder; digest must not
        # depend on re-serializing a pinned capsule with different whitespace.
        if sha256_source_file(release / BASELINE) != baseline["sha256"]:
            raise ValueError("Copied baseline differs from verified capsule")
    return analysis
