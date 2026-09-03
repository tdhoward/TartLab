import machine
import time
import uasyncio as asyncio
import uhashlib
import ujson
import uos
import urequests
from tarfile import TarFile

from .miscutils import file_exists, load_settings, log, log_exception, mkdirs, rmvdir, save_settings
from .state import REPOS_FILE, begin_update, set_update_failed, set_update_pending_health


TMP_UPDATE_FOLDER = "/tmp"
UPDATE_NONE = 0
UPDATE_INSTALLED = 1
UPDATE_FAILED = -1
updating_updater = False
FILESYSTEM_RESERVE_BYTES = 10000

PROTECTED_PATHS = (
    "/app.py", "/hdwconfig.py", "/settings.json", "/repos.json", "/logs",
    "/device", "/state", "/files/user",
)
PHASE1_MIGRATION_FILE = "/state/phase1_migration.json"
LEGACY_PROFILE = "legacy-mp123"
MODERN_PROFILE = "lvgl-modern"
LEGACY_REPOSITORY = "tdhoward/tartlab"
MODERN_REPOSITORY = "tdhoward/tartlab-modern-releases"
BOARD_IDENTITY_FILE = "/device/board.json"


def _is_protected(path):
    path = "/" + path.strip("/")
    for protected in PROTECTED_PATHS:
        if path == protected or path.startswith(protected + "/"):
            return True
    return False


def _target_path(target_folder, archive_name):
    archive_name = archive_name.replace("\\", "/")
    parts = archive_name.split("/")
    if archive_name.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Unsafe archive path: " + archive_name)
    target = "/" + target_folder.strip("/")
    if target == "/":
        target = ""
    path = target + "/" + archive_name
    if _is_protected(path):
        raise ValueError("Archive targets protected state: " + path)
    return path


def _protected_board_id():
    try:
        with open(BOARD_IDENTITY_FILE, "r") as stream:
            identity = ujson.load(stream)
    except OSError:
        return None
    board_id = identity.get("board_id") if isinstance(identity, dict) else None
    if not isinstance(board_id, str) or not board_id or \
            any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for character in board_id):
        raise ValueError("Protected board identity is invalid")
    return board_id


def _modern_board_identity(repo):
    firmware_sha256 = repo.get("firmware_sha256")
    board_id = repo.get("board_id")
    protected_board_id = _protected_board_id()
    if board_id is None and protected_board_id is not None:
        board_id = protected_board_id
    if board_id is None:
        raise ValueError("Modern release state has no board identity")
    if not isinstance(board_id, str) or not board_id or \
            any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for character in board_id):
        raise ValueError("Modern release state has an invalid board identity")
    if not isinstance(firmware_sha256, str) or len(firmware_sha256) != 64 or \
            any(character not in "0123456789abcdef"
                for character in firmware_sha256):
        raise ValueError("Modern release state has the wrong firmware identity")
    if protected_board_id is not None and board_id != protected_board_id:
        raise ValueError("Modern release state conflicts with protected board identity")
    return board_id, firmware_sha256


def release_contract(repo):
    """Return the manifest name and profile after enforcing feed isolation."""
    if repo.get("name") != "TartLab":
        manifest_name = repo.get("manifest", "manifest.json")
        if manifest_name != "manifest.json":
            raise ValueError("Non-TartLab repositories require manifest.json")
        return manifest_name, None

    profile = repo.get("runtime_profile", LEGACY_PROFILE)
    repository = repo.get("repo", "").lower()
    manifest_name = repo.get("manifest")
    if profile == MODERN_PROFILE:
        if repository != MODERN_REPOSITORY:
            raise ValueError("Modern profile requires the isolated modern feed")
        if manifest_name != "modern-manifest.json":
            raise ValueError("Modern profile requires modern-manifest.json")
        _modern_board_identity(repo)
        return manifest_name, profile
    if profile == LEGACY_PROFILE:
        if repository != LEGACY_REPOSITORY:
            raise ValueError("Legacy profile requires the legacy feed")
        if manifest_name not in (None, "manifest.json"):
            raise ValueError("Legacy profile requires manifest.json")
        return "manifest.json", profile
    raise ValueError("Unsupported TartLab runtime profile")


def manifest_packages(document, repo, version):
    manifest_name, profile = release_contract(repo)
    if profile == MODERN_PROFILE:
        if not isinstance(document, dict) or document.get("schema") != 1:
            raise ValueError("Invalid modern manifest schema")
        channel = document.get("channel", {})
        compatibility = document.get("compatibility", {})
        if document.get("version") != version:
            raise ValueError("Modern manifest version does not match release")
        if channel.get("repository", "").lower() != MODERN_REPOSITORY or \
                channel.get("manifest") != manifest_name:
            raise ValueError("Modern manifest targets the wrong release feed")
        if compatibility.get("runtime_profile") != MODERN_PROFILE:
            raise ValueError("Modern manifest targets the wrong runtime profile")
        board_id, firmware_sha256 = _modern_board_identity(repo)
        boards = compatibility.get("boards")
        if isinstance(boards, dict):
            board = boards.get(board_id, {})
            firmware = board.get("firmware", {})
        else:
            firmware = compatibility.get("firmware", {})
        if firmware.get("sha256") != firmware_sha256:
            raise ValueError("Modern manifest targets the wrong firmware identity")
        manifest = document.get("packages")
    else:
        manifest = document
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Manifest must contain at least one package")
    required = ("file_name", "sha256", "target", "clear_first")
    for package in manifest:
        if not isinstance(package, dict) or any(key not in package for key in required):
            raise ValueError("Invalid package manifest entry")
        target = "/" + package["target"].strip("/")
        if _is_protected(target):
            raise ValueError("Manifest targets protected state: " + target)
        if target == "/recovery" and package["clear_first"]:
            raise ValueError("Recovery package cannot be cleared in place")
        selection = package.get("selection")
        if selection is not None and (
                selection != "board-id-subtree" or target != "/board" or
                package["clear_first"] is not True):
            raise ValueError("Invalid package selection policy")
        if selection is not None and not isinstance(
                package.get("selected_expanded_sizes"), dict):
            raise ValueError("Selected package sizes are missing")
        if selection is not None:
            for board_id, expanded in package["selected_expanded_sizes"].items():
                if not isinstance(board_id, str) or not board_id or \
                        any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                            for character in board_id) or \
                        not isinstance(expanded, int) or expanded < 0:
                    raise ValueError("Selected package sizes are invalid")


def _package_member_prefix(package, repo):
    selection = package.get("selection")
    if selection is None:
        return None
    unused_manifest, profile = release_contract(repo)
    if profile != MODERN_PROFILE or selection != "board-id-subtree":
        raise ValueError("Package selection requires a modern board identity")
    board_id, unused_firmware = _modern_board_identity(repo)
    return board_id + "/"


async def check_for_update(repo):
    release_contract(repo)
    log("\nChecking %s for updates" % repo["repo"])
    url = "https://api.github.com/repos/%s/releases" % repo["repo"]
    response = None
    try:
        response = urequests.get(url, headers={"User-Agent": "TartLab"})
        settings = load_settings()
        if response.status_code != 200:
            log("Failed to fetch releases: %s" % response.status_code)
            return None, None
        for release in response.json():
            if release.get("prerelease", False) and not settings.get("pre-release-updates", False):
                continue
            if release["tag_name"] != repo["installed_version"]:
                return release["assets"], release["tag_name"]
            break
        log("No suitable releases found.")
        return None, None
    except Exception as error:
        log("Error checking repo!")
        log_exception(error)
        return None, None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


async def download_asset(asset_url, target_file):
    log("Downloading %s" % asset_url)
    retries = 0
    partial_file = target_file + ".part"
    while retries < 5:
        response = None
        try:
            if file_exists(partial_file) == 1:
                uos.remove(partial_file)
            response = urequests.get(asset_url, headers={"User-Agent": "TartLab"})
            if response.status_code != 200:
                log("Error: Received status code %s" % response.status_code)
                return False
            with open(partial_file, "wb") as stream:
                while True:
                    chunk = response.raw.read(1024)
                    if not chunk:
                        break
                    stream.write(chunk)
            if file_exists(target_file) == 1:
                uos.remove(target_file)
            uos.rename(partial_file, target_file)
            return True
        except Exception as error:
            if file_exists(partial_file) == 1:
                uos.remove(partial_file)
            if error.args and error.args[0] == 23:
                retries += 1
                await asyncio.sleep(2)
            else:
                raise
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
    raise OSError("Maximum download retries exceeded")


def _required_install_space(manifest, repo=None):
    required = FILESYSTEM_RESERVE_BYTES
    for package in manifest:
        if package.get("selection") == "board-id-subtree":
            if repo is None:
                raise ValueError("Selected package size requires board identity")
            board_id, unused_firmware = _modern_board_identity(repo)
            expanded = package.get("selected_expanded_sizes", {}).get(board_id)
            if expanded is None:
                raise ValueError("Selected package size is missing for board identity")
        else:
            expanded = package.get("expanded_size")
        if expanded is None:
            filename = TMP_UPDATE_FOLDER + "/" + package["file_name"]
            expanded = uos.stat(filename)[6]
        if not isinstance(expanded, int) or expanded < 0:
            raise ValueError("Invalid expanded package size")
        required += expanded
    return required


def _free_space():
    statvfs = uos.statvfs("/")
    return statvfs[1] * statvfs[3]


def _initial_progress_steps(assets):
    """Count fixed validation steps plus package archives before manifest load."""
    packages = 0
    for asset in assets:
        name = asset.get("name", "")
        if isinstance(name, str) and name.endswith(".tar"):
            packages += 1
    return 4 + packages


def sha256_hash(file_path):
    sha256 = uhashlib.sha256()
    with open(file_path, "rb") as stream:
        while True:
            chunk = stream.read(1024)
            if not chunk:
                break
            sha256.update(chunk)
    return "".join("{:02x}".format(byte) for byte in sha256.digest())


def inspect_archive(filename, target_folder, member_prefix=None):
    paths = []
    terminated = False
    with open(filename, "rb") as tar:
        while True:
            header = tar.read(512)
            if len(header) != 512:
                raise ValueError("Truncated tar header")
            if header == b"\0" * 512:
                terminated = True
                break
            stored_text = header[148:156].split(b"\0", 1)[0].strip() or b"0"
            stored_checksum = int(stored_text, 8)
            actual_checksum = sum(header[:148]) + (32 * 8) + sum(header[156:])
            if stored_checksum != actual_checksum:
                raise ValueError("Invalid tar header checksum")
            name = header[0:100].split(b"\0", 1)[0].decode("utf-8")
            prefix = header[345:500].split(b"\0", 1)[0].decode("utf-8")
            if prefix:
                name = prefix + "/" + name
            if not name:
                raise ValueError("Empty tar member name")
            size_text = header[124:136].split(b"\0", 1)[0].strip() or b"0"
            size = int(size_text, 8)
            if "PaxHeader" not in name:
                path = _target_path(target_folder, name.rstrip("/"))
                if member_prefix is None or name.startswith(member_prefix):
                    paths.append(path)
            remaining = size + ((512 - size % 512) % 512)
            while remaining:
                chunk = tar.read(min(1024, remaining))
                if not chunk:
                    raise ValueError("Truncated tar member")
                remaining -= len(chunk)
    if not terminated or not paths:
        raise ValueError("Empty or unterminated tar archive")
    return paths


async def untar(filename, target_folder="/", overwrite=False, verbose=False,
                chunksize=4096, member_prefix=None):
    inspect_archive(filename, target_folder, member_prefix)
    with open(filename, "rb") as tar:
        for info in TarFile(fileobj=tar):
            await asyncio.sleep(0.01)
            if "PaxHeader" in info.name:
                continue
            if member_prefix is not None and not info.name.startswith(member_prefix):
                continue
            target_path = _target_path(target_folder, info.name)
            if target_path == "/boot.py" and file_exists(PHASE1_MIGRATION_FILE) == 1:
                log("Preserving protected recovery boot gate")
                continue
            directory = target_path.rsplit("/", 1)[0]
            if file_exists(directory) != 2:
                mkdirs(directory)
            if info.type == "file":
                if verbose:
                    print("F %s" % target_path)
                if overwrite or not file_exists(target_path):
                    with open(target_path, "wb") as stream:
                        while True:
                            chunk = info.subf.read(chunksize)
                            if not chunk:
                                break
                            stream.write(chunk)
            elif verbose:
                print("? %s" % target_path)


async def update_folder(tar_file, target_folder, replace, member_prefix=None):
    log("Updating %s" % target_folder)
    inspect_archive(tar_file, target_folder, member_prefix)
    if replace:
        log("Removing contents of %s" % target_folder)
        if file_exists(target_folder) == 2:
            rmvdir(target_folder)
        mkdirs(target_folder)
        await asyncio.sleep(0.25)
    await untar(
        tar_file, target_folder, True, True, member_prefix=member_prefix)
    log("Success (%s)" % tar_file)


def clean_up():
    if file_exists(TMP_UPDATE_FOLDER) == 2:
        rmvdir(TMP_UPDATE_FOLDER)


async def update_packages(repo, callback):
    global updating_updater
    try:
        manifest_name, unused_profile = release_contract(repo)
    except Exception as error:
        log("Release feed policy rejected the update!")
        log_exception(error)
        return UPDATE_FAILED
    assets, latest_version = await check_for_update(repo)
    if not assets:
        return UPDATE_NONE

    progress_steps = _initial_progress_steps(assets)
    asset_map = {asset["name"]: asset for asset in assets}
    manifest_asset = asset_map.get(manifest_name)
    if manifest_asset is None:
        log("Could not find %s." % manifest_name)
        return UPDATE_FAILED
    callback("Checking disk space", 1, progress_steps)
    try:
        total_size = manifest_asset["size"]
        free_space = _free_space()
        if total_size + FILESYSTEM_RESERVE_BYTES > free_space:
            log("Not enough disk space!")
            return UPDATE_FAILED
    except Exception as error:
        log("Error checking disk space!")
        log_exception(error)
        return UPDATE_FAILED

    clean_up()
    mkdirs(TMP_UPDATE_FOLDER)
    await asyncio.sleep(0.25)

    try:
        callback("Downloading manifest", 2, progress_steps)
        manifest_path = TMP_UPDATE_FOLDER + "/" + manifest_name
        if not await download_asset(manifest_asset["browser_download_url"], manifest_path):
            raise OSError("Manifest download failed")
        with open(manifest_path, "r") as stream:
            document = ujson.load(stream)
        manifest = manifest_packages(document, repo, latest_version)
        progress_steps = 4 + len(manifest)

        required_download = 0
        for package in manifest:
            asset = asset_map.get(package["file_name"])
            if asset is None:
                raise ValueError("Missing release asset: " + package["file_name"])
            required_download += asset["size"]
        if required_download + FILESYSTEM_RESERVE_BYTES > _free_space():
            raise OSError("Not enough disk space to stage release")

        callback("Downloading files", 3, progress_steps)
        for package in manifest:
            asset = asset_map.get(package["file_name"])
            if asset is None:
                raise ValueError("Missing release asset: " + package["file_name"])
            target_file = TMP_UPDATE_FOLDER + "/" + package["file_name"]
            if not await download_asset(asset["browser_download_url"], target_file):
                raise OSError("Package download failed: " + package["file_name"])

        callback("Checking files", 4, progress_steps)
        for package in manifest:
            filename = TMP_UPDATE_FOLDER + "/" + package["file_name"]
            if sha256_hash(filename) != package["sha256"]:
                raise ValueError("Hash did not match: " + package["file_name"])
            inspect_archive(
                filename, package["target"],
                _package_member_prefix(package, repo))
        if _required_install_space(manifest, repo) > _free_space():
            raise OSError("Not enough disk space to extract release safely")
        log("Downloaded files successfully.")
    except Exception as error:
        log("Update validation failed!")
        log_exception(error)
        clean_up()
        return UPDATE_FAILED

    for package in manifest:
        if package["file_name"] == "tartlabutils.tar":
            manifest.remove(package)
            manifest.append(package)
            updating_updater = True
            break

    try:
        begin_update(repo["name"], repo["installed_version"], latest_version)
        step = 5
        for package in manifest:
            filename = TMP_UPDATE_FOLDER + "/" + package["file_name"]
            callback("Updating %s" % package["target"], step, progress_steps)
            if package["target"].rstrip("/") == "/recovery" and \
                    file_exists("/recovery/recovery.py") == 1:
                log("Preserving installed recovery runtime")
                step += 1
                continue
            await update_folder(
                filename, package["target"], package["clear_first"],
                _package_member_prefix(package, repo))
            step += 1
        set_update_pending_health()
        clean_up()
        return UPDATE_INSTALLED
    except Exception as error:
        log("Error installing packages!")
        log_exception(error)
        try:
            set_update_failed(error)
        except Exception as marker_error:
            log("Could not persist failed-update marker!")
            log_exception(marker_error)
        clean_up()
        return UPDATE_FAILED


def restart_device(stay_in_IDE=True):
    log("Restarting device...")
    if stay_in_IDE:
        settings = load_settings()
        settings["STARTUP_MODE"] = "IDE"
        save_settings(settings)
    time.sleep(0.2)
    machine.reset()


async def main_update_routine(callback):
    global updating_updater
    updating_updater = False
    with open(REPOS_FILE, "r") as stream:
        repos = ujson.load(stream)
    log("============ Updater has started. PLEASE WAIT. ============")
    repo_list = list(repos["list"])
    repo_list.sort(key=lambda item: item["name"] == "TartLab")
    restart_required = False
    for repo in repo_list:
        log("\nStarting update for %s from version %s" % (repo["name"], repo["installed_version"]))
        await asyncio.sleep(0.2)
        result = await update_packages(repo, callback)
        if result == UPDATE_INSTALLED:
            restart_required = True
            log("Installed %s; version commit is pending boot health" % repo["name"])
            if updating_updater:
                break
        elif result == UPDATE_FAILED:
            restart_required = True
            log("Update FAILED for %s" % repo["name"])
            break
        else:
            log("No update necessary for %s" % repo["name"])
    log("============ Updater has finished. ============")
    await asyncio.sleep(0.5)
    if restart_required:
        restart_device()
