import os
import ujson


STATE_DIR = "/state"
DEVICE_DIR = "/device"
SETTINGS_FILE = STATE_DIR + "/settings.json"
REPOS_FILE = STATE_DIR + "/repos.json"
LOG_DIR = STATE_DIR + "/logs"
SELECTED_APP_FILE = STATE_DIR + "/selected_app.json"
UPDATE_STATE_FILE = STATE_DIR + "/update.json"
BOOT_STATE_FILE = STATE_DIR + "/boot.json"
DEVICE_CONFIG_FILE = DEVICE_DIR + "/hdwconfig.py"
PHASE1_MIGRATION_FILE = STATE_DIR + "/phase1_migration.json"
PHASE1_TRANSITION_FILE = "/defaults/phase1_transition.json"

LEGACY_SETTINGS_FILE = "/settings.json"
LEGACY_REPOS_FILE = "/repos.json"
LEGACY_LOG_DIR = "/logs"
LEGACY_APP_FILE = "/app.py"
LEGACY_DEVICE_CONFIG_FILE = "/hdwconfig.py"
DEFAULT_DEVICE_CONFIG_FILE = "/defaults/hdwconfig.py"


def path_kind(path):
    try:
        mode = os.stat(path)[0]
        if mode & 0x8000:
            return 1
        return 2
    except OSError:
        return 0


def ensure_dir(path):
    normalized = path.replace("\\", "/")
    current = ""
    if len(normalized) > 2 and normalized[1] == ":":
        current = normalized[:2]
        normalized = normalized[2:]
    for part in normalized.strip("/").split("/"):
        if not part:
            continue
        current += "/" + part
        if path_kind(current) == 0:
            os.mkdir(current)


def copy_file(source, destination):
    parent = destination.rsplit("/", 1)[0]
    ensure_dir(parent)
    with open(source, "rb") as src:
        with open(destination, "wb") as dst:
            while True:
                chunk = src.read(1024)
                if not chunk:
                    break
                dst.write(chunk)


def read_json(path, default=None):
    try:
        with open(path, "r") as stream:
            return ujson.load(stream)
    except (OSError, ValueError):
        return default


def write_json(path, value):
    """Replace a state file while retaining the prior copy until rename succeeds."""
    parent = path.rsplit("/", 1)[0]
    ensure_dir(parent)
    temporary = path + ".tmp"
    backup = path + ".bak"
    for stale in (temporary, backup):
        if path_kind(stale) == 1:
            os.remove(stale)
    with open(temporary, "w") as stream:
        ujson.dump(value, stream)
    had_original = path_kind(path) == 1
    if had_original:
        os.rename(path, backup)
    try:
        os.rename(temporary, path)
    except Exception:
        if had_original and path_kind(backup) == 1:
            os.rename(backup, path)
        raise
    if path_kind(backup) == 1:
        os.remove(backup)


def _copy_logs_once():
    if path_kind(LEGACY_LOG_DIR) != 2 or path_kind(LOG_DIR) == 2:
        return
    ensure_dir(LOG_DIR)
    for name in os.listdir(LEGACY_LOG_DIR):
        source = LEGACY_LOG_DIR + "/" + name
        if path_kind(source) == 1:
            copy_file(source, LOG_DIR + "/" + name)


def _legacy_selected_app():
    try:
        with open(LEGACY_APP_FILE, "r") as stream:
            lines = stream.readlines()
        if len(lines) >= 2 and lines[1].startswith("# "):
            return validate_selected_app(lines[1][2:].strip())
    except (OSError, ValueError):
        pass
    return "hello.py"


def ensure_layout():
    """Migrate legacy root state only when the protected destination is absent."""
    ensure_dir(STATE_DIR)
    ensure_dir(DEVICE_DIR)

    if path_kind(SETTINGS_FILE) == 0 and path_kind(LEGACY_SETTINGS_FILE) == 1:
        copy_file(LEGACY_SETTINGS_FILE, SETTINGS_FILE)
    if path_kind(REPOS_FILE) == 0 and path_kind(LEGACY_REPOS_FILE) == 1:
        copy_file(LEGACY_REPOS_FILE, REPOS_FILE)
    _copy_logs_once()

    if path_kind(SELECTED_APP_FILE) == 0:
        save_selected_app(_legacy_selected_app())

    if path_kind(DEVICE_CONFIG_FILE) == 0:
        source = LEGACY_DEVICE_CONFIG_FILE
        if path_kind(source) != 1:
            source = DEFAULT_DEVICE_CONFIG_FILE
        if path_kind(source) == 1:
            copy_file(source, DEVICE_CONFIG_FILE)
    _migrate_legacy_version_commit()


def _migrate_legacy_version_commit():
    """Undo the legacy updater's pre-health version commit exactly once."""
    if path_kind(PHASE1_MIGRATION_FILE) == 1:
        return
    transition = read_json(PHASE1_TRANSITION_FILE, None)
    repos = read_json(REPOS_FILE, None)
    marker = get_update_state()
    result = {"schema": 1, "applied": False}
    if isinstance(transition, dict) and isinstance(repos, dict) and marker is None:
        previous = transition.get("legacy_installed_versions", {})
        pending = []
        for repo in repos.get("list", []):
            name = repo.get("name")
            old_version = previous.get(name)
            current_version = repo.get("installed_version")
            if old_version and current_version and current_version != old_version:
                pending.append({
                    "name": name,
                    "previous_version": old_version,
                    "pending_version": current_version,
                })
                repo["installed_version"] = old_version
        if pending:
            write_json(REPOS_FILE, repos)
            write_json(UPDATE_STATE_FILE, {
                "schema": 1,
                "status": "pending_health",
                "repos": pending,
                "transition": "legacy_phase1",
            })
            result["applied"] = True
    write_json(PHASE1_MIGRATION_FILE, result)


def validate_selected_app(filename):
    if not isinstance(filename, str):
        raise ValueError("Selected app must be a string")
    filename = filename.replace("\\", "/")
    if filename.startswith("/"):
        raise ValueError("Selected app must be relative to the user folder")
    filename = filename.strip("/")
    if not filename.endswith(".py"):
        raise ValueError("Selected app must be a Python file")
    parts = filename.split("/")
    if not filename or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid selected app path")
    for part in parts:
        stem = part[:-3] if part == parts[-1] else part
        if not _is_importable_name(stem):
            raise ValueError("App names: letters, digits, _ only.")
    return filename


def _is_importable_name(value):
    """Use the identifier subset supported by the legacy MicroPython profile."""
    if not value:
        return False
    for character in value:
        if not ("a" <= character <= "z" or "A" <= character <= "Z" or
                "0" <= character <= "9" or character == "_"):
            return False
    return True


def get_selected_app():
    data = read_json(SELECTED_APP_FILE, {})
    try:
        return validate_selected_app(data.get("filename", "hello.py"))
    except (AttributeError, ValueError):
        return "hello.py"


def save_selected_app(filename):
    filename = validate_selected_app(filename)
    write_json(SELECTED_APP_FILE, {"schema": 1, "filename": filename})


def get_update_state():
    return read_json(UPDATE_STATE_FILE, None)


def begin_update(repo_name, previous_version, pending_version):
    marker = get_update_state()
    if not isinstance(marker, dict):
        marker = {"schema": 1, "status": "installing", "repos": []}
    repos = marker.get("repos", [])
    repos = [item for item in repos if item.get("name") != repo_name]
    repos.append({
        "name": repo_name,
        "previous_version": previous_version,
        "pending_version": pending_version,
    })
    marker["repos"] = repos
    marker["status"] = "installing"
    marker.pop("error", None)
    write_json(UPDATE_STATE_FILE, marker)


def set_update_pending_health():
    marker = get_update_state()
    if isinstance(marker, dict):
        marker["status"] = "pending_health"
        write_json(UPDATE_STATE_FILE, marker)


def set_update_failed(message):
    marker = get_update_state()
    if not isinstance(marker, dict):
        marker = {"schema": 1, "repos": []}
    marker["status"] = "failed"
    marker["error"] = str(message)[:160]
    write_json(UPDATE_STATE_FILE, marker)


def commit_pending_update():
    marker = get_update_state()
    if not isinstance(marker, dict) or marker.get("status") != "pending_health":
        return False
    repos = read_json(REPOS_FILE, None)
    if not isinstance(repos, dict):
        raise ValueError("Cannot commit update without valid release state")
    pending = {}
    for item in marker.get("repos", []):
        pending[item.get("name")] = item.get("pending_version")
    for repo in repos.get("list", []):
        if repo.get("name") in pending:
            repo["installed_version"] = pending[repo["name"]]
    write_json(REPOS_FILE, repos)
    os.remove(UPDATE_STATE_FILE)
    return True
