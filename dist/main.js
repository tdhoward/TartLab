import { listFilesInSidebar, toggleSidebar } from './sidebar.js';
import { createNewFileTab, updatePlusTab, updateSaveButton } from './tabs.js';
import { createTab, switchToTab, closeTab, editors, activeEditor } from './editor.js';

const saveButton = document.querySelector('#controls button');

function saveFile() {
    if (!activeEditor) {
        alert('No file is currently open.');
        return;
    }

    const filename = activeEditor.filename;
    const content = activeEditor.editor.getValue();
    fetch(`${apiBaseUrl}/files/${filename}`, {
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
updatePlusTab();
updateSaveButton(); // Ensure the Save button starts disabled

document.getElementById('filesIcon').onclick = () => toggleSidebar('filesIcon');
document.getElementById('helpIcon').onclick = () => toggleSidebar('helpIcon');
document.querySelector('#controls button').onclick = saveFile;

// Expose closeTab to the global scope
window.closeTab = closeTab;

export { saveButton };
