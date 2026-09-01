"""Load and validate TartLab's host-side modern board catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BOARDS_ROOT = ROOT / "boards"
SCHEMA = 1
SUPPORT_STATUSES = frozenset({"bringup", "candidate", "qualified", "retired"})
ORIENTATIONS = frozenset({"portrait", "landscape", "square"})
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_MODULE = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_TOP_LEVEL_KEYS = {
    "schema", "id", "name", "vendor", "runtime_profile", "support_status",
    "hardware", "selector", "runtime", "firmware", "qualification",
    "documentation",
}
_HARDWARE_KEYS = {
    "revisions", "mcu", "flash_size_bytes", "psram_size_bytes", "display",
    "touch", "console", "power",
}
_DISPLAY_KEYS = {
    "width", "height", "orientation", "transport", "controller",
}
_TOUCH_KEYS = {"present", "controller"}
_SELECTOR_KEYS = {"module", "source", "protected_path"}
_RUNTIME_KEYS = {"source", "target"}
_FIRMWARE_KEYS = {
    "artifact", "sha256", "image_format", "flash_offset", "lock",
    "provenance",
}
_QUALIFICATION_KEYS = {"release_version", "evidence"}


class BoardCatalogError(ValueError):
    """Raised when a board descriptor violates the catalog contract."""


def _object(value: Any, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BoardCatalogError("%s must be an object" % label)
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise BoardCatalogError(
            "%s keys differ (missing=%s, extra=%s)" % (label, missing, extra))
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoardCatalogError("%s must be a non-empty string" % label)
    return value


def _relative_file(root: Path, value: Any, label: str) -> Path:
    relative = Path(_text(value, label))
    if relative.is_absolute() or ".." in relative.parts:
        raise BoardCatalogError("%s must be a repository-relative path" % label)
    path = (root / relative).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise BoardCatalogError("%s does not name a repository file: %s" % (label, relative))
    return path


def _relative_directory(root: Path, value: Any, label: str) -> Path:
    relative = Path(_text(value, label))
    if relative.is_absolute() or ".." in relative.parts:
        raise BoardCatalogError("%s must be a repository-relative path" % label)
    path = (root / relative).resolve()
    if root.resolve() not in path.parents or not path.is_dir():
        raise BoardCatalogError(
            "%s does not name a repository directory: %s" % (label, relative))
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_descriptor(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardCatalogError("%s: %s" % (path, exc)) from exc
    if not isinstance(value, dict):
        raise BoardCatalogError("%s: descriptor must be an object" % path)
    return value


def validate_descriptor(descriptor: dict[str, Any], *, root: Path = ROOT,
                        descriptor_path: Path | None = None) -> dict[str, Any]:
    descriptor = _object(descriptor, "board descriptor", _TOP_LEVEL_KEYS)
    if descriptor["schema"] != SCHEMA:
        raise BoardCatalogError("unsupported board descriptor schema")

    board_id = _text(descriptor["id"], "id")
    if not _ID.fullmatch(board_id):
        raise BoardCatalogError("id must match %s" % _ID.pattern)
    if descriptor_path is not None and descriptor_path.parent.name != board_id:
        raise BoardCatalogError("descriptor id must match its directory name")
    for field in ("name", "vendor", "runtime_profile"):
        _text(descriptor[field], field)

    status = descriptor["support_status"]
    if status not in SUPPORT_STATUSES:
        raise BoardCatalogError("unknown support_status: %s" % status)

    hardware = _object(descriptor["hardware"], "hardware", _HARDWARE_KEYS)
    revisions = hardware["revisions"]
    if not isinstance(revisions, list) or not revisions:
        raise BoardCatalogError("hardware.revisions must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in revisions):
        raise BoardCatalogError("hardware.revisions entries must be non-empty strings")
    _text(hardware["mcu"], "hardware.mcu")
    for field in ("flash_size_bytes", "psram_size_bytes"):
        if not isinstance(hardware[field], int) or hardware[field] < 0:
            raise BoardCatalogError("hardware.%s must be a non-negative integer" % field)
    for field in ("console", "power"):
        _text(hardware[field], "hardware.%s" % field)

    display = _object(hardware["display"], "hardware.display", _DISPLAY_KEYS)
    for field in ("width", "height"):
        if not isinstance(display[field], int) or display[field] <= 0:
            raise BoardCatalogError("hardware.display.%s must be positive" % field)
    if display["orientation"] not in ORIENTATIONS:
        raise BoardCatalogError("unknown display orientation")
    for field in ("transport", "controller"):
        _text(display[field], "hardware.display.%s" % field)

    touch = _object(hardware["touch"], "hardware.touch", _TOUCH_KEYS)
    if not isinstance(touch["present"], bool):
        raise BoardCatalogError("hardware.touch.present must be boolean")
    if touch["present"]:
        _text(touch["controller"], "hardware.touch.controller")
    elif touch["controller"] is not None:
        raise BoardCatalogError("a board without touch must use a null controller")

    runtime = descriptor["runtime"]
    if runtime is not None:
        runtime = _object(runtime, "runtime", _RUNTIME_KEYS)
        runtime_path = _relative_directory(root, runtime["source"], "runtime.source")
        if runtime["target"] != "/board/" + board_id:
            raise BoardCatalogError(
                "runtime.target must be /board/<board-id>")
    else:
        runtime_path = None

    selector = descriptor["selector"]
    if selector is not None:
        selector = _object(selector, "selector", _SELECTOR_KEYS)
        module = _text(selector["module"], "selector.module")
        if not _MODULE.fullmatch(module):
            raise BoardCatalogError("selector.module must be a simple Python module")
        selector_path = _relative_file(root, selector["source"], "selector.source")
        if selector_path.stem != module:
            raise BoardCatalogError("selector source name must match selector.module")
        if runtime_path is None or runtime_path not in selector_path.parents:
            raise BoardCatalogError("selector source must belong to the board runtime")
        if selector["protected_path"] != "/device/hdwconfig.py":
            raise BoardCatalogError("selector.protected_path must be /device/hdwconfig.py")

    firmware = descriptor["firmware"]
    if firmware is not None:
        firmware = _object(firmware, "firmware", _FIRMWARE_KEYS)
        artifact = _relative_file(root, firmware["artifact"], "firmware.artifact")
        expected_hash = firmware["sha256"]
        if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
            raise BoardCatalogError("firmware.sha256 must be lowercase SHA-256")
        if _sha256(artifact) != expected_hash:
            raise BoardCatalogError("firmware artifact SHA-256 does not match")
        _text(firmware["image_format"], "firmware.image_format")
        if not isinstance(firmware["flash_offset"], str) or not re.fullmatch(
                r"0x[0-9a-fA-F]+", firmware["flash_offset"]):
            raise BoardCatalogError("firmware.flash_offset must be hexadecimal")
        _relative_file(root, firmware["lock"], "firmware.lock")
        _relative_file(root, firmware["provenance"], "firmware.provenance")

    qualification = descriptor["qualification"]
    if qualification is not None:
        qualification = _object(
            qualification, "qualification", _QUALIFICATION_KEYS)
        _text(qualification["release_version"], "qualification.release_version")
        _relative_file(root, qualification["evidence"], "qualification.evidence")

    documentation = descriptor["documentation"]
    if not isinstance(documentation, list) or not documentation:
        raise BoardCatalogError("documentation must be a non-empty list")
    for index, path in enumerate(documentation):
        _relative_file(root, path, "documentation[%d]" % index)

    if status in ("candidate", "qualified") and (
            selector is None or runtime is None):
        raise BoardCatalogError("%s boards require a selector and runtime" % status)
    if status in ("candidate", "qualified") and firmware is None:
        raise BoardCatalogError("%s boards require firmware" % status)
    if status == "qualified" and qualification is None:
        raise BoardCatalogError("qualified boards require qualification evidence")
    if status in ("bringup", "candidate") and qualification is not None:
        raise BoardCatalogError("%s boards cannot claim qualification" % status)
    return descriptor


def descriptor_paths(boards_root: Path = BOARDS_ROOT) -> Iterable[Path]:
    return sorted(boards_root.glob("*/board.json"))


def load_catalog(*, root: Path = ROOT,
                 boards_root: Path | None = None) -> dict[str, dict[str, Any]]:
    if boards_root is None:
        boards_root = root / "boards"
    catalog: dict[str, dict[str, Any]] = {}
    selector_modules: dict[str, str] = {}
    for path in descriptor_paths(boards_root):
        descriptor = validate_descriptor(
            load_descriptor(path), root=root, descriptor_path=path)
        board_id = descriptor["id"]
        if board_id in catalog:
            raise BoardCatalogError("duplicate board id: %s" % board_id)
        selector = descriptor["selector"]
        if selector is not None:
            module = selector["module"]
            if module in selector_modules:
                raise BoardCatalogError(
                    "selector %s is shared by %s and %s" %
                    (module, selector_modules[module], board_id))
            selector_modules[module] = board_id
        catalog[board_id] = descriptor
    if not catalog:
        raise BoardCatalogError("board catalog is empty")
    return catalog


def select_board(board_id: str, *, required_status: str | None = None,
                 root: Path = ROOT) -> dict[str, Any]:
    catalog = load_catalog(root=root)
    try:
        descriptor = catalog[board_id]
    except KeyError as exc:
        raise BoardCatalogError("unknown board id: %s" % board_id) from exc
    if required_status is not None and descriptor["support_status"] != required_status:
        raise BoardCatalogError(
            "board %s is %s, not %s" %
            (board_id, descriptor["support_status"], required_status))
    return descriptor


def default_board(runtime_profile: str, *, root: Path = ROOT) -> dict[str, Any]:
    """Return the qualified default board named by a runtime profile."""
    profile_path = root / "profiles" / (runtime_profile + ".json")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardCatalogError("%s: %s" % (profile_path, exc)) from exc
    if not isinstance(profile, dict):
        raise BoardCatalogError("runtime profile must be an object")
    board_id = profile.get("default_board_id")
    if not isinstance(board_id, str):
        raise BoardCatalogError(
            "runtime profile %s has no default_board_id" % runtime_profile)
    descriptor = select_board(board_id, required_status="qualified", root=root)
    if descriptor["runtime_profile"] != runtime_profile:
        raise BoardCatalogError("default board targets a different runtime profile")
    return descriptor


def selector_source(descriptor: dict[str, Any]) -> str:
    selector = descriptor.get("selector")
    if selector is None:
        raise BoardCatalogError("board has no selector")
    return (
        "# Generated by the authenticated TartLab adult provisioning tool.\n"
        "from %s import *\n" % selector["module"]
    )
