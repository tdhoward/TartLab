import { updateSaveButton } from './tabs.js';

const editors = {};
let activeEditor = null;

function createTab(filename, content) {
    const tabsDiv = document.getElementById('tabs');
    const tab = document.createElement('div');
    tab.className = 'tab';
    tab.dataset.filename = filename;
    tab.innerHTML = `${filename} <button class="close-tab" data-filename="${filename}">X</button>`;
    tab.onclick = () => switchToTab(filename);
    tabsDiv.insertBefore(tab, tabsDiv.lastElementChild); // Insert before the "+" tab

    const editorDiv = document.createElement('div');
    editorDiv.className = 'editor-instance';
    document.getElementById('editor').appendChild(editorDiv);

    const editor = CodeMirror(editorDiv, {
        value: content,
        mode: 'python',
        lineNumbers: true,
        theme: 'monokai',
        autoRefresh: true,
        styleActiveLine: { nonEmpty: true },
        gutters: ["CodeMirror-linenumbers"]
    });

    editor.on('change', () => {
        updateSaveButton();
    });

    editors[filename] = { editor, tab, editorDiv, filename };

    // Stop propagation when the close button is clicked
    tab.querySelector('.close-tab').onclick = (event) => {
        event.stopPropagation();
        closeTab(event);
    };

    switchToTab(filename);
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
    updateSaveButton();
}

function closeTab(event) {
    event.stopPropagation();
    const filename = event.target.getAttribute('data-filename');
    const editorData = editors[filename];
    const isActive = activeEditor && activeEditor.filename === filename;

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

export { createTab, switchToTab, closeTab, editors, activeEditor };
