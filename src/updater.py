import ujson
import urequests
import uos
from tarfile import TarFile


PACKAGES_FILE='/packages.json'

def check_for_update(package):
    repo_url = f"https://api.github.com/repos/{package['name']}/releases/latest"
    response = urequests.get(repo_url)
    
    if response.status_code == 200:
        latest_release = response.json()
        latest_version = latest_release['tag_name']
        
        if latest_version > package['installed_version']:
            return latest_release['tarball_url'], latest_version
    
    return None, None


def download_update(tarball_url, target_file='/tmp/update.tar'):
    response = urequests.get(tarball_url, stream=True)
    
    if response.status_code == 200:
        with open(target_file, 'wb') as file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    file.write(chunk)
        return True
    
    return False


def exists(path):
    try:
        _ = uos.stat(path)
    except:
        return False
    else:
        return True


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
                    if not exists(target_path):
                        uos.mkdir(target_path)
                elif info.type == "file":
                    if verbose:
                        print("F %s" % target_path)
                    if overwrite or not exists(target_path):
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


def replace_folder(tar_file, target_folder):
    # Delete the existing folder contents
    if uos.path.exists(target_folder):
        for root, dirs, files in uos.ilistdir(target_folder):
            for name in files:
                uos.remove(uos.path.join(root, name))
            for name in dirs:
                uos.rmdir(uos.path.join(root, name))
    else:  # Create the target folder
        uos.mkdir(target_folder)
    untar(tar_file, True, True)


def update_package(package):
    tarball_url, latest_version = check_for_update(package)
    
    if tarball_url and latest_version:
        target_file = '/tmp/update.tar'
        
        if download_update(tarball_url, target_file):
            replace_folder(target_file, package['folder'])
            
            # Update the installed version in the package object
            package['installed_version'] = latest_version
            return True
        
    return False


def main_update_routine():
    packages = []
    with open(PACKAGES_FILE, 'r') as file:
        packages = ujson.load(file)
    
    for package in packages:
        if update_package(package):
            print(f"Updated {package['name']} to version {package['installed_version']}")
        else:
            print(f"No update necessary for {package['name']}")
    
    # Save the updated package list back to the file
    with open(PACKAGES_FILE, 'w') as file:
        ujson.dump(packages, file)
