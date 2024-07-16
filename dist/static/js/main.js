import { currentFolder, toggleSidebar, listFilesInSidebar } from "./sidebar.js";
import { renameTab, activeEditor, editors } from './editor.js';
import { createNewFileTab, updateSaveButton } from "./tabs.js";
import './repl-client.js';

const saveButton = document.getElementById("saveFileBt");
const newButton = document.getElementById("newFileBt");
const toastContainer = document.getElementById("toast-container");
const fileContextMenu = document.getElementById("file-context-menu");
const fileContextMenuTitle = document.getElementById("file-context-menu-title");
const darkOverlay = document.getElementById("dark-overlay");

const hostname = window.location.hostname;
const baseUrl = `http://${hostname}`;
const apiBaseUrl = `${baseUrl}/api`;
const userFilesLocation = baseUrl + "/files/user";

function openContextMenu(filename) {
    fileContextMenuTitle.textContent = filename;
    fileContextMenu.classList.remove("hidden");
    darkOverlay.classList.remove("hidden");

    // Attach event handlers for menu items
    document.getElementById("set-as-app").onclick = () => setAsApp(filename);
    // filename already includes subfolders in the user space
    let downloadLink = document.getElementById("download-link");
    downloadLink.href = userFilesLocation + "/" + filename;
    downloadLink.onclick = closeContextMenu;
    document.getElementById("download").onclick = () => downloadLink.click();
    document.getElementById("rename").onclick = () => renameFile(filename);
    document.getElementById("move").onclick = () => moveFile(filename);
    document.getElementById("delete").onclick = () => deleteFile(filename);
}

function closeContextMenu() {
  fileContextMenu.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

// Close the context menu when clicking outside of it
darkOverlay.onclick = closeContextMenu;

function saveFile() {
    if (!activeEditor) {
        showToast('No file is currently open.', 'warning');
        return;
    }

    if (!activeEditor.isNamed) {
      const newFilename = prompt("Enter a name for the new file:");
      if (newFilename) {
        renameTab(activeEditor.filename, newFilename);
        activeEditor.isNamed = true;
      } else {
        showToast("File name is required to save.", "warning");
        return;
      }
    }

    const filename = encodeURIComponent(activeEditor.filename); // URI encode the filename
    const content = activeEditor.editor.getValue();
    fetch(`${baseUrl}/files/user/${filename}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
    })
    .then((response) => {
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        showToast('File saved successfully!', 'info');
        activeEditor.editor.isDirty = false; // Mark editor as not dirty after saving
        updateSaveButton();
        listFilesInSidebar();  // update file list
    })
    .catch(error => showToast(error, 'error'));
}

function setAsApp(filename) {
    closeContextMenu();
    fetch(`${apiBaseUrl}/setasapp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename })
    })
    .then((response) => {
        if (!response.ok) {
            return response.json().then((data) => {
                throw new Error(data.error || 'An error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        showToast('Success!', 'info');
        listFilesInSidebar();  // update file list
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
    fetch(`${apiBaseUrl}/files/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src, dest }),
    })
    .then((response) => {
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
        listFilesInSidebar(); // update file list
    })
    .catch((error) => showToast(error, "error"));
}

function deleteFile(filename) {
    if (!confirm("Are you sure you want to delete this file?"))
        return;
    closeContextMenu();
    const fname = encodeURIComponent(filename); // URI encode the filename
    fetch(`${baseUrl}/files/user/${fname}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    })
    .then((response) => {
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
        listFilesInSidebar(); // update file list
    })
    .catch((error) => showToast(error, "error"));
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

updateSaveButton();

document.getElementById('filesIcon').onclick = () => toggleSidebar('filesIcon');
document.getElementById('helpIcon').onclick = () => toggleSidebar('helpIcon');
saveButton.onclick = saveFile;
newButton.onclick = createNewFileTab;

// Hide the loading overlay once the content is fully loaded
window.addEventListener('load', () => {
    document.getElementById('loading-overlay').style.display = 'none';
});

export { baseUrl, apiBaseUrl, saveButton, openContextMenu };
