const apiBaseUrl = 'https://your-api-url.com';

function toggleSidebar(iconId) {
    const panel = document.getElementById('panel');
    const fileList = document.getElementById('fileList');
    const helpContent = document.getElementById('helpContent');
    const main = document.getElementById('main');

    const icons = document.querySelectorAll('.icon');
    let alreadyActive = false;

    icons.forEach(icon => {
        if (icon.id === iconId) {
            if (icon.classList.contains('active')) {
                alreadyActive = true;
                icon.classList.remove('active');
            } else {
                icon.classList.add('active');
            }
        } else {
            icon.classList.remove('active');
        }
    });

    if (alreadyActive) {
        panel.classList.add('collapsed');
        main.style.marginLeft = '56px';
    } else {
        panel.classList.remove('collapsed');
        main.style.marginLeft = '306px';
        if (iconId === 'filesIcon') {
            listFilesInSidebar();
            fileList.style.display = 'block';
            helpContent.style.display = 'none';
        } else if (iconId === 'helpIcon') {
            fileList.style.display = 'none';
            helpContent.style.display = 'block';
        }
    }
}

function listFilesInSidebar() {
    fetch(`${apiBaseUrl}/files`)
        .then(response => response.json())
        .then(data => {
            const fileListDiv = document.getElementById('fileList');
            fileListDiv.innerHTML = '';
            data.files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.textContent = file;
                fileItem.onclick = () => loadFile(file);
                fileListDiv.appendChild(fileItem);
            });
        })
        .catch(error => alert('Error listing files: ' + error));
}

export { listFilesInSidebar, toggleSidebar };
