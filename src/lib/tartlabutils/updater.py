import ujson
import urequests
import uos
from tarfile import TarFile
from .miscutils import rmvdir, mkdirs, file_exists, log, load_settings, save_settings
import uhashlib
import machine
import urequests


REPOS_FILE='/repos.json'
TMP_UPDATE_FOLDER = '/tmp'
updating_updater = False


def check_for_update(repo):
    print(f"Checking {repo['repo']} for updates")
    repo_api_url = f"https://api.github.com/repos/{repo['repo']}/releases"
    headers = {'User-Agent': 'TartLab'}
    response = urequests.get(repo_api_url, headers=headers)
    settings = load_settings()
    
    if response.status_code == 200:
        releases = response.json()
        latest_release = None
        
        for release in releases:
            is_prerelease = release.get('prerelease', False)
            if is_prerelease and not settings.get('pre-release-updates', False):
                continue  # Skip pre-releases if pre-release updates are not enabled

            latest_release = release  # Found a suitable release
            break

        if latest_release and latest_release['tag_name'] != repo['installed_version']:
            return latest_release['assets'], latest_release['tag_name']
        else:
            print("No suitable releases found.")
            return None, None
    else:
        print("Failed to fetch releases:", response.status_code)
        return None, None


def download_asset(tarball_url, target_file):
    print(f'Downloading {tarball_url}')
    headers = {'User-Agent': 'TartLab'}
    try:
        response = urequests.get(tarball_url, headers=headers)
        if response.status_code == 200:
            with open(target_file, 'wb') as file:
                while True:
                    chunk = response.raw.read(1024)
                    if not chunk:
                        break
                    file.write(chunk)
            return True
        else:
            print(f"Error: Received status code {response.status_code}")
            return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
    finally:
        try:
            response.close()
        except:
            pass


def sha256_hash(file_path):
    sha256 = uhashlib.sha256()
    with open(file_path, 'rb') as file:
        while True:
            chunk = file.read(1024)  # Read in 1 KB chunks
            if not chunk:
                break
            sha256.update(chunk)
    hash_bytes = sha256.digest()
    hash_hex = ''.join('{:02x}'.format(byte) for byte in hash_bytes)
    return hash_hex


def untar(filename, target_folder='/', overwrite=False, verbose=False, chunksize=4096):
    try:
        with open(filename, 'rb') as tar:
            for info in TarFile(fileobj=tar):
                if "PaxHeader" in info.name:
                    continue  # Skip PaxHeader files
                target_path = target_folder + '/' + info.name
                target_path = target_path.replace('//','/').rstrip("/")
                # Ensure the directory exists
                dir_path = target_path.rsplit('/', 1)[0]
                if file_exists(dir_path) != 2:  # 2 means folder exists
                    mkdirs(dir_path)
                if info.type == "file":
                    if verbose:
                        print("F %s" % target_path)
                    if overwrite or not file_exists(target_path):
                        with open(target_path, "wb") as fp:
                            while True:
                                chunk = info.subf.read(chunksize)
                                if not chunk:
                                    break
                                fp.write(chunk)
                elif verbose:
                    print("? %s" % target_path)
    except Exception as e:
        print("Error extracting tar file:", e)


def update_folder(tar_file, target_folder, replace):
    log(f'Updating {target_folder}')
    if replace:
        log(f'Removing contents of {target_folder}')
        # Delete the existing folder contents
        if file_exists(target_folder) == 2:
            rmvdir(target_folder)
        uos.mkdir(target_folder)  # recreate folder
    untar(tar_file, target_folder, True, True)


def clean_up():
    if file_exists(TMP_UPDATE_FOLDER) == 2:
        rmvdir(TMP_UPDATE_FOLDER)


def update_packages(repo):
    global updating_updater
    assets, latest_version = check_for_update(repo)
    if not assets:
        return False
    log(f'Updates found.')

    # check if we have enough storage space to do this.
    total_size = sum(a['size'] for a in assets)
    statvfs = uos.statvfs('/')
    # Block size (statvfs[1]) * Number of free blocks (statvfs[3])
    free_space = statvfs[1] * statvfs[3]
    if total_size + 10000 > free_space:  # leave a buffer of 10k
        log(f'Not enough disk space!')
        return False
    
    # Delete the temp update folder if it exists
    if file_exists(TMP_UPDATE_FOLDER):
        rmvdir(TMP_UPDATE_FOLDER)
    
    # Create the temp update folder directory
    uos.mkdir(TMP_UPDATE_FOLDER)

    manifest_asset = [a for a in assets if a['name']=='manifest.json']
    if len(manifest_asset) != 1:
        log(f'Could not find manifest.json.')
        clean_up()
        return False
    a = manifest_asset[0]

    # download the manifest
    target_file = TMP_UPDATE_FOLDER + '/' + a['name']
    url = a['browser_download_url']
    if not download_asset(url, target_file):
        clean_up()
        return False

    # try to load the manifest.json file
    manifest = []
    try:
        with open(TMP_UPDATE_FOLDER + '/manifest.json', 'r') as file:
            manifest = ujson.load(file)
    except:
        log(f'Error opening manifest.')
        clean_up()
        return False

    # get list of assets specified in manifest
    downloads = [m['file_name'] for m in manifest]
    log(f'Manifest contains: {downloads}')

    # download all the specified assets
    for a in assets:
        if a['name'] in downloads:
            target_file = TMP_UPDATE_FOLDER + '/' + a['name']
            url = a['browser_download_url']
            if not download_asset(url, target_file):
                log(f'Error downloading {url}')
                clean_up()
                return False

    # step through the manifest list, check csums
    for m in manifest:
        fname = TMP_UPDATE_FOLDER + '/' + m['file_name']
        hash = sha256_hash(fname)
        if hash != m['sha256']:
            clean_up()
            return False
    log('Downloaded files successfully.')

    # if we're updating the updater, move that to the end of the list
    for m in manifest:
        if m['file_name'] == 'tartlabutils.tar':
            manifest.remove(m)  # Remove the object from its current position
            manifest.append(m)  # Append it to the end of the list
            updating_updater = True
            break

    # if everything is correct, install them all and update the version
    for m in manifest:
        fname = TMP_UPDATE_FOLDER + '/' + m['file_name']
        update_folder(fname, m['target'], m['clear_first'])

    # Update the installed version in the package object
    repo['installed_version'] = latest_version
    return True


def restart_device(stay_in_IDE = True):
    if stay_in_IDE:
        settings = load_settings()
        settings['STARTUP_MODE'] = 'IDE'
        save_settings(settings)
    machine.reset()


def main_update_routine():
    global updating_updater
    repos = {}
    with open(REPOS_FILE, 'r') as file:
        repos = ujson.load(file)
    print(f'Updating repos: {repos}')

    # if we're updating TartLab, move that to the end of the list so we update last
    for r in repos['list']:
        if r['name'] == 'TartLab':
            repos['list'].remove(r)  # Remove the object from its current position
            repos['list'].append(r)  # Append it to the end of the list
            break

    for repo in repos['list']:
        print(f"Starting update for {repo['name']} to version {repo['installed_version']}")
        if update_packages(repo):
            print(f"Updated {repo['name']} to version {repo['installed_version']}")
            if updating_updater:
                break
        else:
            print(f"No update necessary for {repo['name']}")
    
    # Save the updated package list back to the file
    with open(REPOS_FILE, 'w') as file:
        ujson.dump(repos, file)

    restart_device()
