import os
import utime
from .response import HTTPResponse
from .url import HTTPRequest, InvalidRequest
from .sendfile import sendfile

# Since there is no strftime in micropython...
# Days and Months mappings for HTTP-date format (for Last-Modified header)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_http_date(gmtime_tuple):
    # gmtime_tuple format: (year, month, mday, hour, minute, second, weekday, yearday)
    year, month, mday, hour, minute, second, weekday, _ = gmtime_tuple
    return "{}, {:02d} {} {:04d} {:02d}:{:02d}:{:02d} GMT".format(
        DAYS[weekday], mday, MONTHS[month - 1], year, hour, minute, second
    )

# extensions to serve
FILE_TYPES = {
    'html': 'text/html',
    'css': 'text/css',
    'js': 'application/javascript',
    'svg': 'image/svg+xml',
    'png': 'image/png',
    'py': 'text/x-python',
    'ico': 'image/x-icon',
    'jpg': 'image/jpeg',
}


def file_or_dir_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


# Serve static files with client-side caching
async def serve_file(reader, writer, request, file_path, use_caching = True):
    extension = file_path.split('.')[-1]
    content_type = FILE_TYPES.get(extension, 'application/octet-stream')
    extra_headers = dict()
    try:
        if file_or_dir_exists(file_path + '.gz'):  # send gzipped version, if it exists
            file_path += '.gz'
            extra_headers['Content-Encoding'] = "gzip"
        # Set up headers for caching
        file_stat = os.stat(file_path)
        if use_caching:
            last_modified_time = file_stat[8]  # The 8th element is the last modified time
            last_modified_str = format_http_date(utime.gmtime(last_modified_time))
            last_modified_bytes = last_modified_str.encode()
            # b'If-Modified-Since': b'Wed, 22 May 2024 17:57:58 GMT'
            if b'If-Modified-Since' in request.header:
                print(request.header[b'If-Modified-Since'])
                if request.header[b'If-Modified-Since'] == last_modified_bytes:
                    response = HTTPResponse(304)
                    await response.send(writer)
                    return
            extra_headers['Last-Modified'] = last_modified_str
            extra_headers['Cache-Control'] = 'public, max-age=3600'
        else:
            extra_headers['Cache-Control'] = 'no-cache'
        file_size = str(file_stat[6])  # in bytes
        extra_headers['Content-Length'] = file_size
        response = HTTPResponse(200, content_type, close=True, header=extra_headers)
        await response.send(writer)
        await sendfile(writer, file_path)
        await writer.drain()
        print(f"Served file: {file_path} with response code 200")
    except OSError:
        response = HTTPResponse(404)
        await response.send(writer)
        print(f"File not found: {file_path} with response code 404")
