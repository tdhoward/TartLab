import { toggleSidebar, listFilesInSidebar } from "./sidebar.js";
import { renameTab, activeEditor, editors } from './editor.js';
import { createNewFileTab, updateSaveButton } from "./tabs.js";
import './repl-client.js';

const saveButton = document.getElementById("saveFileBt");
const newButton = document.getElementById("newFileBt");
const toastContainer = document.getElementById("toast-container");
const fileContextMenu = document.getElementById("file-context-menu");
const darkOverlay = document.getElementById("dark-overlay");

const hostname = window.location.hostname;
const apiBaseUrl = `http://${hostname}/api`;

function openContextMenu(filename) {
  fileContextMenu.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");

  // Attach event handlers for menu items
  document.getElementById("set-as-app").onclick = () =>
    handleMenuAction("setAsApp", filename);
  document.getElementById("rename").onclick = () =>
    handleMenuAction("rename", filename);
  document.getElementById("move").onclick = () =>
    handleMenuAction("move", filename);
  document.getElementById("delete").onclick = () =>
    handleMenuAction("delete", filename);
}

function closeContextMenu() {
  fileContextMenu.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

function handleMenuAction(action, filename) {
  closeContextMenu();
  switch (action) {
    case "setAsApp":
      // Call your setAsApp function
      break;
    case "rename":
      // Call your rename function
      break;
    case "move":
      // Call your move function
      break;
    case "delete":
      deleteFile(filename);
      break;
  }
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
    fetch(`${apiBaseUrl}/files/user/${filename}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
    })
    .then(response => response.json())
    .then(data => {
        showToast('File saved successfully!', 'info');
        activeEditor.editor.isDirty = false; // Mark editor as not dirty after saving
        updateSaveButton();
        listFilesInSidebar();  // update file list
    })
    .catch(error => showToast('Error saving file: ' + error, 'error'));
}

function deleteFile(filename) {
    if (!confirm("Are you sure you want to delete this file?"))
        return;
    const fname = encodeURIComponent(filename); // URI encode the filename
    fetch(`${apiBaseUrl}/files/user/${fname}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
    })
    .then((response) => response.json())
    .then((data) => {
        showToast("File deleted.", "info");
        // If we just deleted a file that is still open, mark that as dirty
        if (filename in editors) {
            editors[filename].editor.isDirty = true;
            updateSaveButton(); // Update the Save button state
        }
        listFilesInSidebar(); // update file list
    })
    .catch((error) => showToast("Error deleting file: " + error, "error"));
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

export { apiBaseUrl, saveButton, openContextMenu };
