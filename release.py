# This script uses the content of the packages.json file to create release packages
# and a manifest.json file.  These can then be uploaded to GitHub as a new release.

import os
import shutil
import tarfile
import hashlib
import json

def calculate_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

PROTECTED_PATHS = (
    "/app.py", "/hdwconfig.py", "/settings.json", "/repos.json", "/logs",
    "/device", "/state", "/files/user",
)


def create_tarfile(name, source, exclude_subdirs, output_dir, excludes=None):
    excludes = set(excludes or [])
    tar_path = os.path.join(output_dir, f"{name}.tar")
    with tarfile.open(tar_path, "w", format=tarfile.USTAR_FORMAT) as tar:
        if exclude_subdirs:
            for item in os.listdir(source):
                item_path = os.path.join(source, item)
                if os.path.isfile(item_path) and item not in excludes:
                    tar.add(item_path, arcname=item)
        else:
            for root, dirs, files in os.walk(source):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Add file to tar, stripping the folder_path prefix
                    tar.add(file_path, arcname=os.path.relpath(file_path, source))
    return tar_path


def archive_paths(tar_path, target):
    target = "/" + target.strip("/")
    if target == "/":
        target = ""
    with tarfile.open(tar_path, "r") as tar:
        return sorted(target + "/" + member.name.replace("\\", "/") for member in tar.getmembers())


def validate_archive_ownership(paths):
    for path in paths:
        normalized = "/" + path.strip("/")
        for protected in PROTECTED_PATHS:
            if normalized == protected or normalized.startswith(protected + "/"):
                raise ValueError(f"Release archive targets protected path: {normalized}")

def main():
    release_dir = "release"
    
    # Delete the release directory if it exists
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)
    
    # Create the release directory
    os.makedirs(release_dir)

    with open("tartlab_packages.json", "r") as f:
        packages = json.load(f)
    
    manifest = []
    inventory = {}
    
    for package in packages:
        name = package["name"]

        confirm = input(f"Include '{name}' package in release? (y/n): ")
        if confirm.lower() == 'n':
            continue

        source = package["source"]
        exclude_subdirs = source.endswith('*')
        
        if exclude_subdirs:
            source = source.rstrip('*')
        
        tar_path = create_tarfile(
            name, source, exclude_subdirs, release_dir, package.get("exclude", []))
        sha256 = calculate_sha256(tar_path)
        paths = archive_paths(tar_path, package["target"])
        validate_archive_ownership(paths)
        inventory[name] = paths
        
        manifest_entry = {
            "file_name": os.path.basename(tar_path),
            "sha256": sha256,
            "target": package["target"],
            "clear_first": package["clear_first"],
            "ownership": package.get("ownership", "system"),
        }
        manifest.append(manifest_entry)
    
    manifest_path = os.path.join(release_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    with open(os.path.join(release_dir, "archive_inventory.json"), "w") as f:
        json.dump(inventory, f, indent=4)

    print("Process complete.")

if __name__ == "__main__":
    main()
