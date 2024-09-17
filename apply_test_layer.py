import os
import shutil

# Define the source and target root directories
source_root = 'test_layer'
target_root = 'dist'

# Walk through the source directory tree
for dirpath, dirnames, filenames in os.walk(source_root):
    # Calculate the relative path from the source root
    relative_path = os.path.relpath(dirpath, source_root)
    # Construct the corresponding target directory path
    target_dir = os.path.join(target_root, relative_path)
    # Create the target directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)
    # Iterate over all files in the current directory
    for filename in filenames:
        # Construct full source and target file paths
        source_file = os.path.join(dirpath, filename)
        target_file = os.path.join(target_dir, filename)
        # Copy the file to the target location, overwriting if it exists
        shutil.copy2(source_file, target_file)
