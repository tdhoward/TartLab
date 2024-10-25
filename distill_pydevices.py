# Pulls in a distilled form of PyDevices (https://github.com/bdbarnett/mpdisplay)
# in order to create a managed package that we can use for TartLab updates.

import os
import shutil
import glob
import fnmatch
import re

# Define source and destination root directories
source_root = os.path.abspath(os.path.join('..', 'mpdisplay'))
destination_root = os.path.abspath(os.path.join('..', 'TartLab', 'src', 'lib', 'pydevices'))

# Define the copy tasks
copy_tasks = [
    {
        'src_pattern': os.path.join('board_configs', '*', 'board_config.py'),
        'dst_pattern': os.path.join('board_configs', '*', 'board_config.py'),
        'exclude_dirs': [
            os.path.join('board_configs', 'circuitpython'),
            os.path.join('board_configs', 'desktop'),
            os.path.join('board_configs', 'jupyter'),
        ],
        'exclude_dirs_glob': [os.path.join('board_configs', 'wokwi_*')],
    },
    {
        'src_pattern': os.path.join('drivers', 'display', '*.py'),
        'dst_pattern': os.path.join('display_drv', ''),
    },
    {
        'src_pattern': os.path.join('drivers', 'touch', '*.py'),
        'dst_pattern': os.path.join('touch_drv', ''),
    },
    {
        'src_pattern': os.path.join('src', 'lib', '*'),
        'dst_pattern': os.path.join('', ''),
        'exclude_files': ['framebuf.py'],
    },
    {
        'src_pattern': os.path.join('src', 'extras', 'png.py'),
        'dst_pattern': os.path.join('utils', 'png.py'),
    },
    {
        'src_pattern': os.path.join('src', 'extras', 'pbm.py'),
        'dst_pattern': os.path.join('utils', 'pbm.py'),
    },
    {
        'src_pattern': os.path.join('src', 'extras', 'bmp565.py'),
        'dst_pattern': os.path.join('utils', 'bmp565.py'),
    },
]

def process_task(task, source_root, destination_root):
    src_pattern = task['src_pattern']
    dst_pattern = task['dst_pattern']
    exclude_dirs = task.get('exclude_dirs', [])
    exclude_dirs_glob = task.get('exclude_dirs_glob', [])
    exclude_files = task.get('exclude_files', [])

    # Generate full source pattern path
    src_pattern_full = os.path.join(source_root, src_pattern)
    matching_paths = glob.glob(src_pattern_full, recursive=True)

    # Convert patterns to lists of parts
    src_pattern_parts = src_pattern.split(os.sep)
    dst_pattern_parts = dst_pattern.split(os.sep)

    # Identify the indices of wildcards in the src_pattern
    wildcard_indices = [i for i, part in enumerate(src_pattern_parts) if part == '*']

    for src_path in matching_paths:
        # Apply exclusions
        excluded = False
        relative_src_path = os.path.relpath(src_path, source_root)
        src_dir = os.path.dirname(relative_src_path)

        # Exclude specific directories
        for exclude_dir in exclude_dirs:
            exclude_dir_norm = os.path.normpath(exclude_dir)
            if src_dir.startswith(exclude_dir_norm):
                excluded = True
                break

        # Exclude directories based on glob patterns
        if not excluded:
            for exclude_dir_glob in exclude_dirs_glob:
                exclude_dir_glob_norm = os.path.normpath(exclude_dir_glob)
                if fnmatch.fnmatch(src_dir, exclude_dir_glob_norm):
                    excluded = True
                    break

        # Exclude specific files
        if not excluded:
            filename = os.path.basename(src_path)
            if filename in exclude_files:
                excluded = True

        if excluded:
            continue

        # Split the relative source path into parts
        src_path_parts = relative_src_path.split(os.sep)

        # Extract variable parts based on wildcard positions
        variable_parts = [src_path_parts[i] for i in wildcard_indices]

        # Build the destination path parts
        dst_path_parts = []
        variable_idx = 0
        for part in dst_pattern_parts:
            if part == '*':
                dst_path_parts.append(variable_parts[variable_idx])
                variable_idx += 1
            else:
                dst_path_parts.append(part)

        # Handle cases where dst_pattern ends with os.sep or is empty
        if dst_pattern.endswith(os.sep) or dst_pattern == '':
            # Append the filename to the destination path
            dst_path_parts.append(os.path.basename(src_path))
        else:
            # Check if the last part is an empty string
            if dst_path_parts and dst_path_parts[-1] == '':
                dst_path_parts[-1] = os.path.basename(src_path)

        # Construct the relative destination path
        dst_path_relative = os.path.join(*dst_path_parts)
        dst_path = os.path.join(destination_root, dst_path_relative)

        # Ensure the destination directory exists
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)

        # Check if the source path is a file or a directory
        if os.path.isfile(src_path):
            # Copy the file
            shutil.copy2(src_path, dst_path)
            print(f"Copied file {src_path} to {dst_path}")
        elif os.path.isdir(src_path):
            # Copy the directory
            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
            print(f"Copied directory {src_path} to {dst_path}")
        else:
            print(f"Skipped {src_path}: Not a file or directory")


# Renames folders with dashes to underscores
def rename_dash_folders(path):
    for root, dirnames, filenames in os.walk(path, topdown=False):
        for dirname in dirnames:
            if '-' in dirname:
                old_dir = os.path.join(root, dirname)
                new_dirname = dirname.replace('-', '_')
                new_dir = os.path.join(root, new_dirname)
                os.rename(old_dir, new_dir)


# Check if the destination directory exists
if os.path.exists(destination_root):
    # Prompt the user for confirmation
    confirm = input(f"Are you sure you want to delete the directory '{destination_root}'? (y/n): ")
    if confirm.lower() == 'y':
        # Delete the directory and all its contents
        shutil.rmtree(destination_root)
        print(f"The directory '{destination_root}' has been deleted.")
    else:
        print("Deletion canceled.")
        exit()

# Create the folder again
os.makedirs(destination_root)

# Execute all copy tasks
for task in copy_tasks:
    process_task(task, source_root, destination_root)

# Rename the folders with dashes so we can import them in python
rename_dash_folders(os.path.join(destination_root, 'board_configs'))
