// Initialize CodeMirror
const editor = CodeMirror(document.getElementById('editor'), {
    mode: 'python',
    lineNumbers: true,
    theme: 'monokai',  // Use the monokai theme for a VSCode-like dark theme
    autoRefresh: true,  // Ensure the editor refreshes properly
    styleActiveLine: { nonEmpty: true },  // Highlight the active line
    gutters: ["CodeMirror-linenumbers"]  // Add gutter for line numbers
});

const apiBaseUrl = 'https://your-api-url.com';
let currentFile = '';

function toggleSidebar(iconId) {
    const panel = document.getElementById('panel');
    const fileList = document.getElementById('fileList');
    const helpContent = document.getElementById('helpContent');
    const main = document.getElementById('main');

    const icons = document.querySelectorAll('.icon');
    let alreadyActive = false;

    icons.forEach(icon => {
        if (icon.id === iconId) {
            if (icon.classList.contains('active')) {
                alreadyActive = true;
                icon.classList.remove('active');
            } else {
                icon.classList.add('active');
            }
        } else {
            icon.classList.remove('active');
        }
    });

    if (alreadyActive) {
        panel.classList.add('collapsed');
        main.style.marginLeft = '56px';
    } else {
        panel.classList.remove('collapsed');
        main.style.marginLeft = '306px';
        if (iconId === 'filesIcon') {
            listFiles();
            fileList.style.display = 'block';
            helpContent.style.display = 'none';
        } else if (iconId === 'helpIcon') {
            fileList.style.display = 'none';
            helpContent.style.display = 'block';
        }
    }
}

function loadFile(filename) {
    fetch(`${apiBaseUrl}/files/${filename}`)
        .then(response => response.json())
        .then(data => {
            editor.setValue(data.content);
            document.getElementById('filename').value = filename;
            currentFile = filename;
            openTab(filename);
        })
        .catch(error => alert('Error loading file: ' + error));
}

function saveFile() {
    const filename = document.getElementById('filename').value;
    if (filename) {
        const content = editor.getValue();
        fetch(`${apiBaseUrl}/files/${filename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        })
        .then(response => response.json())
        .then(data => alert('File saved successfully!'))
        .catch(error => alert('Error saving file: ' + error));
    } else {
        alert('Please enter a filename.');
    }
}

function listFiles() {
    fetch(`${apiBaseUrl}/files`)
        .then(response => response.json())
        .then(data => {
            const fileListDiv = document.getElementById('fileList');
            fileListDiv.innerHTML = '';
            data.files.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.textContent = file;
                fileItem.onclick = () => loadFile(file);
                fileListDiv.appendChild(fileItem);
            });
        })
        .catch(error => alert('Error listing files: ' + error));
}

function openTab(filename) {
    const tabsDiv = document.getElementById('tabs');
    let tab = document.querySelector(`.tab[data-filename="${filename}"]`);
    if (!tab) {
        tab = document.createElement('div');
        tab.className = 'tab';
        tab.dataset.filename = filename;
        tab.textContent = filename;
        tab.onclick = () => loadFile(filename);
        tabsDiv.appendChild(tab);
    }
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
}

// Initially list files
listFiles();

document.getElementById('filesIcon').onclick = () => toggleSidebar('filesIcon');
document.getElementById('helpIcon').onclick = () => toggleSidebar('helpIcon');
