"""Validate the reviewed Phase 4 mapping to current PyDevices sources.

The mapping records research pins and compatibility findings.  It is not the
runtime vendor lock: no mapped upstream file is copied into a release by this
tool.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

from release_utils import read_json, sha256_source_file


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "vendor/legacy-pydevices.imports.json"
MAPPING = ROOT / "vendor/legacy-pydevices.upstream.json"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
RELATIONSHIPS = {
    "moved_evolved",
    "renamed_evolved",
    "restructured_evolved",
    "split_evolved",
    "no_current_equivalent",
}


def reachable_paths(inventory: dict[str, object]) -> set[str]:
    """Return the reviewed reachable vendor paths from the import inventory."""
    result = set()
    for category in inventory["categories"].values():
        result.update(category["files"])
    return result


def _relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % label)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("%s must be a safe POSIX-relative path" % label)
    return value


def validate_mapping(
        mapping: dict[str, object], inventory: dict[str, object],
) -> dict[str, object]:
    """Validate mapping schema, pins, and exact reachable-file coverage."""
    if mapping.get("schema") != 1:
        raise ValueError("unsupported upstream mapping schema")
    if mapping.get("inventory_file") != INVENTORY.relative_to(ROOT).as_posix():
        raise ValueError("upstream mapping names the wrong import inventory")
    if mapping.get("runtime_replacement_approved") is not False:
        raise ValueError("audit mapping must not approve a runtime replacement")

    repositories = mapping.get("repositories")
    if not isinstance(repositories, dict) or not repositories:
        raise ValueError("upstream mapping must pin at least one repository")
    for name, repository in repositories.items():
        if not isinstance(repository, dict):
            raise ValueError("repository %s metadata must be an object" % name)
        url = repository.get("url")
        if not isinstance(url, str) or not url.startswith(
                "https://github.com/PyDevices/"):
            raise ValueError("repository %s must use an official HTTPS URL" % name)
        if not COMMIT_RE.fullmatch(str(repository.get("commit", ""))):
            raise ValueError("repository %s must pin a full commit" % name)
        if repository.get("license") != "MIT":
            raise ValueError("repository %s must record its reviewed license" % name)
        _relative_path(repository.get("license_path"),
                       "repository %s license_path" % name)
        if not SHA256_RE.fullmatch(
                str(repository.get("license_canonical_sha256", ""))):
            raise ValueError("repository %s must pin its license content" % name)
        _relative_path(repository.get("checkout_directory"),
                       "repository %s checkout_directory" % name)

    entries = mapping.get("mappings")
    if not isinstance(entries, list):
        raise ValueError("upstream mappings must be a list")
    local_paths = []
    unresolved = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("upstream mapping entry must be an object")
        local_path = _relative_path(entry.get("local_path"), "local_path")
        local_paths.append(local_path)
        relationship = entry.get("relationship")
        if relationship not in RELATIONSHIPS:
            raise ValueError("unsupported relationship for %s" % local_path)
        if entry.get("drop_in_compatible") is not False:
            raise ValueError("%s must not be marked drop-in compatible" % local_path)
        upstream = entry.get("upstream")
        if not isinstance(upstream, list):
            raise ValueError("%s upstream references must be a list" % local_path)
        if relationship == "no_current_equivalent":
            unresolved += 1
            if upstream:
                raise ValueError("%s has an equivalent despite its status" % local_path)
        elif not upstream:
            raise ValueError("%s is missing an upstream reference" % local_path)
        for reference in upstream:
            if not isinstance(reference, dict):
                raise ValueError("%s has an invalid upstream reference" % local_path)
            if reference.get("repository") not in repositories:
                raise ValueError("%s names an unpinned repository" % local_path)
            _relative_path(reference.get("path"),
                           "%s upstream path" % local_path)

    if len(local_paths) != len(set(local_paths)):
        raise ValueError("upstream mapping contains duplicate local paths")
    expected = reachable_paths(inventory)
    actual = set(local_paths)
    if actual != expected:
        raise ValueError(
            "upstream mapping coverage mismatch: missing=%s unexpected=%s" % (
                sorted(expected - actual), sorted(actual - expected)))

    expected_summary = {
        "drop_in_compatible_files": 0,
        "mapped_files": len(entries) - unresolved,
        "pinned_repositories": len(repositories),
        "reviewed_reachable_files": len(entries),
        "without_current_equivalent": unresolved,
    }
    if mapping.get("summary") != expected_summary:
        raise ValueError("upstream mapping summary is stale")
    return mapping


def _git(checkout: Path, *arguments: str) -> str:
    command = ["git", "-C", str(checkout), *arguments]
    result = subprocess.run(
        command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def verify_checkouts(mapping: dict[str, object], checkout_root: Path) -> None:
    """Verify optional local checkouts against every recorded commit and path."""
    checkouts = {}
    for name, repository in mapping["repositories"].items():
        checkout = checkout_root / repository["checkout_directory"]
        if not checkout.is_dir():
            raise ValueError("missing upstream checkout: %s" % checkout)
        head = _git(checkout, "rev-parse", "HEAD")
        if head != repository["commit"]:
            raise ValueError("upstream checkout %s is at %s, expected %s" % (
                name, head, repository["commit"]))
        license_path = checkout / repository["license_path"]
        if sha256_source_file(license_path) != repository[
                "license_canonical_sha256"]:
            raise ValueError("upstream license content changed for %s" % name)
        checkouts[name] = checkout

    for entry in mapping["mappings"]:
        for reference in entry["upstream"]:
            repository = mapping["repositories"][reference["repository"]]
            checkout = checkouts[reference["repository"]]
            commit_path = "%s:%s" % (repository["commit"], reference["path"])
            _git(checkout, "cat-file", "-e", commit_path)


def check_upstream_mapping(
        mapping_path: Path = MAPPING,
        inventory_path: Path = INVENTORY,
        checkout_root: Path | None = None,
) -> dict[str, object]:
    """Load and validate the reviewed mapping, optionally checking git trees."""
    mapping = validate_mapping(read_json(mapping_path), read_json(inventory_path))
    if checkout_root is not None:
        verify_checkouts(mapping, checkout_root.resolve())
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout-root", type=Path,
        help="optionally verify already-fetched upstream checkouts and paths")
    args = parser.parse_args()
    mapping = check_upstream_mapping(checkout_root=args.checkout_root)
    summary = mapping["summary"]
    print(
        "Reviewed {reviewed_reachable_files} reachable files against "
        "{pinned_repositories} pinned repositories: {mapped_files} mapped, "
        "{without_current_equivalent} without a current equivalent, 0 drop-in."
        .format(**summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
