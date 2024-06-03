import { createTab, switchToTab, editors } from './editor.js';

const hostname = window.location.hostname;
const apiBaseUrl = `http://${hostname}/api`;

function toggleSidebar(iconId) {
    const panel = document.getElementById('panel');
    const fileList = document.getElementById('fileList');
    const helpContent = document.getElementById('helpContent');
    const main = document.getElementById('main');
    const spaceUsageContainer = document.getElementById('space-usage-container');

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
        spaceUsageContainer.style.display = 'none'; // Hide space usage bar when panel is collapsed
    } else {
        panel.classList.remove('collapsed');
        main.style.marginLeft = '306px';
        if (iconId === 'filesIcon') {
            listFilesInSidebar();
            fileList.style.display = 'block';
            helpContent.style.display = 'none';
            spaceUsageContainer.style.display = 'block'; // Show space usage bar when files panel is open
        } else if (iconId === 'helpIcon') {
            fileList.style.display = 'none';
            helpContent.style.display = 'block';
            spaceUsageContainer.style.display = 'none'; // Hide space usage bar when help panel is open
        }
    }
}

function listFilesInSidebar() {
    fetch(`${apiBaseUrl}/files/user`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const fileListDiv = document.getElementById('fileList');
            fileListDiv.innerHTML = '';
            data.files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.textContent = file;
                fileItem.className = 'file-item';
                fileItem.onclick = () => openFile(file);
                fileListDiv.appendChild(fileItem);
            });
        })
        .catch(error => {
            const fileListDiv = document.getElementById('fileList');
            fileListDiv.innerHTML = '<div class="error">Can\'t connect.</div>';
        });

    fetchSpaceUsage(); // Fetch space usage data
}

function openFile(filename) {
    if (editors[filename]) {
        switchToTab(filename);
    } else {
        fetch(`/files/user/${encodeURIComponent(filename)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.text();
            })
            .then(content => {
                createTab(filename, content);
            })
            .catch(error => {
                alert('Error opening file: ' + error);
            });
    }
}

function fetchSpaceUsage() {
    fetch(`${apiBaseUrl}/space`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const usedBytes = data.total_bytes - data.free_bytes;
            const totalBytes = data.total_bytes;
            const usedMB = (usedBytes / (1024 * 1024)).toFixed(2);
            const totalMB = (totalBytes / (1024 * 1024)).toFixed(2);
            const usedPercentage = (usedBytes / totalBytes) * 100;

            const spaceUsageText = document.getElementById('space-usage-text');
            const usedSpace = document.getElementById('used-space');

            spaceUsageText.innerHTML = `Used: ${usedMB} MB / ${totalMB} MB`;

            usedSpace.style.width = `${usedPercentage}%`;
            if (usedPercentage < 60) {
                usedSpace.style.backgroundColor = 'green';
            } else if (usedPercentage < 80) {
                usedSpace.style.backgroundColor = 'yellow';
            } else {
                usedSpace.style.backgroundColor = 'red';
            }
        })
        .catch(error => {
            const spaceUsageText = document.getElementById('space-usage-text');
            const usedSpace = document.getElementById('used-space');
            spaceUsageText.innerHTML = '<div class="error">Can\'t connect.</div>';
            usedSpace.style.width = '0%';
        });
}

export { listFilesInSidebar, toggleSidebar };
