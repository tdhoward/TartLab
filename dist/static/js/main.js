import { currentFolder, toggleSidebar, buildFilesPanelContent } from "./sidebar.js";
import { renameTab, activeTab, editors, createNewFileTab, updateSaveButton } from "./tabs.js";
import './repl-client.js';
import './wifi.js';

const saveButton = document.getElementById("saveFileBt");
const newButton = document.getElementById("newFileBt");
const toastContainer = document.getElementById("toast-container");
const contextMenu = document.getElementById("context-menu");
const contextMenuTitle = document.getElementById("context-menu-title");
const contextSetAsApp = document.getElementById("context-set-as-app");
const contextDownload = document.getElementById("context-download");
const contextDownloadLink = document.getElementById("context-download-link");
const contextRename = document.getElementById("context-rename");
const contextMove = document.getElementById("context-move");
const contextDelete = document.getElementById("context-delete");
const darkOverlay = document.getElementById("dark-overlay");
const footerSpinner = document.getElementById("footer-spinner");

const imgFileTypes = ["png","svg"];

const hostname = window.location.hostname;
const baseUrl = `http://${hostname}`;
const apiBaseUrl = `${baseUrl}/api`;
const userFilesLocation = baseUrl + "/files/user";

function stripLeadingSlashes(path) {
    return path.replace(/^\/+/, "");
}

function openContextMenu(name, type, isApp = false) {
    contextMenu.classList.remove("hidden");
    darkOverlay.classList.remove("hidden");
    darkOverlay.onclick = closeContextMenu;  // Close the context menu when clicking outside of it
    if (type == "file") {
        let filename = name
        contextMenuTitle.textContent = filename;
        // don't allow "set as app" for non-python files
        if (filename.endsWith(".py") && !isApp) {
            contextSetAsApp.onclick = () => setAsApp(filename);
            contextSetAsApp.classList.remove("hidden");
        } else {
            contextSetAsApp.classList.add("hidden");
        }
        
        // filename already includes subfolders in the user space
        contextDownloadLink.href = userFilesLocation + "/" + filename;
        contextDownloadLink.onclick = closeContextMenu;
        contextDownload.onclick = () => contextDownloadLink.click();
        contextRename.onclick = () => renameFile(filename);
        contextMove.onclick = () => moveFile(filename);
        contextDelete.onclick = () => deleteFile(filename);

        contextDownload.classList.remove("hidden");
        contextMove.classList.remove("hidden");
    }
    else if (type == "folder") {
        let foldername = name;
        contextMenuTitle.textContent = stripLeadingSlashes(foldername);
        contextSetAsApp.classList.add("hidden");
        contextDownload.classList.add("hidden");
        contextRename.onclick = () => renameFolder(foldername);
        contextMove.classList.add("hidden");  // should we allow moving whole folders? Maybe.
        contextDelete.onclick = () => deleteFolder(foldername);
    }
}

function closeContextMenu() {
  contextMenu.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}


function saveFile() {
    if (!activeTab) {
        showToast('No file is currently open.', 'warning');
        return;
    }

    if (!activeTab.isNamed) {
      let newFilename = prompt("Enter a name for the new file:");
      if (newFilename) {
        newFilename = stripLeadingSlashes(currentFolder + '/' + newFilename);  // include the current folder
        renameTab(activeTab.filename, newFilename);
        activeTab.isNamed = true;
      } else {
        showToast("File name is required to save.", "warning");
        return;
      }
    }

    const filename = encodeURIComponent(activeTab.filename); // URI encode the filename
    const content = activeTab.editor.getValue();
    showSpinners(true);
    fetch(`${baseUrl}/files/user/${filename}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
    })
    .then((response) => {
        showSpinners(false);
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        showToast('File saved successfully!', 'info');
        activeTab.editor.isDirty = false; // Mark editor as not dirty after saving
        updateSaveButton();
        buildFilesPanelContent();  // update file list
    })
    .catch(error => showToast(error, 'error'));
}

function setAsApp(filename) {
    closeContextMenu();
    showSpinners(true);
    fetch(`${apiBaseUrl}/setasapp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
    })
    .then((response) => {
        showSpinners(false);
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        showToast('Success!', 'info');
        buildFilesPanelContent();  // update file list
    })
    .catch(error => showToast(error, 'error'));
}

function renameFile(filename) {
    closeContextMenu();
    const newFilename = prompt("Enter a new name for the file:", filename);
    if (newFilename) {
        renameOrMoveFile(filename, newFilename);
    }
}

function moveFile(filename) {
    closeContextMenu();
    let newPath = prompt("Enter a new location for the file:").replace(/\\/g,"/");
    if (newPath) {
        if (!newPath.startsWith('/')) {
            newPath = currentFolder + newPath;
        }
        renameOrMoveFile(filename, newPath + '/' + filename);
    }
}

function renameOrMoveFile(srcFile, destFile) {
    let src = srcFile;
    let dest = destFile;
    showSpinners(true);
    fetch(`${apiBaseUrl}/files/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src, dest }),
    })
    .then((response) => {
        showSpinners(false);
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then((data) => {
        showToast("Success.", "info");
        // If we just moved/renamed a file that is still open, rename that tab
        if (srcFile in editors) {
            renameTab(srcFile, destFile);
        }
        buildFilesPanelContent(); // update file list
    })
    .catch((error) => showToast(error, "error"));
}

function deleteFile(filename) {
    if (!confirm("Are you sure you want to delete this file?"))
        return;
    closeContextMenu();
    const fname = encodeURIComponent(filename); // URI encode the filename
    showSpinners(true);
    fetch(`${baseUrl}/files/user/${fname}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    })
    .then((response) => {
        showSpinners(false);
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then((data) => {
        showToast("File deleted.", "info");
        // If we just deleted a file that is still open, mark that as dirty
        if (filename in editors) {
            editors[filename].editor.isDirty = true;
            updateSaveButton(); // Update the Save button state
        }
        buildFilesPanelContent(); // update file list
    })
    .catch((error) => showToast(error, "error"));
}

function createFolder() {
  let newFolderName = prompt("Enter a name for the new folder:");
  if (!newFolderName) {
    return;
  }
  newFolderName = stripLeadingSlashes(currentFolder + '/' + newFolderName);
  showSpinners(true);
  fetch(`${apiBaseUrl}/folder/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ newFolderName }),
  })
    .then((response) => {
      showSpinners(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred");
        });
      }
      return response.json();
    })
    .then((data) => {
      showToast("Folder created.", "info");
      buildFilesPanelContent(); // update file/folder list
    })
    .catch((error) => showToast(error, "error"));
}

function deleteFolder(folderName) {
    closeContextMenu();
    if (!confirm("Are you sure you want to delete this folder and all its contents?"))
        return;
    showSpinners(true);
    fetch(`${apiBaseUrl}/folder/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folderName }),
    })
    .then((response) => {
      showSpinners(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred");
        });
      }
      return response.json();
    })
    .then((data) => {
      showToast("Folder deleted.", "info");
      buildFilesPanelContent(); // update file/folder list
    })
    .catch((error) => showToast(error, "error"));
}

function renameFolder(foldername) {
    closeContextMenu();
    foldername = stripLeadingSlashes(foldername);
    const newFoldername = prompt("Enter a new name for the folder:", foldername);
    if (newFoldername) {
        let src = foldername;
        let dest = newFoldername;
        showSpinners(true);
        fetch(`${apiBaseUrl}/folder/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src, dest }),
        })
        .then((response) => {
            showSpinners(false);
            if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || "An error occurred");
            });
            }
            return response.json();
        })
        .then((data) => {
            showToast("Success.", "info");
            buildFilesPanelContent(); // update file/folder list
        })
        .catch((error) => showToast(error, "error"));
    }
}

function uploadFile() {
    const fileInput = document.getElementById("fileUploadInput");
    fileInput.click();
    fileInput.onchange = () => {
        let file = fileInput.files[0];
        if (file) {
            showSpinners(true);
            const formData = new FormData();
            formData.append("file", file);
            fileInput.value = "";  // clear it for next time
            fetch(`${apiBaseUrl}/files/upload${currentFolder}`, {
                method: "POST",
                body: formData,
            })
            .then((response) => {
                showSpinners(false);
                if (!response.ok) {
                return response.json().then((data) => {
                    throw new Error(data.error || "An error occurred");
                });
                }
                return response.json();
            })
            .then((data) => {
                showToast("Success.", "info");
                buildFilesPanelContent(); // update file/folder list
            })
            .catch((error) => showToast(error, "error"));
        }
    };
}


function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// Show all the spinners.  This is because we generally only have one spinner visible at a time.
function showSpinners(enabled) {
    const spinners = document.querySelectorAll('.spinner');
    spinners.forEach(spinner => {
        if (enabled)
            spinner.classList.remove("hidden");
        else
            spinner.classList.add("hidden");
    });
}

updateSaveButton();

document.getElementById('filesIcon').onclick = () => toggleSidebar('filesIcon');
document.getElementById('helpIcon').onclick = () => toggleSidebar('helpIcon');
document.getElementById("settingsIcon").onclick = () => toggleSidebar("settingsIcon");
saveButton.onclick = saveFile;
newButton.onclick = createNewFileTab;

// Hide the loading overlay once the content is fully loaded
window.addEventListener('load', () => {
    document.getElementById('loading-overlay').style.display = 'none';
});

window.addEventListener('beforeunload', function (e) {
    if (!editors) return;
    // Check if there are unsaved changes
    let unsavedChgs = false;
    for (const key of Object.keys(editors)) {
        if (editors[key].editor.isDirty)
            unsavedChgs = true;
    }
    if (unsavedChgs) {
        // Cancel the event and
        // show alert that the unsaved
        // changes would be lost
        e.preventDefault();
        e.returnValue = '';
    }
});

export {
  baseUrl,
  apiBaseUrl,
  imgFileTypes,
  saveButton,
  darkOverlay,
  openContextMenu,
  createFolder,
  deleteFolder,
  uploadFile,
  showToast,
  showSpinners,
};
