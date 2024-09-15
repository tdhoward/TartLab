import os
import gzip
import shutil
import time

# This script uses the src folder to create a dist folder ready for deployment.
# It only copies over the files that are needed, and g-zips files larger than 2k.
# The gzipped files can then be served by the embedded device more quickly, without
# requiring gzipping on the fly.

SRC_FOLDER = './src'
DIST_FOLDER = './dist'
IDE_FOLDER = '/ide'
WEB_FOLDER = '/www'


# Walks through all files (including subfolders) and compresses files
# larger than size_threshold with gzip, removing the original file
def compress_and_remove_large_files(folder_path, size_threshold=2048):
    # Walk through the directory tree
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            
            # Check if the file size is greater than the threshold
            if os.path.getsize(file_path) > size_threshold:
                # Get the original file's creation and modification times
                stat = os.stat(file_path)
                original_times = (stat.st_atime, stat.st_mtime)

                # Create a gzipped version of the file
                with open(file_path, 'rb') as f_in:
                    with gzip.open(file_path + '.gz', 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Set the creation and modification times of the new .gz file
                os.utime(file_path + '.gz', times=original_times)

                # Delete the original file
                os.remove(file_path)


def copy_only_files(src_folder, dest_folder):
    for item in os.listdir(src_folder):
        src_path = os.path.join(src_folder, item)

        # Check if the item is a file (ignore directories for now)
        if os.path.isfile(src_path):
            dest_path = os.path.join(dest_folder, item)
            
            # Copy the file to the destination folder
            shutil.copy(src_path, dest_path)
            
            # Copy the original file's access and modification times
            shutil.copystat(src_path, dest_path)


# Check if the directory exists
if os.path.exists(DIST_FOLDER):
    # Prompt the user for confirmation
    confirm = input(f"Are you sure you want to delete the directory '{DIST_FOLDER}'? (y/n): ")
    if confirm.lower() == 'y':
        # Delete the directory and all its contents
        shutil.rmtree(DIST_FOLDER)
        print(f"The directory '{DIST_FOLDER}' has been deleted.")
    else:
        print("Deletion canceled.")
        exit()

# Create the new dist folder
os.makedirs(DIST_FOLDER)

# Copy the main py files from SRC to DIST
copy_only_files(SRC_FOLDER, DIST_FOLDER)

# /files
shutil.copytree(SRC_FOLDER + '/files', DIST_FOLDER + '/files')

# /configs
shutil.copytree(SRC_FOLDER + '/configs', DIST_FOLDER + '/configs')

# /lib
# TODO: Maybe at some point we compile the python code in the lib folder
shutil.copytree(SRC_FOLDER + '/lib', DIST_FOLDER + '/lib')

# copy all the ide files (we'll delete some later)
shutil.copytree(SRC_FOLDER + IDE_FOLDER, DIST_FOLDER + IDE_FOLDER)

# remove the files used for testing
shutil.rmtree(DIST_FOLDER + IDE_FOLDER + WEB_FOLDER + '/api')
shutil.rmtree(DIST_FOLDER + IDE_FOLDER + WEB_FOLDER + '/files')

# TODO: It would be great to include a bundler and minifier here for the web app files.

# Compress the static web app files
compress_and_remove_large_files(DIST_FOLDER + IDE_FOLDER + WEB_FOLDER)

print("Process complete.")
