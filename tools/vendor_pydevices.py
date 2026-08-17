"""Build a deterministic, allowlisted PyDevices migration candidate.

This tool stages current upstream sources for Phase 4 review.  It deliberately
does not modify ``src/lib/pydevices`` or a release distribution.  Promotion to
the legacy runtime remains a separate hardware-gated change.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile

from pydevices_upstream import validate_mapping
from release_utils import (
    canonical_source_bytes,
    file_inventory,
    inventory_identifier,
    read_json,
    sha256_source_file,
    write_json,
)


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build"
LOCK = ROOT / "vendor/pydevices-candidate.lock.json"
UPSTREAM_MAPPING = ROOT / "vendor/legacy-pydevices.upstream.json"
IMPORT_INVENTORY = ROOT / "vendor/legacy-pydevices.imports.json"
FILE_ROLES = {"dependency", "mapped-equivalent"}
COMPATIBILITY_ROLES = {"compatibility-adapter", "retained-local"}


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % label)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("%s must be a safe POSIX-relative path" % label)
    return value


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _remove_readonly(function, path, _error) -> None:
    """Let rmtree remove read-only git object files on Windows."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, onerror=_remove_readonly)


def validate_vendor_lock(
        lock: dict[str, object], mapping: dict[str, object],
        *, lock_root: Path = ROOT / "vendor",
) -> dict[str, object]:
    """Validate pins, explicit files, patches, and audit-map coverage."""
    if lock.get("schema") != 1:
        raise ValueError("unsupported PyDevices candidate lock schema")
    if lock.get("profile") != "legacy-mp123-candidate":
        raise ValueError("unexpected PyDevices candidate profile")
    if lock.get("promotion_status") != "research-only":
        raise ValueError("candidate lock must not approve runtime promotion")
    if lock.get("upstream_mapping") != UPSTREAM_MAPPING.relative_to(ROOT).as_posix():
        raise ValueError("candidate lock names the wrong upstream mapping")

    repositories = lock.get("repositories")
    if not isinstance(repositories, dict) or not repositories:
        raise ValueError("candidate lock must pin repositories")
    mapped_repositories = mapping["repositories"]
    if set(repositories) != set(mapped_repositories):
        raise ValueError("candidate repositories differ from the upstream audit")
    compared_fields = (
        "checkout_directory", "commit", "commit_date", "license",
        "license_canonical_sha256", "license_path", "url",
    )
    for name, repository in repositories.items():
        if not isinstance(repository, dict):
            raise ValueError("repository %s metadata must be an object" % name)
        audited = mapped_repositories[name]
        for field in compared_fields:
            if repository.get(field) != audited.get(field):
                raise ValueError(
                    "repository %s %s differs from upstream audit" % (name, field))

    files = lock.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("candidate lock must contain an explicit file allowlist")
    sources = []
    destinations = []
    mapped_sources = set()
    dependency_sources = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("candidate file entry must be an object")
        repository = item.get("repository")
        if repository not in repositories:
            raise ValueError("candidate file names an unpinned repository")
        source = _safe_relative(item.get("source"), "candidate source")
        destination = _safe_relative(
            item.get("destination"), "candidate destination")
        role = item.get("role")
        if role not in FILE_ROLES:
            raise ValueError("unsupported candidate file role for %s" % destination)
        source_key = (repository, source)
        sources.append(source_key)
        destinations.append(destination)
        if role == "mapped-equivalent":
            mapped_sources.add(source_key)
        else:
            dependency_sources.add(source_key)
    if len(sources) != len(set(sources)):
        raise ValueError("candidate allowlist contains duplicate sources")
    if len(destinations) != len(set(destinations)):
        raise ValueError("candidate allowlist contains duplicate destinations")

    audited_sources = {
        (reference["repository"], reference["path"])
        for entry in mapping["mappings"]
        for reference in entry["upstream"]
    }
    if mapped_sources != audited_sources:
        raise ValueError(
            "candidate mapped-equivalent coverage mismatch: missing=%s extra=%s" % (
                sorted(audited_sources - mapped_sources),
                sorted(mapped_sources - audited_sources)))
    if dependency_sources & audited_sources:
        raise ValueError("audited equivalents must not be labeled dependencies")

    external = lock.get("allowed_external_imports")
    if (not isinstance(external, list)
            or external != sorted(set(external))
            or not all(isinstance(name, str) and name for name in external)):
        raise ValueError("allowed_external_imports must be sorted and unique")

    compatibility_license = lock.get("compatibility_license")
    if not isinstance(compatibility_license, dict):
        raise ValueError("candidate must pin its compatibility license")
    license_source = _safe_relative(
        compatibility_license.get("source"), "compatibility license source")
    license_destination = _safe_relative(
        compatibility_license.get("destination"),
        "compatibility license destination")
    license_hash = compatibility_license.get("sha256")
    if (not isinstance(license_hash, str) or len(license_hash) != 64
            or any(char not in "0123456789abcdef" for char in license_hash)):
        raise ValueError("candidate compatibility license must pin a SHA-256")
    compatibility_license_path = ROOT / license_source
    if (not compatibility_license_path.is_file()
            or sha256_source_file(compatibility_license_path) != license_hash):
        raise ValueError("candidate compatibility license content mismatch")

    dynamic = lock.get("allowed_dynamic_import_sources")
    compatibility_files = lock.get("compatibility_files")
    if not isinstance(compatibility_files, list) or not compatibility_files:
        raise ValueError("candidate must contain explicit compatibility files")
    compatibility_sources = []
    compatibility_destinations = []
    compatibility_roles = []
    for item in compatibility_files:
        if not isinstance(item, dict):
            raise ValueError("candidate compatibility file must be an object")
        source = _safe_relative(
            item.get("source"), "candidate compatibility source")
        destination = _safe_relative(
            item.get("destination"), "candidate compatibility destination")
        role = item.get("role")
        if role not in COMPATIBILITY_ROLES:
            raise ValueError(
                "unsupported compatibility role for %s" % destination)
        expected_hash = item.get("sha256")
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                or any(char not in "0123456789abcdef" for char in expected_hash)):
            raise ValueError(
                "candidate compatibility file must pin a SHA-256")
        source_path = lock_root / source
        if (not source_path.is_file()
                or sha256_source_file(source_path) != expected_hash):
            raise ValueError(
                "candidate compatibility content mismatch: %s" % source)
        compatibility_sources.append(source)
        compatibility_destinations.append(destination)
        compatibility_roles.append(role)
    if len(compatibility_sources) != len(set(compatibility_sources)):
        raise ValueError("candidate contains duplicate compatibility sources")
    if len(compatibility_destinations) != len(set(compatibility_destinations)):
        raise ValueError("candidate contains duplicate compatibility destinations")
    if set(destinations) & set(compatibility_destinations):
        raise ValueError("upstream and compatibility destinations overlap")

    runtime_destinations = destinations + compatibility_destinations
    if (not isinstance(dynamic, list)
            or dynamic != sorted(set(dynamic))
            or not all(path in runtime_destinations for path in dynamic)):
        raise ValueError(
            "allowed_dynamic_import_sources must be sorted selected destinations")

    patches = lock.get("patches")
    if not isinstance(patches, list):
        raise ValueError("candidate patches must be a list")
    patch_paths = []
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("candidate patch entry must be an object")
        path = _safe_relative(patch.get("path"), "candidate patch path")
        expected_hash = patch.get("sha256")
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                or any(char not in "0123456789abcdef" for char in expected_hash)):
            raise ValueError("candidate patch must pin a SHA-256")
        patch_path = lock_root / path
        if (not patch_path.is_file()
                or sha256_source_file(patch_path) != expected_hash):
            raise ValueError("candidate patch content mismatch: %s" % path)
        patch_paths.append(path)
    if len(patch_paths) != len(set(patch_paths)):
        raise ValueError("candidate patch list contains duplicate paths")

    expected_summary = {
        "compatibility_adapter_files": compatibility_roles.count(
            "compatibility-adapter"),
        "dependency_files": len(dependency_sources),
        "mapped_equivalent_sources": len(mapped_sources),
        "patch_files": len(patches),
        "pinned_repositories": len(repositories),
        "retained_local_files": compatibility_roles.count("retained-local"),
        "runtime_files": len(runtime_destinations),
        "selected_source_files": len(files),
    }
    if lock.get("summary") != expected_summary:
        raise ValueError("candidate lock summary is stale")
    return lock


def check_vendor_lock(
        lock_path: Path = LOCK,
        mapping_path: Path = UPSTREAM_MAPPING,
) -> dict[str, object]:
    """Load and validate the checked-in candidate lock."""
    mapping = validate_mapping(
        read_json(mapping_path), read_json(IMPORT_INVENTORY))
    return validate_vendor_lock(
        read_json(lock_path), mapping, lock_root=lock_path.parent)


def _git(checkout: Path, *arguments: str, text: bool = True):
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        check=True, capture_output=True, text=text)
    return result.stdout.strip() if text else result.stdout


def _fetch_repositories(lock: dict[str, object], checkout_root: Path) -> None:
    for name, repository in lock["repositories"].items():
        checkout = checkout_root / repository["checkout_directory"]
        checkout.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", str(checkout)], check=True)
        _git(checkout, "remote", "add", "origin", repository["url"])
        _git(
            checkout, "fetch", "--quiet", "--depth=1", "origin",
            repository["commit"])
        _git(checkout, "checkout", "--quiet", "--detach", "FETCH_HEAD")


def _verify_repositories(
        lock: dict[str, object], checkout_root: Path,
) -> dict[str, Path]:
    result = {}
    for name, repository in lock["repositories"].items():
        checkout = checkout_root / repository["checkout_directory"]
        if not checkout.is_dir():
            raise ValueError("missing pinned checkout: %s" % checkout)
        head = _git(checkout, "rev-parse", "HEAD")
        if head != repository["commit"]:
            raise ValueError(
                "%s checkout is at %s, expected %s" % (
                    name, head, repository["commit"]))
        license_data = _git(
            checkout, "show", "%s:%s" % (
                repository["commit"], repository["license_path"]),
            text=False)
        if _sha256_bytes(_canonical_bytes(license_data)) != repository[
                "license_canonical_sha256"]:
            raise ValueError("pinned license mismatch for %s" % name)
        result[name] = checkout
    return result


def _module_name(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_name(path: Path) -> str:
    module = _module_name(path)
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _resolve_import_from(node: ast.ImportFrom, package: str) -> str:
    if not node.level:
        return node.module or ""
    package_parts = package.split(".") if package else []
    keep = len(package_parts) - node.level + 1
    if keep < 0:
        return ""
    parts = package_parts[:keep]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(part for part in parts if part)


def audit_runtime_imports(
        runtime_root: Path,
        allowed_external_imports: list[str],
        allowed_dynamic_import_sources: list[str],
) -> dict[str, object]:
    """Compile sources and require an exact explicit import dependency set."""
    files = sorted(runtime_root.rglob("*.py"))
    modules = {_module_name(path.relative_to(runtime_root)) for path in files}
    modules.discard("")
    top_levels = {module.split(".")[0] for module in modules}
    external = set()
    dynamic_sources = set()

    for path in files:
        relative = path.relative_to(runtime_root)
        source = path.read_bytes()
        tree = ast.parse(source, filename=str(relative))
        compile(source, str(relative), "exec")
        package = _package_name(relative)
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_import_from(node, package)
                if base:
                    targets.append(base)
            elif (isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)
                  and node.func.id == "__import__"):
                dynamic_sources.add(relative.as_posix())

            for target in targets:
                top_level = target.split(".")[0]
                if top_level not in top_levels:
                    external.add(top_level)
                    continue
                if target not in modules and any(
                        module.startswith(target + ".") for module in modules):
                    continue
                if "." in target and target not in modules:
                    raise ValueError(
                        "%s imports missing selected module %s" % (
                            relative.as_posix(), target))

    expected_external = set(allowed_external_imports)
    if external != expected_external:
        raise ValueError(
            "external import allowlist mismatch: missing=%s unexpected=%s" % (
                sorted(external - expected_external),
                sorted(expected_external - external)))
    expected_dynamic = set(allowed_dynamic_import_sources)
    if dynamic_sources != expected_dynamic:
        raise ValueError(
            "dynamic import source mismatch: missing=%s unexpected=%s" % (
                sorted(dynamic_sources - expected_dynamic),
                sorted(expected_dynamic - dynamic_sources)))
    return {
        "compiled_python_files": len(files),
        "dynamic_import_sources": sorted(dynamic_sources),
        "external_imports": sorted(external),
    }


def apply_patch_manifest(
        patch_path: Path,
        runtime_root: Path,
        allowed_destinations: set[str],
) -> dict[str, object]:
    """Apply a strict, hash-pinned JSON text replacement patch."""
    patch = read_json(patch_path)
    if patch.get("schema") != 1 or not isinstance(patch.get("operations"), list):
        raise ValueError("invalid candidate patch manifest: %s" % patch_path)
    changed = []
    for operation in patch["operations"]:
        relative = _safe_relative(operation.get("path"), "patch operation path")
        if relative not in allowed_destinations:
            raise ValueError("patch targets an unselected file: %s" % relative)
        target = runtime_root / relative
        before = target.read_bytes()
        if _sha256_bytes(before) != operation.get("before_sha256"):
            raise ValueError("patch preimage mismatch: %s" % relative)
        text = before.decode("utf-8")
        replacements = operation.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            raise ValueError("patch operation has no replacements: %s" % relative)
        for replacement in replacements:
            old = replacement.get("old")
            new = replacement.get("new")
            count = replacement.get("count")
            if (not isinstance(old, str) or not isinstance(new, str)
                    or not isinstance(count, int) or count < 1):
                raise ValueError("invalid replacement in patch for %s" % relative)
            if text.count(old) != count:
                raise ValueError("patch replacement count mismatch: %s" % relative)
            text = text.replace(old, new)
        after = text.encode("utf-8")
        if _sha256_bytes(after) != operation.get("after_sha256"):
            raise ValueError("patch result mismatch: %s" % relative)
        target.write_bytes(after)
        changed.append({
            "after_sha256": operation["after_sha256"],
            "before_sha256": operation["before_sha256"],
            "path": relative,
        })
    return {"operations": changed, "path": patch_path.name}


def _size_report(
        lock: dict[str, object], runtime_root: Path, licenses_root: Path,
) -> dict[str, object]:
    by_repository = defaultdict(lambda: {"bytes": 0, "files": 0})
    by_role = defaultdict(lambda: {"bytes": 0, "files": 0})
    by_top_level = defaultdict(lambda: {"bytes": 0, "files": 0})
    sized_files = [
        (item, item["repository"])
        for item in lock["files"]
    ] + [
        (item, "tartlab-compatibility")
        for item in lock["compatibility_files"]
    ]
    for item, origin in sized_files:
        path = runtime_root / item["destination"]
        size = len(canonical_source_bytes(path))
        repository = by_repository[origin]
        repository["bytes"] += size
        repository["files"] += 1
        role = by_role[item["role"]]
        role["bytes"] += size
        role["files"] += 1
        top = PurePosixPath(item["destination"]).parts[0]
        group = by_top_level[top]
        group["bytes"] += size
        group["files"] += 1
    runtime_inventory = file_inventory(
        runtime_root, normalize_source_text=True)
    license_inventory = file_inventory(
        licenses_root, normalize_source_text=True)
    return {
        "licenses": {
            "expanded_bytes": sum(item["size"] for item in license_inventory),
            "files": len(license_inventory),
        },
        "runtime": {
            "by_repository": dict(sorted(by_repository.items())),
            "by_role": dict(sorted(by_role.items())),
            "by_top_level": dict(sorted(by_top_level.items())),
            "expanded_bytes": sum(item["size"] for item in runtime_inventory),
            "files": len(runtime_inventory),
            "identifier": inventory_identifier(runtime_inventory),
        },
        "schema": 1,
    }


def _build_from_checkouts(
        lock: dict[str, object],
        lock_path: Path, mapping_path: Path, checkout_root: Path,
        staging: Path,
) -> dict[str, object]:
    checkouts = _verify_repositories(lock, checkout_root)
    runtime_root = staging / "runtime"
    licenses_root = staging / "licenses"
    runtime_root.mkdir(parents=True)
    licenses_root.mkdir()
    source_records = []
    for item in lock["files"]:
        repository = lock["repositories"][item["repository"]]
        checkout = checkouts[item["repository"]]
        source_spec = "%s:%s" % (repository["commit"], item["source"])
        data = _git(checkout, "show", source_spec, text=False)
        destination = runtime_root / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        source_records.append({
            "destination": item["destination"],
            "repository": item["repository"],
            "role": item["role"],
            "source": item["source"],
            "source_sha256": _sha256_bytes(data),
        })

    compatibility_records = []
    for item in lock["compatibility_files"]:
        source = lock_path.parent / item["source"]
        data = canonical_source_bytes(source)
        destination = runtime_root / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        compatibility_records.append({
            "destination": item["destination"],
            "role": item["role"],
            "source": source.relative_to(ROOT).as_posix(),
            "source_sha256": _sha256_bytes(data),
        })

    license_records = []
    for name, repository in lock["repositories"].items():
        data = _git(
            checkouts[name], "show", "%s:%s" % (
                repository["commit"], repository["license_path"]),
            text=False)
        destination = licenses_root / name / "LICENSE"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(data)
        license_records.append({
            "canonical_sha256": _sha256_bytes(_canonical_bytes(data)),
            "destination": destination.relative_to(staging).as_posix(),
            "repository": name,
            "source": repository["license_path"],
        })

    compatibility_license = lock["compatibility_license"]
    license_source = ROOT / compatibility_license["source"]
    data = canonical_source_bytes(license_source)
    destination = licenses_root / compatibility_license["destination"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    license_records.append({
        "canonical_sha256": _sha256_bytes(data),
        "destination": destination.relative_to(staging).as_posix(),
        "repository": "tartlab-compatibility",
        "source": compatibility_license["source"],
    })

    # Patches are reserved for pinned upstream sources. TartLab compatibility
    # files must be reviewed and re-hashed directly instead of patched in place.
    allowed_destinations = {
        item["destination"] for item in lock["files"]
    }
    patch_records = []
    for patch in lock["patches"]:
        patch_path = lock_path.parent / patch["path"]
        record = apply_patch_manifest(
            patch_path, runtime_root, allowed_destinations)
        record["sha256"] = patch["sha256"]
        record["path"] = patch["path"]
        patch_records.append(record)

    import_audit = audit_runtime_imports(
        runtime_root,
        lock["allowed_external_imports"],
        lock["allowed_dynamic_import_sources"],
    )
    output_by_destination = {
        item["path"]: item for item in file_inventory(
            runtime_root, normalize_source_text=True)
    }
    for record in source_records + compatibility_records:
        output = output_by_destination[record["destination"]]
        record["output_sha256"] = output["sha256"]
        record["output_size"] = output["size"]

    sizes = _size_report(lock, runtime_root, licenses_root)
    write_json(staging / "size-report.json", sizes)
    provenance = {
        "compatibility_files": compatibility_records,
        "import_audit": import_audit,
        "licenses": license_records,
        "lock_file": lock_path.relative_to(ROOT).as_posix(),
        "lock_sha256": sha256_source_file(lock_path),
        "patches": patch_records,
        "profile": lock["profile"],
        "promotion_status": lock["promotion_status"],
        "repositories": lock["repositories"],
        "runtime_identifier": sizes["runtime"]["identifier"],
        "schema": 1,
        "selected_files": source_records,
        "upstream_mapping": mapping_path.relative_to(ROOT).as_posix(),
        "upstream_mapping_sha256": sha256_source_file(mapping_path),
    }
    write_json(staging / "provenance.json", provenance)
    return provenance


def _validate_output_path(output: Path) -> Path:
    output = output.resolve()
    build_root = BUILD_ROOT.resolve()
    if output == build_root or build_root not in output.parents:
        raise ValueError("candidate output must be a child of %s" % build_root)
    return output


def build_vendor_candidate(
        *,
        output: Path,
        checkout_root: Path | None = None,
        fetch: bool = False,
        clean: bool = False,
        lock_path: Path = LOCK,
        mapping_path: Path = UPSTREAM_MAPPING,
) -> dict[str, object]:
    """Build and publish a fully verified deterministic candidate directory."""
    if fetch == (checkout_root is not None):
        raise ValueError("select exactly one of fetch or checkout_root")
    output = _validate_output_path(output)
    if output.exists() and not clean:
        raise FileExistsError(
            "candidate output exists; pass --clean to replace it: %s" % output)

    mapping = validate_mapping(
        read_json(mapping_path), read_json(IMPORT_INVENTORY))
    lock = validate_vendor_lock(
        read_json(lock_path), mapping, lock_root=lock_path.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        prefix=output.name + ".staging-", dir=output.parent))
    fetched = None
    try:
        if fetch:
            fetched = Path(tempfile.mkdtemp(
                prefix="pydevices-fetch-", dir=output.parent))
            _fetch_repositories(lock, fetched)
            active_checkouts = fetched
        else:
            active_checkouts = checkout_root.resolve()
        provenance = _build_from_checkouts(
            lock, lock_path, mapping_path,
            active_checkouts, staging)
        if output.exists():
            _remove_tree(output)
        staging.replace(output)
        return provenance
    finally:
        if staging.exists():
            _remove_tree(staging)
        if fetched is not None and fetched.exists():
            _remove_tree(fetched)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--checkout-root", type=Path,
        help="directory containing already-pinned repository checkouts")
    source.add_argument(
        "--fetch", action="store_true",
        help="fetch exact commits into a temporary build workspace")
    parser.add_argument(
        "--output", type=Path,
        default=BUILD_ROOT / "vendor/pydevices-candidate")
    parser.add_argument(
        "--clean", action="store_true",
        help="replace an existing output only after staging verifies")
    args = parser.parse_args()
    output = args.output.resolve()
    provenance = build_vendor_candidate(
        output=output,
        checkout_root=args.checkout_root,
        fetch=args.fetch,
        clean=args.clean,
    )
    runtime = read_json(output / "size-report.json")["runtime"]
    print(
        "Built {files} allowlisted files / {expanded_bytes} bytes at {identifier}"
        .format(**runtime))
    print("Promotion status: %s" % provenance["promotion_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
