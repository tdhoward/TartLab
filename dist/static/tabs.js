import { createTab, switchToTab, closeTab, editors, activeEditor } from './editor.js';
import { saveButton } from './main.js';

let newFileCounter = 1;

function createNewFileTab() {
    const filename = `New file ${newFileCounter++}`;
    createTab(filename, '');
}

function updatePlusTab() {
    const tabsDiv = document.getElementById('tabs');
    const plusTab = document.createElement('div');
    plusTab.className = 'tab plus';
    plusTab.innerHTML = '+';
    plusTab.onclick = createNewFileTab;
    tabsDiv.appendChild(plusTab);
}

function updateSaveButton() {
    const saveButton = document.querySelector('#controls button:nth-child(2)');
    if (!activeEditor || activeEditor.editor.getValue() === '' || !activeEditor.editor.isDirty) {
        saveButton.disabled = true;
    } else {
        saveButton.disabled = false;
    }
}

export { createNewFileTab, updatePlusTab, updateSaveButton };
