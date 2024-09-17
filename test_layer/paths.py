import sys

# add search folders for importing modules
dirs = ["./lib", 
        "./files/user", 
        "./configs", 
        "./lib/pydevices", 
        "./lib/pydevices/buses",
        "./lib/pydevices/display_drv",
        "./lib/pydevices/touch_drv",
        "./lib/pydevices/displays",
        "./lib/pydevices/utils"]

for d in dirs:
    if d not in sys.path:
        sys.path.insert(1, d)
