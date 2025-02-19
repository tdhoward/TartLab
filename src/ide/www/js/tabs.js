import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { python } from "@codemirror/lang-python";
import { linter } from "@codemirror/lint";
import { highlightSelectionMatches } from "@codemirror/search";
//import { basicSetup } from "@codemirror/basic-setup";
import { basicSetup } from "codemirror";
import { defaultKeymap } from "@codemirror/commands";

import { saveButton, saveFile } from "./main.js";
import { replPlayButton } from "./repl-client.js";

// Custom monokai theme (refine as needed)
import { EditorView as EV } from "@codemirror/view";
const monokaiTheme = EV.theme({
  "&": {
    color: "#f8f8f2",
    backgroundColor: "#272822",
  },
  ".cm-content": {
    caretColor: "#f8f8f0",
  },
  ".cm-gutters": {
    backgroundColor: "#272822",
    color: "#8f908a",
    border: "none",
  },
}, { dark: true });

let newFileCounter = 1;
const tabsDiv = document.getElementById("tabs");
const pageContainerDiv = document.getElementById("page-container");

const editors = {};
const tabs = {};
let activeTab = null;

function createNewFileTab() {
  const filename = `New file ${newFileCounter++}`;
  createTab(filename, "", "", "python", false);
}

function updateSaveButton() {
  if (
    !activeTab ||
    (activeTab.contentType != "python" && activeTab.contentType != "txt") ||
    editors[activeTab.filename].editor.state.doc.toString() === "" ||
    editors[activeTab.filename].editor.isDirty == false
  ) {
    saveButton.disabled = true;
  } else {
    saveButton.disabled = false;
  }
}

function updatePlayButtonVisibility() {
  if (
    activeTab &&
    activeTab.contentType === "python" &&
    editors[activeTab.filename].editor.state.doc.toString() != "" &&
    editors[activeTab.filename].editor.isDirty == false
  ) {
    replPlayButton.classList.remove("hidden");
  } else {
    replPlayButton.classList.add("hidden");
  }
}

function createTab(filename, fullPath, content, contentType, isNamed) {
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
    else if (ext == "txt" || ext == "log") contentType = "txt";
  }

  const pageDiv = document.createElement("div");
  pageDiv.className = "page-instance";
  tabs[filename] = { tabDiv, pageDiv, filename, contentType, fullPath };

  if (contentType == "python") {
    createEditor(tabs[filename], content, isNamed, "python");
  } else if (contentType == "html") {
    createHTMLPage(tabs[filename], content);
  } else if (contentType == "txt") {
    createEditor(tabs[filename], content, isNamed, "null");
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
  pageDiv.classList.add("error-page");
  pageDiv.innerHTML = "<b>Unable to display this file type.</b>";
  pageContainerDiv.appendChild(pageDiv);
}

function createHTMLPage(tab, content) {
  let pageDiv = tab.pageDiv;
  pageDiv.classList.add("html-page");
  pageDiv.innerHTML = content; // this ignores the head section, etc.
  pageContainerDiv.appendChild(pageDiv);
}

function createImagePage(tab, content, contentType) {
  let pageDiv = tab.pageDiv;
  pageDiv.classList.add("img-page");
  const imgElement = document.createElement("img");
  imgElement.src = content;

  pageDiv.appendChild(imgElement);
  pageContainerDiv.appendChild(pageDiv);
}

function createEditor(tab, content, isNamed, mode) {
  const editorDiv = tab.pageDiv;
  editorDiv.classList.add("editor-instance");
  pageContainerDiv.appendChild(editorDiv);

  // Listener for document changes
  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      // Mark editor as dirty (custom property)
      editor.isDirty = true;
      updateSaveButton();
      updatePlayButtonVisibility();
    }
  });

  // Language extension based on mode: either python or basic text editing
  let languageExtension = mode === "python" ? python() : [];

  // Custom keybindings (using CM6's keymap extension)
  const customKeymap = keymap.of([
    {
      key: "Ctrl-s",
      run: () => {
        saveFile();
        return true;
      },
    },
    {
      key: "Cmd-s",
      run: () => {
        saveFile();
        return true;
      },
    },
    {
      key: "Ctrl-f",
      run: () => {
        /* invoke find command */ return true;
      },
    },
    {
      key: "F11",
      run: () => {
        /* toggle fullscreen manually */ return true;
      },
    },
    {
      key: "Escape",
      run: () => {
        /* exit fullscreen if active */ return true;
      },
    },
    // Add additional bindings as required...
  ]);

  const state = EditorState.create({
    doc: content,
    extensions: [
      basicSetup,
      languageExtension,
      customKeymap,
      updateListener,
      monokaiTheme,
      // Additional extensions like linting or search can be added here
    ],
  });

  const editor = new EditorView({
    state,
    parent: editorDiv,
  });

  // Optionally custom properties
  editor.isDirty = false;

  let filename = tab.filename;
  editors[filename] = { editor, tab, isNamed };
}

function renameTab(fromFilename, toFilename) {
  if (fromFilename == toFilename) return;
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
  tabs[toFilename].tabDiv.onclick = () => switchToTab(toFilename);
  delete tabs[fromFilename];
}

function switchToTab(filename) {
  if (activeTab) {
    activeTab.pageDiv.classList.add("hidden");
    activeTab.tabDiv.classList.remove("active");
  }
  activeTab = tabs[filename];
  activeTab.pageDiv.classList.remove("hidden");
  activeTab.tabDiv.classList.add("active");
  if (activeTab.contentType == "python" && editors[filename]) {
    editors[filename].editor.refresh();
    editors[filename].editor.focus(); // Ensure the editor gains keyboard focus
  }
  updateSaveButton();
  updatePlayButtonVisibility();
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
      updatePlayButtonVisibility();
    }
  }
}

export {
  createNewFileTab,
  updateSaveButton,
  updatePlayButtonVisibility,
  createTab,
  renameTab,
  switchToTab,
  closeTab,
  tabs,
  editors,
  activeTab,
};
