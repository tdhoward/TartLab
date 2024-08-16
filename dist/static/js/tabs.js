import { saveButton } from './main.js';

let newFileCounter = 1;
const tabsDiv = document.getElementById("tabs");
const pageContainerDiv = document.getElementById("page-container");

const editors = {};
const tabs = {};
let activeTab = null;


function createNewFileTab() {
    const filename = `New file ${newFileCounter++}`;
    createTab(filename, '', 'python', false);
}

function updateSaveButton() {
    if (!activeTab || 
        activeTab.contentType != 'python' ||
        editors[activeTab.filename].editor.getValue() === '' || 
        editors[activeTab.filename].editor.isDirty == false) {
        saveButton.disabled = true;
    } else {
        saveButton.disabled = false;
    }
}

function createTab(filename, content, contentType, isNamed) {
  const tabDiv = document.createElement("div");
  tabDiv.className = "tab";
  tabDiv.dataset.filename = filename;
  tabDiv.innerHTML = `${filename} <button class="close-tab" data-filename="${filename}">&times;</button>`;
  tabDiv.onclick = () => switchToTab(filename);

  tabsDiv.appendChild(tabDiv); // Append the new tab to the end of the tabs container

  if (contentType == "") {
    // autodetect based on file extension
    const ext = filename.toLowerCase().split(".").pop();
    if (ext == "py") contentType = "python";
    else if (ext == "htm" || ext == "html") contentType = "html";
  }

  const pageDiv = document.createElement("div");
  pageDiv.className = "page-instance";
  tabs[filename] = { tabDiv, pageDiv, filename, contentType };

  if (contentType == "python") {
    createEditor(tabs[filename], content, isNamed);
  } else if (contentType == 'html') {
    createHTMLPage(tabs[filename], content);
  } else if (contentType == "imglink") {
    createImagePage(tabs[filename], content, contentType);
  } else {
    createErrorPage(tabs[filename]);
  }

  // Stop propagation when the close button is clicked
  tabDiv.querySelector(".close-tab").onclick = (event) => {
    event.stopPropagation();
    closeTab(event);
  };

  switchToTab(filename);
}

function createErrorPage(tab) {
  let pageDiv = tab.pageDiv;
  pageDiv.classList.add('error-page');
  pageDiv.innerHTML = "<b>Unable to display this file type.</b>";
  pageContainerDiv.appendChild(pageDiv);
}

function createHTMLPage(tab, content) {
  let pageDiv = tab.pageDiv;

  pageDiv.innerHTML = content;  // this ignores the head section, etc.
  pageContainerDiv.appendChild(pageDiv);
}

function createImagePage(tab, content, contentType) {
  let pageDiv = tab.pageDiv;

  const imgElement = document.createElement("img");
  imgElement.src = content;
  
  pageDiv.appendChild(imgElement);
  pageContainerDiv.appendChild(pageDiv);
}


function createEditor(tab, content, isNamed) {
  const editorDiv = tab.pageDiv;
  editorDiv.classList.add("editor-instance");
  pageContainerDiv.appendChild(editorDiv);

  const editor = CodeMirror(editorDiv, {
    value: content,
    mode: "python",
    lineNumbers: true,
    theme: "monokai",
    autoRefresh: true,
    styleActiveLine: { nonEmpty: true },
    gutters: ["CodeMirror-linenumbers"],
    indentWithTabs: true, // Use tabs for indentation
    tabSize: 4, // Tab size set to 4
    indentUnit: 4, // Indent unit set to 4
    extraKeys: {
      F11: function (cm) {
        cm.setOption("fullScreen", !cm.getOption("fullScreen"));
      },
      Esc: function (cm) {
        if (cm.getOption("fullScreen")) cm.setOption("fullScreen", false);
      },
    },
  });

  editor.on("change", () => {
    editor.isDirty = true; // Mark editor as having unsaved changes
    updateSaveButton();
  });

  editor.isDirty = false; // Initial state is not dirty
  let filename = tab.filename;
  editors[filename] = { editor, tab, isNamed };
}

function renameTab(fromFilename, toFilename) {
  if (tabs[fromFilename].contentType == "python") {
    editors[toFilename] = editors[fromFilename];
    delete editors[fromFilename];
  }
  tabs[toFilename] = tabs[fromFilename];
  tabs[toFilename].filename = toFilename;
  tabs[toFilename].tabDiv.dataset.filename = toFilename;
  tabs[
    toFilename
  ].tabDiv.innerHTML = `${toFilename} <button class="close-tab" data-filename="${toFilename}">X</button>`;
  delete tabs[fromFilename];
}

function switchToTab(filename) {
  if (activeTab) {
    activeTab.pageDiv.style.display = "none";
    activeTab.tabDiv.classList.remove("active");
  }
  activeTab = tabs[filename];
  activeTab.pageDiv.style.display = "block";
  activeTab.tabDiv.classList.add("active");
  if (activeTab.contentType == "python" && editors[filename]) {
    editors[filename].editor.refresh();
    editors[filename].editor.focus(); // Ensure the editor gains keyboard focus
    updateSaveButton();
  }
}

function closeTab(event) {
  event.stopPropagation();
  const filename = event.target.getAttribute("data-filename");
  const tab = tabs[filename];
  const isActive = activeTab && activeTab.filename === filename;
  if (tab.contentType == "python" && editors[filename]) {
    const editorObj = editors[filename];

    if (editorObj.editor.isDirty) {
      const confirmClose = confirm(
        "You have unsaved changes. Are you sure you want to close this tab?"
      );
      if (!confirmClose) {
        return; // Do not close the tab if the user cancels
      }
    }
    delete editors[filename];
  }
  tab.pageDiv.remove();
  tab.tabDiv.remove();
  delete tabs[filename];

  if (isActive) {
    const remainingTabs = Object.keys(tabs);
    if (remainingTabs.length > 0) {
      switchToTab(remainingTabs[0]);
    } else {
      activeTab = null;
      updateSaveButton();
    }
  }
}

document.addEventListener("click", function (event) {
  if (event.target.classList.contains("close-tab")) {
    closeTab(event);
  }
});

export {
  createNewFileTab,
  updateSaveButton, 
  createTab,
  renameTab,
  switchToTab,
  closeTab,
  tabs,
  editors,
  activeTab,
};
