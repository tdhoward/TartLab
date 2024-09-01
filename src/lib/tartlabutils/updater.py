import ujson
import urequests
import uos
from tarfile import TarFile
from .miscutils import rmvdir, file_exists
import uhashlib
import machine


REPOS_FILE='/repos.json'
TMP_UPDATE_FOLDER = '/tmp'
updating_root = False

def check_for_update(repo):
    repo_api_url = f"https://api.github.com/repos/{repo['repo']}/releases/latest"
    response = urequests.get(repo_api_url)
    
    if response.status_code == 200:
        latest_release = response.json()
        latest_version = float(latest_release['tag_name'])
        
        if latest_version > repo['installed_version']:
            return latest_release['assets'], latest_version
    return None, None


def download_asset(tarball_url, target_file):
    response = urequests.get(tarball_url, stream=True)
    if response.status_code == 200:
        with open(target_file, 'wb') as file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)
        return True
    return False


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
                if info.type == "dir":
                    if verbose:
                        print("D %s" % target_path)
                    if not file_exists(target_path):
                        uos.mkdir(target_path)
                elif info.type == "file":
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
    if replace:
        # Delete the existing folder contents
        if file_exists(target_folder) == 2:
            rmvdir(target_folder)
        else:  # Create the target folder
            uos.mkdir(target_folder)
    untar(tar_file, True, True)


def clean_up():
    if file_exists(TMP_UPDATE_FOLDER) == 2:
        rmvdir(TMP_UPDATE_FOLDER)


def update_packages(repo):
    global updating_root
    assets, latest_version = check_for_update(repo)
    if not assets:
        return False

    # check if we have enough storage space to do this.
    total_size = sum(a['size'] for a in assets)
    statvfs = uos.statvfs('/')
    # Block size (statvfs[1]) * Number of free blocks (statvfs[3])
    free_space = statvfs[1] * statvfs[3]
    if total_size + 10000 > free_space:  # leave a buffer of 10k
        return False
    
    # Delete the temp update folder if it exists
    if file_exists(TMP_UPDATE_FOLDER):
        rmvdir(TMP_UPDATE_FOLDER)
    
    # Create the temp update folder directory
    uos.mkdir(TMP_UPDATE_FOLDER)
    
    # download all the assets
    for a in assets:
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
        clean_up()
        return False

    # step through the manifest list, check csums
    for m in manifest:
        fname = TMP_UPDATE_FOLDER + '/' + m['file_name']
        hash = sha256_hash(fname)
        if hash != m['sha256']:
            clean_up()
            return False

    # if we're updating the updater, move that to the end of the list
    for m in manifest:
        if m['file_name'] == 'tartlabutils.tar':
            manifest.remove(m)  # Remove the object from its current position
            manifest.append(m)  # Append it to the end of the list
            updating_root = True
            break

    # if everything is correct, install them all and update the version
    for m in manifest:
        fname = TMP_UPDATE_FOLDER + '/' + m['file_name']
        update_folder(fname, m['target'], m['clear_first'])

    # Update the installed version in the package object
    repo['installed_version'] = latest_version
    return True


def restart_device():
    machine.reset()


def main_update_routine():
    global updating_root
    repos = {}
    with open(REPOS_FILE, 'r') as file:
        repos = ujson.load(file)
    
    for repo in repos['list']:
        if update_packages(repo):
            print(f"Updated {repo['name']} to version {repo['installed_version']}")
            if updating_root:
                break
        else:
            print(f"No update necessary for {repo['name']}")
    
    # Save the updated package list back to the file
    with open(REPOS_FILE, 'w') as file:
        ujson.dump(repos, file)

    restart_device()
