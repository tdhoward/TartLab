# This script creates a release package suitable for uploading to GitHub.
# Two files are created, 'tartlab.tar' and 'checksums.json'
import tarfile
import hashlib
import os
import json

def create_tar_with_checksum(folder_path, tar_filename, target_folder):
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

    tar_path = os.path.join(target_folder, tar_filename)
    checksum_file_path = os.path.join(target_folder, 'checksums.json')

    # Create a tar file with relative paths
    with tarfile.open(tar_path, 'w') as tar:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # Add file to tar, stripping the folder_path prefix
                tar.add(file_path, arcname=os.path.relpath(file_path, folder_path))

    # Calculate SHA-256 checksum of the tar file
    sha256_hash = hashlib.sha256()
    with open(tar_path, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    checksum = sha256_hash.hexdigest()

    # Create a dictionary with the tar file name and checksum
    checksum_dict = {tar_filename: checksum}

    # Write the dictionary to checksums.json
    with open(checksum_file_path, 'w') as json_file:
        json.dump(checksum_dict, json_file, indent=4)

    return checksum_dict

# Example usage
folder_to_tar = 'dist/ide'
tar_filename = 'tartlab.tar'
target_folder = 'release'
create_tar_with_checksum(folder_to_tar, tar_filename, target_folder)
