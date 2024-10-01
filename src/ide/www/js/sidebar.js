import { createTab, switchToTab, tabs } from "./tabs.js";
import {
  apiBaseUrl,
  imgFileTypes,
  openContextMenu,
  createFolder,
  uploadFile,
  showToast,
  showSpinners,
} from "./main.js";

const iconBar = document.getElementById("iconBar");
const iconDivs = document.querySelectorAll(".icon");

const panelDiv = document.getElementById('panel');

const panelHelpContent = document.getElementById("panel-content-help");
const helpContentDiv = document.getElementById("helpContent");

const panelSettingsContent = document.getElementById("panel-content-settings");
const settingsContentDiv = document.getElementById("settingsContent");

const panelFilesContent = document.getElementById("panel-content-files");
const panelToolbarDiv = document.getElementById("panel-toolbar");
const newFolderDiv = document.getElementById("newFolderIcon");
const uploadFileDiv = document.getElementById("uploadFileIcon");
const panelCurrentFolderDiv = document.getElementById("panel-current-folder");
const fileListDiv = document.getElementById('fileList');
const spaceUsageTextDiv = document.getElementById("space-usage-text");
const usedSpaceDiv = document.getElementById("used-space");

const mainDiv = document.getElementById("main");
const hamburgerMenuButton = document.getElementById("hamburger-menu-bt");

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
    } else {             // open the panel
        panelDiv.classList.remove('collapsed');
        mainDiv.classList.add('main-with-side-panel');
        if (iconId === 'filesIcon') {
            buildFilesPanelContent();
            panelFilesContent.style.display = "flex";
            panelHelpContent.style.display = "none";
            panelSettingsContent.style.display = "none";
        } else if (iconId === 'helpIcon') {
            panelFilesContent.style.display = "none";
            panelHelpContent.style.display = "flex";
            panelSettingsContent.style.display = "none";
        } else if (iconId === 'settingsIcon') {
            panelFilesContent.style.display = "none";
            panelHelpContent.style.display = "none";
            panelSettingsContent.style.display = "flex";
        }
    }
}

function getParentFolder(folderPath) {
    if (folderPath.endsWith("/"))
        folderPath = folderPath.slice(0, -1);  // Remove trailing slash
    const lastSlashIndex = folderPath.lastIndexOf("/"); // Find last slash
    if (lastSlashIndex < 1) // If there's no slash, return the root
        return "/";
    return folderPath.substring(0, lastSlashIndex); // Return the substring up to the last slash
}

function buildFilesPanelContent() {
    // show the current folder
    panelCurrentFolderDiv.innerHTML = "";
    const currentFolderSpan = document.createElement("span");
    currentFolderSpan.textContent = "Path: " + currentFolder;
    panelCurrentFolderDiv.appendChild(currentFolderSpan);

    let reqPath = "/files/user";
    if (currentFolder != '/')
        reqPath = reqPath + currentFolder;
    showSpinners(true);
    fetch(`${apiBaseUrl}${reqPath}`)
        .then(response => {
            showSpinners(false);
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            fileListDiv.innerHTML = "";
            let appIndex = data.app ?? -1;
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
            data.files.forEach((file, idx) => {
                let fullPath = currentFolder + "/" + file;
                fullPath = fullPath.replace(/^\/*/, "");  // get rid of leading slash

                const fileItem = document.createElement("div");
                fileItem.className = "file-item";
                fileItem.onclick = () => openFile(fullPath);

                const fileNameContainer = document.createElement("div");
                fileNameContainer.className = "file-name-container";
                const fileName = document.createElement("span");
                fileName.textContent = file;
                fileNameContainer.appendChild(fileName);

                if (idx == appIndex) {
                  const appStar = document.createElement("img");
                  appStar.src = "../img/star.svg";
                  appStar.className = "app-star";
                  fileNameContainer.appendChild(appStar);
                }

                const menuButton = document.createElement("button");
                menuButton.textContent = "☰";
                menuButton.className = "menu-button";
                menuButton.onclick = (event) => {
                  event.stopPropagation();
                  openContextMenu(fullPath, "file", idx == appIndex);
                };

                fileItem.appendChild(fileNameContainer);
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
    buildFilesPanelContent(); // refresh everything
}


function buildHelpPanelContent() {
  const helpAccordionDiv = document.getElementById("help-accordion");
  helpAccordionDiv.innerHTML = ""; // Clear existing content

  fetch("/files/help/manifest.json")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Failed to load help manifest");
      }
      return response.json();
    })
    .then((manifest) => {
      manifest.folders.forEach((folder) => {
        const folderDiv = document.createElement("div");
        folderDiv.className = "help-folder";
        folderDiv.textContent = folder["folder name"];

        const folderContentDiv = document.createElement("div");
        folderContentDiv.className = "help-folder-content";

        folder.entries.forEach((entry) => {
          const fileDiv = document.createElement("div");
          fileDiv.className = "help-file";

          const titleDiv = document.createElement("div");
          titleDiv.className = "help-file-title";
          titleDiv.textContent = entry.title;

          const subtitleDiv = document.createElement("div");
          subtitleDiv.className = "help-file-subtitle";
          subtitleDiv.textContent = entry.subtitle;

          fileDiv.appendChild(titleDiv);
          fileDiv.appendChild(subtitleDiv);
          fileDiv.onclick = () => {
            const allContentDivs = document.querySelectorAll(".help-file");
            allContentDivs.forEach((div) => div.classList.remove("active"));
            fileDiv.classList.add("active");
            openFile(entry.file, "/files/help");
          }
          folderContentDiv.appendChild(fileDiv);
        });

        folderDiv.onclick = () => {
          const allContentDivs = document.querySelectorAll(".help-folder-content");
          const allFolderDivs = document.querySelectorAll(".help-folder");

          // Collapse all folders and remove active state
          allContentDivs.forEach((div) => (div.style.display = "none"));
          allFolderDivs.forEach((div) => div.classList.remove("active"));

          // Expand the clicked folder and add active state
          folderContentDiv.style.display = "block";
          folderDiv.classList.add("active");
        };

        helpAccordionDiv.appendChild(folderDiv);
        helpAccordionDiv.appendChild(folderContentDiv);
      });
    })
    .catch((error) => {
      helpAccordionDiv.innerHTML = `<div class="error">${error.message}</div>`;
      showToast(error, "error");
    });
}


function openFile(filename, filepath='/files/user') {
    if (tabs[filename]) {
        switchToTab(filename);
    } else {
        const url = `${filepath}/${encodeURIComponent(filename)}`;
        const ext = filename.toLowerCase().split(".").pop();
        if (imgFileTypes.includes(ext)) {
            createTab(filename, url, "imglink", true);
            return;
        }
        showSpinners(true);
        fetch(url)
            .then(response => {
                showSpinners(false);
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.text();
            })
            .then(content => {
                createTab(filename, content, '', true);
            })
            .catch(error => {
                showToast(error, "error");
            });
    }
}

function fetchSpaceUsage() {
    showSpinners(true);
    fetch(`${apiBaseUrl}/space`)
    .then(response => {
        showSpinners(false);
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

newFolderDiv.onclick = createFolder;
uploadFileDiv.onclick = uploadFile;

export {
  currentFolder,
  buildFilesPanelContent,
  buildHelpPanelContent, 
  toggleSidebar,
};
