"""Small recovery-only OTA client with no dependency on TartLab or vendor modules."""

import os
import time

import uhashlib
import ujson
import urequests


STATE_DIR = "/state"
STATE_REPOS = STATE_DIR + "/repos.json"
LEGACY_REPOS = "/repos.json"
UPDATE_STATE = STATE_DIR + "/update.json"
TEMP_DIR = "/tmp/recovery"
FILESYSTEM_RESERVE_BYTES = 10000
PHASE1_MIGRATION_FILE = STATE_DIR + "/phase1_migration.json"
PROTECTED = (
    "/app.py", "/hdwconfig.py", "/settings.json", "/repos.json", "/logs",
    "/device", "/state", "/files/user",
)


def _kind(path):
    try:
        return 1 if os.stat(path)[0] & 0x8000 else 2
    except OSError:
        return 0


def _mkdirs(path):
    current = ""
    for part in path.strip("/").split("/"):
        if part:
            current += "/" + part
            if _kind(current) == 0:
                os.mkdir(current)


def _remove_tree(path):
    if _kind(path) == 2:
        for name in os.listdir(path):
            _remove_tree(path.rstrip("/") + "/" + name)
        os.rmdir(path)
    elif _kind(path) == 1:
        os.remove(path)


def _read_json(path, default):
    try:
        with open(path, "r") as stream:
            return ujson.load(stream)
    except Exception:
        return default


def _write_json(path, value):
    _mkdirs(path.rsplit("/", 1)[0])
    temporary = path + ".tmp"
    with open(temporary, "w") as stream:
        ujson.dump(value, stream)
    if _kind(path) == 1:
        os.remove(path)
    os.rename(temporary, path)


def _protected(path):
    path = "/" + path.strip("/")
    return any(path == item or path.startswith(item + "/") for item in PROTECTED)


def _target_path(target, member):
    member = member.replace("\\", "/")
    parts = member.split("/")
    if member.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Unsafe archive path")
    base = "/" + target.strip("/")
    path = ("" if base == "/" else base) + "/" + member
    if _protected(path):
        raise ValueError("Archive targets protected state")
    return path


def _tar_members(filename, target, extract=False):
    paths = []
    with open(filename, "rb") as stream:
        while True:
            header = stream.read(512)
            if not header or header == b"\0" * 512:
                break
            if len(header) != 512:
                raise ValueError("Truncated tar header")
            name = header[0:100].split(b"\0", 1)[0].decode("utf-8")
            prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8")
            if prefix:
                name = prefix + "/" + name
            size_text = header[124:135].split(b"\0", 1)[0].strip() or b"0"
            size = int(size_text, 8)
            type_flag = header[156:157]
            path = _target_path(target, name.rstrip("/"))
            paths.append(path)
            preserve_boot = path == "/boot.py" and _kind(PHASE1_MIGRATION_FILE) == 1
            if extract and not preserve_boot and type_flag in (b"", b"0", b"\0"):
                _mkdirs(path.rsplit("/", 1)[0])
                remaining = size
                with open(path, "wb") as output:
                    while remaining:
                        chunk = stream.read(min(1024, remaining))
                        if not chunk:
                            raise ValueError("Truncated tar member")
                        output.write(chunk)
                        remaining -= len(chunk)
            else:
                remaining = size
                while remaining:
                    chunk = stream.read(min(1024, remaining))
                    if not chunk:
                        raise ValueError("Truncated tar member")
                    remaining -= len(chunk)
            padding = (512 - size % 512) % 512
            if padding and len(stream.read(padding)) != padding:
                raise ValueError("Truncated tar padding")
    return paths


def _sha256(path):
    digest = uhashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break
            digest.update(chunk)
    return "".join("{:02x}".format(byte) for byte in digest.digest())


def _download(url, path):
    response = None
    try:
        response = urequests.get(url, headers={"User-Agent": "TartLab-Recovery"})
        if response.status_code != 200:
            raise OSError("HTTP status %s" % response.status_code)
        with open(path, "wb") as output:
            while True:
                chunk = response.raw.read(1024)
                if not chunk:
                    break
                output.write(chunk)
    finally:
        if response is not None:
            response.close()


def _download_verified(url, path, expected_sha256=None):
    if expected_sha256 and _kind(path) == 1 and _sha256(path) == expected_sha256:
        return False
    partial = path + ".part"
    if _kind(partial) == 1:
        os.remove(partial)
    try:
        _download(url, partial)
        if expected_sha256 and _sha256(partial) != expected_sha256:
            raise ValueError("Package hash mismatch")
        if _kind(path) == 1:
            os.remove(path)
        os.rename(partial, path)
        return True
    except Exception:
        if _kind(partial) == 1:
            os.remove(partial)
        raise


def _release(repo):
    response = None
    try:
        url = "https://api.github.com/repos/%s/releases" % repo["repo"]
        response = urequests.get(url, headers={"User-Agent": "TartLab-Recovery"})
        if response.status_code != 200:
            raise OSError("Release lookup failed")
        for release in response.json():
            if not release.get("prerelease", False):
                return release
        raise ValueError("No stable release found")
    finally:
        if response is not None:
            response.close()


def _validate_manifest(manifest):
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Empty manifest")
    for package in manifest:
        for key in ("file_name", "sha256", "target", "clear_first"):
            if key not in package:
                raise ValueError("Invalid manifest")
        if _protected(package["target"]):
            raise ValueError("Manifest targets protected state")
        if package["target"].rstrip("/") == "/recovery" and package["clear_first"]:
            raise ValueError("Recovery cannot clear itself")


def _free_space():
    stats = os.statvfs("/")
    return stats[1] * stats[3]


def _required_install_space(manifest):
    required = FILESYSTEM_RESERVE_BYTES
    for package in manifest:
        expanded = package.get("expanded_size")
        if expanded is None:
            expanded = os.stat(TEMP_DIR + "/" + package["file_name"])[6]
        if not isinstance(expanded, int) or expanded < 0:
            raise ValueError("Invalid expanded package size")
        required += expanded
    return required


def _tartlab_repo(repos):
    for item in repos.get("list", []):
        if item.get("name") == "TartLab":
            return item
    return None


def _install_verified_packages(tartlab, version, manifest, progress):
    marker = _read_json(UPDATE_STATE, None)
    resume = isinstance(marker, dict) and marker.get("source") == "recovery" and \
        marker.get("status") == "installing"
    if resume:
        pending = marker.get("repos", [])
        resume = bool(pending) and pending[0].get("name") == "TartLab" and \
            pending[0].get("pending_version") == version
    if not resume:
        marker = {
            "schema": 1,
            "status": "installing",
            "repos": [{
                "name": "TartLab",
                "previous_version": tartlab["installed_version"],
                "pending_version": version,
            }],
            "source": "recovery",
            "completed_packages": [],
        }
    completed = marker.get("completed_packages", [])
    marker["completed_packages"] = completed
    _write_json(UPDATE_STATE, marker)
    try:
        packages = [item for item in manifest if item["target"].rstrip("/") != "/recovery"]
        packages.sort(key=lambda item: item["file_name"] == "tartlabutils.tar")
        for package in packages:
            filename = package["file_name"]
            if filename in completed:
                progress("Already installed " + filename)
                continue
            target = package["target"]
            progress("Installing " + filename)
            if package["clear_first"] and _kind(target) != 0:
                _remove_tree(target)
                _mkdirs(target)
            _tar_members(TEMP_DIR + "/" + filename, target, True)
            completed.append(filename)
            _write_json(UPDATE_STATE, marker)
        marker["status"] = "pending_health"
        _write_json(UPDATE_STATE, marker)
        _remove_tree(TEMP_DIR)
        return version
    except Exception as error:
        marker["status"] = "failed"
        marker["error"] = str(error)[:160]
        _write_json(UPDATE_STATE, marker)
        raise


def resume_staged_update(progress=print):
    marker = _read_json(UPDATE_STATE, None)
    if not isinstance(marker, dict) or marker.get("source") != "recovery" or \
            marker.get("status") != "installing":
        raise ValueError("No interrupted staged recovery update")
    pending = marker.get("repos", [])
    if not pending or pending[0].get("name") != "TartLab":
        raise ValueError("Invalid staged recovery marker")
    version = pending[0].get("pending_version")
    repos_path = STATE_REPOS if _kind(STATE_REPOS) == 1 else LEGACY_REPOS
    repos = _read_json(repos_path, {})
    tartlab = _tartlab_repo(repos)
    if tartlab is None:
        raise ValueError("TartLab release state not found")
    manifest = _read_json(TEMP_DIR + "/manifest.json", None)
    _validate_manifest(manifest)
    for package in manifest:
        path = TEMP_DIR + "/" + package["file_name"]
        if _kind(path) != 1 or _sha256(path) != package["sha256"]:
            raise ValueError("Staged package hash mismatch")
        _tar_members(path, package["target"], False)
    if _required_install_space(manifest) > _free_space():
        raise OSError("Not enough disk space to extract release safely")
    return _install_verified_packages(tartlab, version, manifest, progress)


def update_to_latest(progress=print):
    repos_path = STATE_REPOS if _kind(STATE_REPOS) == 1 else LEGACY_REPOS
    repos = _read_json(repos_path, {})
    tartlab = _tartlab_repo(repos)
    if tartlab is None:
        raise ValueError("TartLab release state not found")
    release = _release(tartlab)
    version = release["tag_name"]
    assets = {item["name"]: item for item in release["assets"]}
    manifest_asset = assets.get("manifest.json")
    if manifest_asset is None:
        raise ValueError("Release manifest not found")

    if _kind(TEMP_DIR) == 0:
        _mkdirs(TEMP_DIR)
    progress("Downloading recovery manifest")
    manifest_path = TEMP_DIR + "/manifest.json"
    _download_verified(manifest_asset["browser_download_url"], manifest_path)
    manifest = _read_json(manifest_path, None)
    _validate_manifest(manifest)
    for package in manifest:
        asset = assets.get(package["file_name"])
        if asset is None:
            raise ValueError("Missing package asset")
        path = TEMP_DIR + "/" + package["file_name"]
        if _kind(path) == 1 and _sha256(path) == package["sha256"]:
            progress("Reusing " + package["file_name"])
        else:
            progress("Downloading " + package["file_name"])
            _download_verified(asset["browser_download_url"], path, package["sha256"])
        _tar_members(path, package["target"], False)

    if _required_install_space(manifest) > _free_space():
        raise OSError("Not enough disk space to extract release safely")

    return _install_verified_packages(tartlab, version, manifest, progress)
