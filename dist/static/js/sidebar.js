import { createTab, switchToTab, editors } from './editor.js';
import { apiBaseUrl, openContextMenu, showToast } from "./main.js";

const panelDiv = document.getElementById('panel');
const fileListDiv = document.getElementById('fileList');
const helpContentDiv = document.getElementById('helpContent');
const mainDiv = document.getElementById('main');
const spaceUsageContainerDiv = document.getElementById('space-usage-container');
const iconDivs = document.querySelectorAll(".icon");
const spaceUsageTextDiv = document.getElementById("space-usage-text");
const usedSpaceDiv = document.getElementById("used-space");
const hamburgerMenuButton = document.getElementById("hamburger-menu-bt");
const iconBar = document.getElementById("iconBar");

var currentFolder = '/';

hamburgerMenuButton.addEventListener("click", () => {
  iconBar.classList.toggle("open");
  main.classList.toggle("iconBarOpen");
});

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

    if (alreadyActive) {  // close the panel
        panelDiv.classList.add('collapsed');
        mainDiv.classList.remove('main-with-side-panel')
        hamburgerMenuButton.classList.remove("hidden");
        spaceUsageContainerDiv.style.display = 'none'; // Hide space usage bar when panel is collapsed
    } else {             // open the panel
        panelDiv.classList.remove('collapsed');
        mainDiv.classList.add('main-with-side-panel');
        hamburgerMenuButton.classList.add('hidden');
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

function getParentFolder(folderPath) {
    // Remove any trailing slash if it exists
    if (folderPath.endsWith("/"))
        folderPath = folderPath.slice(0, -1);

    // Find the last slash
    const lastSlashIndex = folderPath.lastIndexOf("/");

    // If there's no slash, return an empty string (no parent folder)
    if (lastSlashIndex === -1)
        return "";

    // Return the substring up to the last slash
    return folderPath.substring(0, lastSlashIndex);
}

function listFilesInSidebar() {
    let reqPath = "/files/user";
    if (currentFolder != '/')
        reqPath = reqPath + currentFolder;
    fetch(`${apiBaseUrl}${reqPath}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            fileListDiv.innerHTML = "";
            data.folders.forEach(folder => {
                let fullPath;
                if (currentFolder != '/') {
                    fullPath = currentFolder + "/" + folder;
                } else {
                    fullPath = currentFolder + folder;
                }
                if (folder == '..') {
                    fullPath = getParentFolder(currentFolder);
                }

                const folderItem = document.createElement("div");
                folderItem.className = "folder-item";
                folderItem.onclick = () => changeFolder(fullPath);

                const iconTextWrapper = document.createElement("div");
                iconTextWrapper.className = "icon-text-wrapper";
                const folderIcon = document.createElement("img");
                folderIcon.src = "img/folder.svg";
                folderIcon.style.width = "1.2rem";
                folderIcon.style.height = "1.2rem";
                iconTextWrapper.appendChild(folderIcon);

                const folderName = document.createElement("span");
                folderName.style.padding = '0.5rem';
                folderName.textContent = folder;
                if (folder == '..')
                    folderName.textContent += " (parent folder)";
                iconTextWrapper.appendChild(folderName);
                folderItem.appendChild(iconTextWrapper);

                // add a context menu button, unless this is the link to the parent folder
                if (folder != '..') {
                    const menuButton = document.createElement("button");
                    menuButton.textContent = "☰";
                    menuButton.className = "menu-button";
                    menuButton.onclick = (event) => {
                      event.stopPropagation();
                      openContextMenu(fullPath, "folder");
                    };
                    folderItem.appendChild(menuButton);
                }

                fileListDiv.appendChild(folderItem);
            });
            data.files.forEach(file => {
                let fullPath = currentFolder + "/" + file;
                fullPath = fullPath.replace(/^\/*/, "");  // get rid of leading slash

                const fileItem = document.createElement("div");
                fileItem.className = "file-item";
                fileItem.onclick = () => openFile(fullPath);

                const fileName = document.createElement("span");
                fileName.textContent = file;

                const menuButton = document.createElement("button");
                menuButton.textContent = "☰";
                menuButton.className = "menu-button";
                menuButton.onclick = (event) => {
                  event.stopPropagation();
                  openContextMenu(fullPath, "file");
                };

                fileItem.appendChild(fileName);
                fileItem.appendChild(menuButton);
                fileListDiv.appendChild(fileItem);
            });
        })
        .catch(error => {
            fileListDiv.innerHTML = '<div class="error">Can\'t connect.</div>';
            showToast(error, "error");
        });

    fetchSpaceUsage(); // Fetch space usage data
}

function changeFolder(path) {
    currentFolder = path;
    listFilesInSidebar(); // refresh everything
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
                showToast(error, "error");
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
            showToast(error, "error");
        });
}

export { currentFolder, listFilesInSidebar, toggleSidebar };
