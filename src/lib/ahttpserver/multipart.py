# Handles uploads with a Content-Type of 'multipart/form-data'
import os
import uasyncio as asyncio
from .response import HTTPResponse, sendHTTPResponse
from .url import HTTPRequest, InvalidRequest
from .server import HTTPServerError


# Extract filename from Content-Disposition header
def extract_filename(content_disposition):
    filename_key = 'filename="'
    start_index = content_disposition.find(filename_key)
    if start_index != -1:
        start_index += len(filename_key)
        end_index = content_disposition.find('"', start_index)
        if end_index != -1:
            return content_disposition[start_index:end_index]
    return None

# Handles the multipart, chunked, upload of a file.
# The file can potentially be large, so we have to write to the file in chunks.
# Only use this for uploading a single file, not for receiving general form data.
async def handleMultipartUpload(reader, writer, request, targetFolder, timeout = 30):
    if b'Content-Type' not in request.header:
        raise HTTPServerError('No Content-Type specified!')
    contentType = request.header[b'Content-Type']
    if b'Content-Length' not in request.header:
        raise HTTPServerError('No Content-Length specified!')
    contentLength = int(request.header[b'Content-Length'])
    empty, boundary = contentType.split(b'boundary=', 1)
    if not boundary:
        raise HTTPServerError('No multipart boundary specified!')

    # Prepare for writing the file
    file_data_started = False
    file = None
    while contentLength > 0:
        # read 1K at a time
        chunk = await asyncio.wait_for(reader.read(min(1024, contentLength)), timeout)
        contentLength -= len(chunk)
        # make sure we don't land directly ocross the end boundary marker
        if contentLength > 0 and contentLength < len(boundary) + 10:
            chunk += await asyncio.wait_for(reader.read(contentLength), timeout)
        if not file_data_started:
            # Look for the beginning of the file part
            boundary_index = chunk.find(b'Content-Disposition: form-data; name="file";')
            if boundary_index != -1:
                # Find the start of the file content
                headers_end_index = chunk.find(b'\r\n\r\n', boundary_index)
                if headers_end_index != -1:
                    contentDisposition = chunk[boundary_index:headers_end_index].decode('utf-8')
                    filename = extract_filename(contentDisposition) or "uploaded_file"
                    filename = targetFolder + '/' + filename
                    file_data_started = True
                    file_data_start = headers_end_index + 4
                    file = open(filename, 'wb')
        if file_data_started:
            # Look for the end boundary
            end_boundary_index = chunk.find(b'\r\n--' + boundary)
            if end_boundary_index != -1:
                file.write(chunk[file_data_start:end_boundary_index])
                break
            else:
                file.write(chunk[file_data_start:])
                file_data_start = 0
    if file:
        file.close()
