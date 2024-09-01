import os

# Returns 1 for file, 2 for folder, or 0 if doesn't exist
def file_exists(filepath):
    try:
        stat = os.stat(filepath)
        if stat[0] & 0x8000 == 0x8000:
            return 1  # regular file
        return 2   # folder
    except OSError:
        return 0   # doesn't exist
    
# Remove URL encoding
def unquote(s):
    res = s.split('%')
    for i in range(1, len(res)):
        item = res[i]
        try:
            res[i] = chr(int(item[:2], 16)) + item[2:]
        except ValueError:
            res[i] = '%' + item
    return "".join(res)
    

# recursively delete dir tree
def rmvdir(d):  # Remove file or tree
    if os.stat(d)[0] & 0x4000:  # Dir
        for f in os.ilistdir(d):
            if f[0] not in ('.', '..'):
                rmvdir("/".join((d, f[0])))  # File or Dir
        os.rmdir(d)
    else:  # File
        os.remove(d)


def split_on_first(data, token = b'\r\n'):
    length = len(data)
    tl = len(token)
    for i in range(length - (tl - 1)):
        if data[i:i+tl] == token:
            return data[:i], data[i+tl:]
    # If no token is found, return the original data and an empty byte string
    return data, b''
