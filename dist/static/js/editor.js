import { updateSaveButton } from './tabs.js';

const tabsDiv = document.getElementById("tabs");
const editorContainerDiv = document.getElementById("editor");

const editors = {};
let activeEditor = null;

function createTab(filename, content, isNamed) {
    const tab = document.createElement('div');
    tab.className = 'tab';
    tab.dataset.filename = filename;
    tab.innerHTML = `${filename} <button class="close-tab" data-filename="${filename}">X</button>`;
    tab.onclick = () => switchToTab(filename);

    tabsDiv.appendChild(tab); // Append the new tab to the end of the tabs container

    const editorDiv = document.createElement('div');
    editorDiv.className = 'editor-instance';
    editorContainerDiv.appendChild(editorDiv);

    const editor = CodeMirror(editorDiv, {
        value: content,
        mode: 'python',
        lineNumbers: true,
        theme: 'monokai',
        autoRefresh: true,
        styleActiveLine: { nonEmpty: true },
        gutters: ["CodeMirror-linenumbers"],
        indentWithTabs: true,  // Use tabs for indentation
        tabSize: 4,            // Tab size set to 4
        indentUnit: 4          // Indent unit set to 4
    });

    editor.on('change', () => {
      editor.isDirty = true; // Mark editor as having unsaved changes
      updateSaveButton();
    });

    editor.isDirty = false; // Initial state is not dirty
    editors[filename] = { editor, tab, editorDiv, filename, isNamed };

    // Stop propagation when the close button is clicked
    tab.querySelector('.close-tab').onclick = (event) => {
        event.stopPropagation();
        closeTab(event);
    };

    switchToTab(filename);
}

function renameTab(fromFilename, toFilename) {
    editors[toFilename] = editors[fromFilename];
    editors[toFilename].filename = toFilename;
    editors[toFilename].tab.dataset.filename = toFilename;
    editors[toFilename].tab.innerHTML = `${toFilename} <button class="close-tab" data-filename="${toFilename}">X</button>`;
    delete editors[fromFilename];
}

function switchToTab(filename) {
    if (activeEditor) {
        activeEditor.editorDiv.style.display = 'none';
        activeEditor.tab.classList.remove('active');
    }
    activeEditor = editors[filename];
    activeEditor.editorDiv.style.display = 'block';
    activeEditor.tab.classList.add('active');
    activeEditor.editor.refresh();
    activeEditor.editor.focus();  // Ensure the editor gains keyboard focus
    updateSaveButton();
}

function closeTab(event) {
    event.stopPropagation();
    const filename = event.target.getAttribute('data-filename');
    const editorData = editors[filename];
    const isActive = activeEditor && activeEditor.filename === filename;

    if (editorData.editor.isDirty) {
        const confirmClose = confirm('You have unsaved changes. Are you sure you want to close this tab?');
        if (!confirmClose) {
            return; // Do not close the tab if the user cancels
        }
    }

    editorData.tab.remove();
    editorData.editorDiv.remove();
    delete editors[filename];

    if (isActive) {
        const remainingTabs = Object.keys(editors);
        if (remainingTabs.length > 0) {
            switchToTab(remainingTabs[0]);
        } else {
            activeEditor = null;
            document.querySelectorAll('.editor-instance').forEach(editorDiv => {
                editorDiv.style.display = 'none';
            });
            updateSaveButton();
        }
    }
}

document.addEventListener('click', function (event) {
    if (event.target.classList.contains('close-tab')) {
        closeTab(event);
    }
});

export { createTab, renameTab, switchToTab, closeTab, editors, activeEditor };
