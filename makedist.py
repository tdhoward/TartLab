import os
import gzip
import shutil
import sys
from python_minifier import minify  # pip install python-minifier 
import subprocess

# This script uses the src folder to create a dist folder ready for deployment.
# It only copies over the files that are needed, and gzips files larger than 2k.
# The gzipped files can then be served by the embedded device more quickly, without
# requiring gzipping on the fly.

SRC_FOLDER = 'src'
DIST_FOLDER = 'dist'
IDE_FOLDER = 'ide'
WEB_FOLDER = 'www'

do_minify = True
if len(sys.argv) > 1:
    do_minify = sys.argv[1].lower() != 'false'

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

def minify_py_file(src_file, dest_file):
    # Read and minify the source file
    with open(src_file, 'r', encoding='utf-8') as f_in:
        source_code = f_in.read()
    try:
        minified_code = minify(source_code, remove_annotations=False)
                            # If there is trouble, try these other options:
                                #combine_imports=False,
                                #remove_pass=False,
                                #hoist_literals=False,
                                #rename_locals=False
                                #remove_object_base=False,
                                #convert_posargs_to_args=False,
                                #preserve_shebang=False,
                                #remove_explicit_return_none=False,
                                #constant_folding=False
        with open(dest_file, 'w', encoding='utf-8') as f_out:
            f_out.write(minified_code)
        print(f"Minified and copied: {src_file} -> {dest_file}")
    except Exception as e:
        print(f"Error minifying {src_file}: {e}")
        # Optionally, copy the file as is if minification fails
        shutil.copy2(src_file, dest_file)

# Function to copy and minify .py files, copying other files as is
def copy_filetree(src_folder, dest_folder, minify_python):
    for root, dirs, files in os.walk(src_folder):
        # Compute the relative path from src_folder to the current root
        rel_path = os.path.relpath(root, src_folder)
        dest_dir = os.path.join(dest_folder, rel_path)
        os.makedirs(dest_dir, exist_ok=True)
        for filename in files:
            src_file = os.path.join(root, filename)
            dest_file = os.path.join(dest_dir, filename)
            if filename.endswith('.py') and minify_python:
                minify_py_file(src_file, dest_file)
            else:
                # Copy other files as is
                shutil.copy2(src_file, dest_file)
            # Copy the original file's access and modification times
            shutil.copystat(src_file, dest_file)

# Function to copy files at the top level (no recursion)
def copy_top_level_files(src_folder, dest_folder, minify_python = False):
    for item in os.listdir(src_folder):
        src_path = os.path.join(src_folder, item)
        if os.path.isfile(src_path):
            dest_path = os.path.join(dest_folder, item)
            if src_path.endswith('.py') and minify_python:
                minify_py_file(src_path, dest_path)
            else:
                # Copy other files as is
                shutil.copy2(src_path, dest_path)
            # Copy the original file's access and modification times
            shutil.copystat(src_path, dest_path)


def build_web_app():
    build_dir = os.path.join(SRC_FOLDER, IDE_FOLDER, WEB_FOLDER)
    abs_build_dir = os.path.abspath(build_dir)
    if not os.path.isdir(abs_build_dir):
        print(f"Error: Build directory does not exist: {abs_build_dir}")
        return
    
    try:
        result = subprocess.run(
            ["npm.cmd", "run", "build"],
            cwd=abs_build_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("Build succeeded!")
    except subprocess.CalledProcessError as e:
        print("Build failed!")
        print(e.stderr)


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


# Create the new dist folder structure, including for the IDE web app destination
os.makedirs(os.path.join(DIST_FOLDER, IDE_FOLDER, WEB_FOLDER))

# Copy the main .py files from SRC to DIST (top-level files only, no minifying)
copy_top_level_files(SRC_FOLDER, DIST_FOLDER)

# Copy files in the /files directory  (These are human-readable files, so don't minify)
copy_filetree(os.path.join(SRC_FOLDER, 'files'), os.path.join(DIST_FOLDER, 'files'), False)

# Copy files in the /configs directory  (These are human-readable files, so don't minify)
copy_filetree(os.path.join(SRC_FOLDER, 'configs'), os.path.join(DIST_FOLDER, 'configs'), False)

# Copy and minify files in the /lib directory
copy_filetree(os.path.join(SRC_FOLDER, 'lib'), os.path.join(DIST_FOLDER, 'lib'), do_minify)


# Build the web app first
print("Building web app...")
build_web_app()

# Copy the ide .py files from SRC to DIST
copy_top_level_files(os.path.join(SRC_FOLDER, IDE_FOLDER), os.path.join(DIST_FOLDER, IDE_FOLDER), True)

# Copy all the ide web app files
copy_filetree(os.path.join(SRC_FOLDER, IDE_FOLDER, WEB_FOLDER, 'dist'), os.path.join(DIST_FOLDER, IDE_FOLDER, WEB_FOLDER), False)
# Compress the static web app files
compress_and_remove_large_files(os.path.join(DIST_FOLDER, IDE_FOLDER, WEB_FOLDER))

print("Process complete.")
