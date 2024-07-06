import { createTab, switchToTab, editors } from './editor.js';
import { apiBaseUrl } from "./main.js";

const panelDiv = document.getElementById('panel');
const fileListDiv = document.getElementById('fileList');
const helpContentDiv = document.getElementById('helpContent');
const mainDiv = document.getElementById('main');
const spaceUsageContainerDiv = document.getElementById('space-usage-container');
const iconDivs = document.querySelectorAll(".icon");
const spaceUsageTextDiv = document.getElementById("space-usage-text");
const usedSpaceDiv = document.getElementById("used-space");

function toggleSidebar(iconId) {
    let alreadyActive = false;

    iconDivs.forEach(icon => {
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
        panelDiv.classList.add('collapsed');
        mainDiv.style.marginLeft = '56px';
        spaceUsageContainerDiv.style.display = 'none'; // Hide space usage bar when panel is collapsed
    } else {
        panelDiv.classList.remove('collapsed');
        mainDiv.style.marginLeft = '306px';
        if (iconId === 'filesIcon') {
            listFilesInSidebar();
            fileListDiv.style.display = 'block';
            helpContentDiv.style.display = 'none';
            spaceUsageContainerDiv.style.display = 'block'; // Show space usage bar when files panel is open
        } else if (iconId === 'helpIcon') {
            fileListDiv.style.display = 'none';
            helpContentDiv.style.display = 'block';
            spaceUsageContainerDiv.style.display = 'none'; // Hide space usage bar when help panel is open
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
            fileListDiv.innerHTML = "";
            data.files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.textContent = file;
                fileItem.className = 'file-item';
                fileItem.onclick = () => openFile(file);
                fileListDiv.appendChild(fileItem);
            });
        })
        .catch(error => {
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
                createTab(filename, content, true);
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

            spaceUsageTextDiv.innerHTML = `Used: ${usedMB} MB / ${totalMB} MB`;

            usedSpaceDiv.style.width = `${usedPercentage}%`;
            if (usedPercentage < 60) {
                usedSpaceDiv.style.backgroundColor = 'green';
            } else if (usedPercentage < 80) {
                usedSpaceDiv.style.backgroundColor = 'yellow';
            } else {
                usedSpaceDiv.style.backgroundColor = 'red';
            }
        })
        .catch(error => {
            spaceUsageTextDiv.innerHTML = '<div class="error">Can\'t connect.</div>';
            usedSpaceDiv.style.width = '0%';
        });
}

export { listFilesInSidebar, toggleSidebar };
