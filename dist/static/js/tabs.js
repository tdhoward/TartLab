import { createTab, activeEditor } from './editor.js';
import { saveButton } from './main.js';

let newFileCounter = 1;

function createNewFileTab() {
    const filename = `New file ${newFileCounter++}`;
    createTab(filename, '', false);
}

function updateSaveButton() {
    if (!activeEditor || activeEditor.editor.getValue() === '' || !activeEditor.editor.isDirty) {
        saveButton.disabled = true;
    } else {
        saveButton.disabled = false;
    }
}

export { createNewFileTab, updateSaveButton };
