// Execute the real tab/save/sidebar modules without a server or new packages.
// DOM, CodeMirror and HTTP are adapters; file routing and save logic are real.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");

class Element {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.style = {};
    const classes = new Set();
    this.classList = {
      add: (...values) => values.forEach((v) => classes.add(v)),
      remove: (...values) => values.forEach((v) => classes.delete(v)),
      contains: (v) => classes.has(v),
    };
  }
  appendChild(child) { this.children.push(child); child.parent = this; }
  addEventListener() {}
  remove() { this.removed = true; }
  querySelector() { return this.closeButton ??= new Element(); }
  getAttribute(name) { return name === "data-filename" ? this.dataset.filename : null; }
  focus() {}
}

async function harness() {
  const nodes = new Map();
  const element = (id) => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const files = new Map([
    ["/files/help/grid_puzzle_levels.json", fs.readFileSync(path.join(root, "src/files/help/grid_puzzle_levels.json"), "utf8")],
    ["/files/help/grid_puzzle.py", fs.readFileSync(path.join(root, "src/files/help/grid_puzzle.py"), "utf8")],
    ["/files/help/manifest.json", fs.readFileSync(path.join(root, "src/files/help/manifest.json"), "utf8")],
  ]);
  const requests = [];
  let promptResult, closeAllowed = false, deferredSave;
  const response = (content) => ({ ok: true, text: async () => content, json: async () => JSON.parse(content) });
  const context = vm.createContext({
    console, Error,
    document: { getElementById: element, createElement: () => new Element(),
      querySelectorAll: () => [], addEventListener() {} },
    window: { location: { hostname: "fixture.invalid" }, addEventListener() {} },
    prompt: () => promptResult,
    confirm: () => closeAllowed,
    setTimeout() {},
    fetch: async (url, options = {}) => {
      const key = decodeURIComponent(new URL(url, "http://fixture.invalid").pathname);
      requests.push([key, options]);
      if (options.method === "POST") {
        files.set(key, JSON.parse(options.body).content);
        if (deferredSave) await deferredSave;
        return response("{}");
      }
      if (key.startsWith("/api/files/user")) return response(JSON.stringify({
        files: [...files.keys()].filter((p) => p.startsWith("/files/user/")).map((p) => p.slice(12)),
        folders: [],
      }));
      if (key === "/api/space") return response('{"total_bytes":100,"free_bytes":50}');
      assert.ok(files.has(key), `unexpected HTTP fixture ${key}`);
      return response(files.get(key));
    },
  });
  const noop = () => [];
  class EditorView {
    static updateListener = { of: (fn) => ({ listener: fn }) };
    constructor({ state }) { this.state = state; }
    focus() {}
    destroy() { this.destroyed = true; }
    edit(text) {
      this.state = { ...this.state, doc: { toString: () => text } };
      for (const extension of this.state.extensions.flat(Infinity)) {
        if (extension?.listener) extension.listener({ docChanged: true });
      }
    }
  }
  const codeMirror = {
    EditorState: { allowMultipleSelections: { of: noop }, create: (config) => ({ ...config, doc: { toString: () => config.doc } }) },
    EditorView, keymap: { of: noop }, indentUnit: { of: noop },
  };
  for (const name of ("highlightSpecialChars drawSelection highlightActiveLine dropCursor " +
    "rectangularSelection crosshairCursor lineNumbers highlightActiveLineGutter indentOnInput " +
    "bracketMatching foldGutter history highlightSelectionMatches autocompletion closeBrackets python").split(" ")) {
    codeMirror[name] = noop;
  }
  for (const name of ("foldKeymap defaultKeymap historyKeymap searchKeymap completionKeymap " +
    "closeBracketsKeymap lintKeymap").split(" ")) codeMirror[name] = [];
  codeMirror.indentWithTab = {};
  const cache = new Map();
  function synthetic(id, values) {
    const result = new vm.SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value);
    }, { context, identifier: id });
    cache.set(id, result);
    return result;
  }
  function resolve(specifier, parent) {
    const id = specifier.startsWith(".") ? path.resolve(path.dirname(parent.identifier), specifier) : specifier;
    if (cache.has(id)) return cache.get(id);
    if (specifier.startsWith("@codemirror/")) return synthetic(id, codeMirror);
    if (id.endsWith("repl-client.js")) return synthetic(id, { replPlayButton: element("play") });
    if (id.endsWith("cm6theme.js")) return synthetic(id, { cooldark: [] });
    if (id.endsWith("settings.js") || id.endsWith(".css")) return synthetic(id, {});
    if (id.endsWith(".svg")) return synthetic(id, { default: "fixture.svg" });
    const result = new vm.SourceTextModule(fs.readFileSync(id, "utf8"), { context, identifier: id });
    cache.set(id, result);
    return result;
  }
  const mainPath = path.join(root, "src/ide/www/js/main.js");
  const main = resolve("./main.js", { identifier: mainPath });
  await main.link(resolve);
  await main.evaluate();
  const tabs = cache.get(path.join(root, "src/ide/www/js/tabs.js")).namespace;
  const sidebar = cache.get(path.join(root, "src/ide/www/js/sidebar.js")).namespace;
  const flush = () => new Promise((done) => setImmediate(done));
  return { tabs, main: main.namespace, element, files, requests, flush,
    prompt: (value) => { promptResult = value; },
    allowClose: (value) => { closeAllowed = value; },
    holdSave: () => { let release; deferredSave = new Promise((done) => { release = done; }); return release; },
    async openHelp(filename) {
      sidebar.buildHelpPanelContent();
      await flush();
      const manifest = JSON.parse(files.get("/files/help/manifest.json"));
      const folderIndex = manifest.folders.findIndex((f) => f.entries.some((e) => e.file === filename));
      assert.ok(folderIndex >= 0, `manifest entry ${filename}`);
      const entryIndex = manifest.folders[folderIndex].entries.findIndex((e) => e.file === filename);
      // Each accordion folder is followed by its list of entries.
      element("help-accordion").children[folderIndex * 2 + 1].children[entryIndex].onclick();
      await flush();
    },
    async openUser(filename) {
      sidebar.buildFilesPanelContent();
      await flush();
      const entry = element("fileList").children.find((item) =>
        item.children[0]?.children[0]?.textContent === filename);
      assert.ok(entry, `user file entry ${filename}`);
      entry.onclick();
      await flush();
    },
    close(filename) {
      tabs.closeTab({ stopPropagation() {}, target: { getAttribute: () => filename } });
    },
  };
}

test("Help JSON saves to a renamed user copy, closes safely and reopens as text", async () => {
  const h = await harness();
  await h.openHelp("grid_puzzle_levels.json");
  const original = h.files.get("/files/help/grid_puzzle_levels.json");
  assert.equal(h.tabs.activeTab.contentType, "txt");
  assert.equal(h.main.saveButton.disabled, false, "unmodified Help can be copied");
  assert.equal(h.element("play").classList.contains("hidden"), true);
  h.prompt("my_rooms.json");
  await h.main.saveFile();
  const editor = h.tabs.editors["my_rooms.json"].editor;
  assert.equal(h.tabs.editors["grid_puzzle_levels.json"], undefined);
  assert.equal(h.tabs.activeTab.fullPath, "/files/user/my_rooms.json");
  assert.equal(h.files.get("/files/user/my_rooms.json"), original);
  editor.edit(original.replace("First Crossing", "My Crossing"));
  h.close("my_rooms.json");
  assert.ok(h.tabs.tabs["my_rooms.json"], "unsaved close refused");
  await h.main.saveFile();
  h.close("my_rooms.json");
  assert.equal(editor.destroyed, true);
  assert.equal(h.tabs.editors["my_rooms.json"], undefined);
  await h.openUser("my_rooms.json");
  assert.match(h.tabs.editors["my_rooms.json"].editor.state.doc.toString(), /My Crossing/);
  assert.equal(h.tabs.activeTab.contentType, "txt");
  h.main.openContextMenu("my_rooms.json", "file");
  assert.equal(h.element("context-set-as-app").classList.contains("hidden"), true);
  assert.equal(h.element("play").classList.contains("hidden"), true);
  assert.equal(h.files.get("/files/help/grid_puzzle_levels.json"), original);
});

test("Python Help copies remain runnable and JSON saves cannot clear another tab's edits", async () => {
  const h = await harness();
  await h.openHelp("grid_puzzle.py");
  h.prompt("my_puzzle.py");
  await h.main.saveFile();
  assert.equal(h.tabs.activeTab.contentType, "python");
  assert.equal(h.element("play").classList.contains("hidden"), false);
  h.main.openContextMenu("my_puzzle.py", "file");
  assert.equal(h.element("context-set-as-app").classList.contains("hidden"), false);
  const python = h.tabs.editors["my_puzzle.py"].editor;
  python.edit("# unsaved Python");
  h.tabs.createTab("data.json", "/files/user/data.json", "{}", "", true);
  const json = h.tabs.editors["data.json"].editor;
  json.edit('{"one":1}');
  const release = h.holdSave();
  const saving = h.main.saveFile();
  json.edit('{"two":2}');
  h.tabs.switchToTab("my_puzzle.py");
  release();
  await saving;
  assert.equal(python.isDirty, true);
  assert.equal(json.isDirty, true);
  assert.equal(h.files.get("/files/user/data.json"), '{"one":1}');
});

test("uppercase JSON extension and existing text files share editor lifecycle", async () => {
  const h = await harness();
  for (const filename of ["rooms.JSON", "notes.txt", "device.log"]) {
    h.tabs.createTab(filename, "/files/help/" + filename, "text", "", true);
    h.tabs.renameTab(filename, "copy_" + filename);
    assert.ok(h.tabs.editors["copy_" + filename]);
    const editor = h.tabs.editors["copy_" + filename].editor;
    editor.edit("edited");
    h.allowClose(true);
    h.close("copy_" + filename);
    assert.equal(editor.destroyed, true);
  }
});
