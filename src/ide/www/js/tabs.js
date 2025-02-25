import { 
  EditorState,
} from "@codemirror/state";
import {
  EditorView,
  keymap,
  highlightSpecialChars,
  drawSelection,
  highlightActiveLine,
  dropCursor,
  rectangularSelection,
  crosshairCursor,
  lineNumbers,
  highlightActiveLineGutter,
} from "@codemirror/view";
import {
  indentOnInput,
  indentUnit,
  bracketMatching,
  foldGutter,
  foldKeymap,
} from "@codemirror/language";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import {
  autocompletion,
  completionKeymap,
  closeBrackets,
  closeBracketsKeymap,
} from "@codemirror/autocomplete";
import { lintKeymap } from "@codemirror/lint";

import { python } from "@codemirror/lang-python";
//import { linter } from "@codemirror/lint";
import { monokai as myTheme } from "./cm6theme.js";

import { saveButton, saveFile } from "./main.js";
import { replPlayButton } from "./repl-client.js";

let newFileCounter = 1;
const tabsDiv = document.getElementById("tabs");
const pageContainerDiv = document.getElementById("page-container");

const editors = {};
const tabs = {};
let activeTab = null;


const cmSetup = [
  // A line number gutter
  lineNumbers(),
  // A gutter with code folding markers
  foldGutter(),
  // Replace non-printable characters with placeholders
  highlightSpecialChars(),
  // The undo history
  history(),
  // Replace native cursor/selection with our own
  drawSelection(),
  // Show a drop cursor when dragging over the editor
  dropCursor(),
  // Allow multiple cursors/selections
  EditorState.allowMultipleSelections.of(true),
  // Re-indent lines when typing specific input
  indentOnInput(),
  // Set indentation to 4 spaces
  indentUnit.of("    "),
  // Highlight syntax with a default style
  //syntaxHighlighting(defaultHighlightStyle),
  // Highlight matching brackets near cursor
  bracketMatching(),
  // Automatically close brackets
  closeBrackets(),
  // Load the autocompletion system
  autocompletion(),
  // Allow alt-drag to select rectangular regions
  rectangularSelection(),
  // Change the cursor to a crosshair when holding alt
  crosshairCursor(),
  // Style the current line specially
  highlightActiveLine(),
  // Style the gutter for current line specially
  highlightActiveLineGutter(),
  // Highlight text that matches the selected text
  highlightSelectionMatches(),
  keymap.of([
    // Closed-brackets aware backspace
    ...closeBracketsKeymap,
    // A large set of basic bindings
    ...defaultKeymap,
    // Search-related keys
    ...searchKeymap,
    // Redo/undo keys
    ...historyKeymap,
    // Code folding bindings
    ...foldKeymap,
    // Autocompletion keys
    ...completionKeymap,
    // Keys related to the linter system
    ...lintKeymap,
  ]),
];


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

  // Listener for document changes
  const updateListener = EditorView.updateListener.of((update) => {
    if (update.docChanged) {
      // Mark editor as dirty (custom property)
      editor.isDirty = true;
      updateSaveButton();
      updatePlayButtonVisibility();
    }
  });

  const state = EditorState.create({
    doc: content,
    extensions: [
      cmSetup,
      languageExtension,
      customKeymap,
      updateListener,
      myTheme,
      keymap.of([indentWithTab]),
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
