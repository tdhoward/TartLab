import { createTab, switchToTab, closeTab, editors, activeEditor } from './editor.js';
import { saveButton } from './main.js';

let newFileCounter = 1;

function createNewFileTab() {
    const filename = `New file ${newFileCounter++}`;
    createTab(filename, '');
}

function updateSaveButton() {
    const saveButton = document.querySelector('#controls button:nth-child(2)');
    if (!activeEditor || activeEditor.editor.getValue() === '' || !activeEditor.editor.isDirty) {
        saveButton.disabled = true;
    } else {
        saveButton.disabled = false;
    }
}

export { createNewFileTab, updateSaveButton };
