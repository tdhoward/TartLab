"""Create or verify the legacy PyDevices static reachability inventory.

The inventory is deliberately conservative: every syntactic import is followed,
including imports in conditional branches and function bodies.  It records a
reviewable payload partition; it does not prune the historical vendor tree.
"""

from __future__ import annotations

import argparse
import ast
from collections import deque
from pathlib import Path

from release_utils import read_json, write_json
from vendor_lock import check_lock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/lib/pydevices"
INVENTORY = ROOT / "vendor/legacy-pydevices.imports.json"

# These directories are placed directly on sys.path by LegacyPlatform.  Their
# children are therefore imported as ``spibus`` or ``displaybuf``, not as
# ``bus_drv.spibus`` or ``add_ons.displaybuf``.
FLAT_SEARCH_DIRS = ("bus_drv", "display_drv", "touch_drv", "add_ons")

# The pinned MicroPython profile provides these names before filesystem lookup.
# Files with the same names remain in the historical source snapshot but are not
# reachable through an unqualified import on that profile.
BUILTIN_PRECEDENCE = ("framebuf", "micropython")

CATEGORY_CONFIG = (
    (
        "core_startup_ide",
        ("src/lib/tartlabutils/platform.py",),
        ("hdwconfig",),
        "Core platform and IDE display dependencies; hardware loading stops at "
        "the explicit hdwconfig boundary.",
    ),
    (
        "t_display_s3_pro_adapter",
        ("src/hdwconfig.py", "src/configs/t_display_s3_pro.py"),
        (),
        "Default legacy board adapter and its conservative driver dependencies.",
    ),
    (
        "shipped_examples",
        tuple(
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / "src/files/help-legacy").glob("*.py"))
        ),
        ("hdwconfig",),
        "Vendor dependencies imported by shipped legacy student examples, "
        "excluding the separately inventoried hardware boundary.",
    ),
)


def _module_name(relative: Path, strip_prefix: bool = False) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if strip_prefix:
        parts.pop(0)
    return ".".join(parts)


def module_indexes(source: Path = SOURCE) -> tuple[dict[str, Path], dict[str, Path]]:
    """Return vendor and TartLab-local import-name indexes."""
    vendor = {}
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        canonical = _module_name(relative)
        if canonical:
            vendor[canonical] = path
        if relative.parts[0] in FLAT_SEARCH_DIRS:
            flat = _module_name(relative, strip_prefix=True)
            if flat:
                vendor[flat] = path

    local = {"hdwconfig": ROOT / "src/hdwconfig.py"}
    for path in sorted((ROOT / "src/configs").glob("*.py")):
        local[path.stem] = path
    return vendor, local


def _package_name(module: str, path: Path) -> str:
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def imported_modules(path: Path, module: str) -> list[str]:
    """Extract absolute import targets, including importable from-list items."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    package = _package_name(module, path)
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            package_parts = package.split(".") if package else []
            keep = len(package_parts) - node.level + 1
            if keep < 0:
                continue
            base_parts = package_parts[:keep]
            if node.module:
                base_parts.extend(node.module.split("."))
            base = ".".join(part for part in base_parts if part)
        else:
            base = node.module or ""
        if base:
            result.append(base)
        for alias in node.names:
            if alias.name != "*":
                result.append(".".join(part for part in (base, alias.name) if part))
    return result


def _resolved_files(module: str, index: dict[str, Path]) -> list[tuple[str, Path]]:
    """Resolve a module and package initializers loaded on the way to it."""
    result = []
    parts = module.split(".")
    for count in range(1, len(parts) + 1):
        name = ".".join(parts[:count])
        path = index.get(name)
        if path is not None and (count == len(parts) or path.name == "__init__.py"):
            result.append((name, path))
    return result


def category_reachability(
        roots: tuple[str, ...], stop_modules: tuple[str, ...],
        vendor: dict[str, Path], local: dict[str, Path],
) -> set[str]:
    """Return vendor paths conservatively reachable from one root category."""
    queue = deque()
    for relative in roots:
        path = ROOT / relative
        queue.append((path.stem, path, False))

    visited = set()
    reachable = set()
    while queue:
        module, path, is_vendor = queue.popleft()
        key = (module, path.resolve())
        if key in visited:
            continue
        visited.add(key)
        if is_vendor:
            reachable.add(path.relative_to(SOURCE).as_posix())

        for imported in imported_modules(path, module):
            if any(
                    imported == stopped or imported.startswith(stopped + ".")
                    for stopped in stop_modules):
                continue
            top_level = imported.partition(".")[0]
            if top_level in BUILTIN_PRECEDENCE:
                continue
            resolved_vendor = _resolved_files(imported, vendor)
            if resolved_vendor:
                for name, dependency in resolved_vendor:
                    queue.append((name, dependency, True))
                continue
            dependency = local.get(imported)
            if dependency is not None:
                queue.append((imported, dependency, False))
    return reachable


def _summary(paths: set[str], locked: dict[str, dict[str, object]]) -> dict[str, int]:
    return {
        "files": len(paths),
        "python_files": sum(path.endswith(".py") for path in paths),
        "expanded_source_bytes": sum(int(locked[path]["size"]) for path in paths),
    }


def make_inventory(lock: dict[str, object] | None = None) -> dict[str, object]:
    lock = lock or check_lock()
    locked = {str(item["path"]): item for item in lock["files"]}
    all_files = set(locked)
    vendor, local = module_indexes()

    assigned = set()
    categories = {}
    for name, roots, stops, description in CATEGORY_CONFIG:
        raw = category_reachability(roots, stops, vendor, local)
        files = raw - assigned
        assigned.update(files)
        categories[name] = {
            "description": description,
            "roots": list(roots),
            "stop_modules": list(stops),
            "files": sorted(files),
            "summary": _summary(files, locked),
        }

    retained = all_files - assigned
    return {
        "schema": 1,
        "profile": "legacy-mp123",
        "analysis": {
            "kind": "conservative-static-import-reachability",
            "builtin_module_precedence": list(BUILTIN_PRECEDENCE),
            "flat_runtime_search_directories": list(FLAT_SEARCH_DIRS),
            "category_precedence": [item[0] for item in CATEGORY_CONFIG],
            "limitations": [
                "Imports in all conditional branches and function bodies count as reachable.",
                "Imports assembled dynamically from runtime strings require an explicit root.",
                "Non-Python resource use is not inferred by the import analysis.",
                "Category file lists are exclusive; shared dependencies belong to the first category.",
                "Unreachable files remain explicitly retained until a later reviewed pruning change.",
            ],
        },
        "vendor_source_identifier": lock["identifier"],
        "categories": categories,
        "retained_unreachable_files": sorted(retained),
        "summary": {
            "source_payload": _summary(all_files, locked),
            "statically_reachable": _summary(assigned, locked),
            "retained_unreachable": _summary(retained, locked),
        },
    }


def payload_paths(inventory: dict[str, object]) -> set[str]:
    result = set(inventory["retained_unreachable_files"])
    for category in inventory["categories"].values():
        overlap = result.intersection(category["files"])
        if overlap:
            raise ValueError("PyDevices inventory categories overlap: %s" % sorted(overlap))
        result.update(category["files"])
    return result


def distribution_paths(dist: Path) -> set[str]:
    root = dist.resolve() / "lib/pydevices"
    if not root.is_dir():
        raise FileNotFoundError("Distribution PyDevices directory is missing: %s" % root)
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix.lower() not in (".pyc", ".pyo")
    }


def _set_difference_message(expected: set[str], actual: set[str]) -> str:
    return "missing=%s unexpected=%s" % (
        sorted(expected - actual), sorted(actual - expected))


def check_inventory(
        expected: dict[str, object] | None = None, dist: Path | None = None,
) -> dict[str, object]:
    lock = check_lock()
    expected = expected or read_json(INVENTORY)
    actual = make_inventory(lock)
    if actual != expected:
        expected_paths = payload_paths(expected)
        actual_paths = payload_paths(actual)
        detail = _set_difference_message(expected_paths, actual_paths)
        if expected_paths == actual_paths:
            detail = "roots, reachability categories, summaries, or analysis settings changed"
        raise ValueError(
            "PyDevices import inventory differs from the reviewed allowlist; "
            "review the dependency change and regenerate explicitly (%s)" % detail)

    locked_paths = {str(item["path"]) for item in lock["files"]}
    allowed_paths = payload_paths(actual)
    if allowed_paths != locked_paths:
        raise ValueError(
            "PyDevices allowlist does not partition the vendor content lock: %s" %
            _set_difference_message(locked_paths, allowed_paths))
    if dist is not None:
        built_paths = distribution_paths(dist)
        if built_paths != allowed_paths:
            raise ValueError(
                "Generated PyDevices distribution differs from the reviewed allowlist: %s" %
                _set_difference_message(allowed_paths, built_paths))
    return actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true",
        help="replace the inventory after explicitly reviewing dependency changes")
    parser.add_argument(
        "--dist", type=Path,
        help="also require a generated distribution to match the payload allowlist")
    args = parser.parse_args()
    if args.write:
        value = make_inventory()
        write_json(INVENTORY, value)
        if args.dist is not None:
            check_inventory(expected=value, dist=args.dist)
        print("Wrote %s (%s reachable, %s retained)" % (
            INVENTORY.relative_to(ROOT),
            value["summary"]["statically_reachable"]["files"],
            value["summary"]["retained_unreachable"]["files"],
        ))
    else:
        value = check_inventory(dist=args.dist)
        suffix = " and %s" % args.dist if args.dist is not None else ""
        print("Verified %s%s" % (INVENTORY.relative_to(ROOT), suffix))
        print("Reachable: %(files)s files / %(expanded_source_bytes)s bytes" %
              value["summary"]["statically_reachable"])


if __name__ == "__main__":
    main()
