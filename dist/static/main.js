import { listFilesInSidebar, toggleSidebar } from './sidebar.js';
import { createTab, switchToTab, closeTab, editors, activeEditor } from './editor.js';
import { updateSaveButton } from './tabs.js';

const hostname = window.location.hostname;
const apiBaseUrl = `http://${hostname}/api`;

let newFileCounter = 1;

function createNewFileTab() {
    const filename = `New file ${newFileCounter++}`;
    createTab(filename, '');
}

const saveButton = document.querySelector('#controls button:nth-child(2)');

function saveFile() {
    if (!activeEditor) {
        showToast('No file is currently open.', 'warning');
        return;
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
    })
    .catch(error => showToast('Error saving file: ' + error, 'error'));
}

// Function to show toast messages
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerText = message;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

// Initially list files and add the "+" tab
listFilesInSidebar();
updateSaveButton(); // Ensure the Save button starts disabled

document.getElementById('filesIcon').onclick = () => toggleSidebar('filesIcon');
document.getElementById('helpIcon').onclick = () => toggleSidebar('helpIcon');
document.querySelector('#controls button:nth-child(2)').onclick = saveFile;
document.querySelector('#controls button:nth-child(1)').onclick = createNewFileTab;

// Hide the loading overlay once the content is fully loaded
window.addEventListener('load', () => {
    document.getElementById('loading-overlay').style.display = 'none';
});

export { saveButton };
