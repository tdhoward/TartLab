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
        'src_pattern': os.path.join('boardconfigs', '*', 'board_config.py'),
        'dst_pattern': os.path.join('boardconfigs', '*', 'board_config.py'),
        'exclude_dirs': [
            os.path.join('boardconfigs', 'circuitpython'),
            os.path.join('boardconfigs', 'desktop'),
            os.path.join('boardconfigs', 'jupyter'),
        ],
        'exclude_dirs_glob': [os.path.join('boardconfigs', 'wokwi_*')],
    },
    {
        'src_pattern': os.path.join('drivers', 'display', '*.py'),
        'dst_pattern': os.path.join('displaydrv', ''),
    },
    {
        'src_pattern': os.path.join('drivers', 'touch', '*.py'),
        'dst_pattern': os.path.join('touchdrv', ''),
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

    # Convert src_pattern to a regex for matching and extracting variable parts
    src_pattern_relative = src_pattern.replace(os.sep, '/')
    src_pattern_regex = re.escape(src_pattern_relative)
    src_pattern_regex = src_pattern_regex.replace(r'\*', '(.*)')
    src_pattern_regex = '^' + src_pattern_regex + '$'
    src_pattern_re = re.compile(src_pattern_regex)

    for src_path in matching_paths:
        # Apply exclusions
        excluded = False
        relative_src_path = os.path.relpath(src_path, source_root).replace(os.sep, '/')
        src_dir = os.path.dirname(relative_src_path).replace(os.sep, '/')

        # Exclude specific directories
        for exclude_dir in exclude_dirs:
            exclude_dir_norm = exclude_dir.replace(os.sep, '/')
            if src_dir.startswith(exclude_dir_norm):
                excluded = True
                break

        # Exclude directories based on glob patterns
        if not excluded:
            for exclude_dir_glob in exclude_dirs_glob:
                exclude_dir_glob_norm = exclude_dir_glob.replace(os.sep, '/')
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

        # Determine destination path
        if '*' in dst_pattern:
            m = src_pattern_re.match(relative_src_path)
            if not m:
                print(f"Warning: No match for {relative_src_path} with pattern {src_pattern_regex}")
                continue
            variable_parts = m.groups()
            dst_path_relative = dst_pattern
            for vp in variable_parts:
                dst_path_relative = dst_path_relative.replace('*', vp, 1)
            dst_path = os.path.join(destination_root, dst_path_relative)
        elif dst_pattern.endswith(os.sep) or dst_pattern == '':
            filename = os.path.basename(src_path)
            dst_path = os.path.join(destination_root, dst_pattern, filename)
        else:
            dst_path = os.path.join(destination_root, dst_pattern)

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
