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
        alert('No file is currently open.');
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
    .then(data => alert('File saved successfully!'))
    .catch(error => alert('Error saving file: ' + error));
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
