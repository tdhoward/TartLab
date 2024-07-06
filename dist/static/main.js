import { toggleSidebar } from './sidebar.js';
import { activeEditor } from './editor.js';
import { createNewFileTab, updateSaveButton } from "./tabs.js";
import './repl-client.js';

const saveButton = document.getElementById("saveFileBt");
const newButton = document.getElementById("newFileBt");
const toastContainer = document.getElementById("toast-container");

const hostname = window.location.hostname;
const apiBaseUrl = `http://${hostname}/api`;

let newFileCounter = 1;

function saveFile() {
    if (!activeEditor) {
        showToast('No file is currently open.', 'warning');
        return;
    }

    if (!activeEditor.isNamed) {
      const newFilename = prompt("Enter a name for the new file:");
      if (newFilename) {
        activeEditor.filename = newFilename;
        activeEditor.isNamed = true;
        activeEditor.tab.dataset.filename = newFilename;
        activeEditor.tab.innerHTML = `${newFilename} <button class="close-tab" data-filename="${newFilename}">X</button>`;
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
        updateSaveButton(); // Update the Save button state
    })
    .catch(error => showToast('Error saving file: ' + error, 'error'));
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

export { apiBaseUrl, saveButton };
