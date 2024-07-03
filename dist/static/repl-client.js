import { apiBaseUrl } from "./main.js";

const replPanel = document.getElementById("repl-panel");
const replHeader = document.getElementById("repl-header");
const replConsole = document.getElementById("repl-console");

let isPanelExpanded = false; // Track the state of the panel

let commandBuffer = [];
let commandHistory = [];
let historyIndex = -1;

const normalPrompt = ">>> ";
const waitingPrompt = "... ";
let currentPrompt = normalPrompt;
let currentIndent = 0;  // how many tabs

function setPrompt(prompt) {
  currentPrompt = prompt;
  const lastLine = replConsole.value.split("\n").pop();
  if (lastLine.startsWith(prompt))
    return;
  if (lastLine.len > 0)
    replConsole.value += "\n";
  replConsole.value += prompt;
  replConsole.scrollTop = replConsole.scrollHeight;
}

function toggleReplPanel() {
  if (isPanelExpanded) {
    replPanel.style.maxHeight = "50px";
  } else {
    replPanel.style.maxHeight = "450px";
  }
  isPanelExpanded = !isPanelExpanded; // Toggle the state
}

// Function to send REPL command
function sendReplCommand(commandArray) {
  // Save command to history
  if (commandHistory.length >= 10) {
    commandHistory.shift(); // Remove oldest command if history exceeds 10
  }
  const sendCommand = commandBuffer.join("\r\n");
  const storeCommand = commandBuffer.join("\n");
  commandHistory.push(storeCommand);
  historyIndex = commandHistory.length; // Reset history index
  currentIndent = 0;  // reset the indent

  // TODO: give some indication that we are waiting on a response from the device.
  fetch(`${apiBaseUrl}/repl`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd: sendCommand }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data && "res" in data) {
        updateReplConsole(data.res);
      } else {
        updateReplConsole("Error: No result returned");
      }
    })
    .catch((error) => updateReplConsole(`Error: ${error}`));
}

// Function to update the REPL console
function updateReplConsole(message) {
  if (message.length > 0 && !message.endsWith('\n'))
    message += '\n';
  replConsole.value += "\n" + message;
  setPrompt(normalPrompt);
}

function moveCursorToCurrentLine() {
  const currentLine = replConsole.value.split("\n").pop();
  const cursorPosition = replConsole.selectionStart;
  if (cursorPosition > (replConsole.value.length - currentLine.length)) {  // already on current line
    return;
  }
  replConsole.selectionStart = replConsole.value.length;
}

replConsole.addEventListener("keydown", (event) => {
  if (!event.ctrlKey && !event.altKey && !event.metaKey) {
    moveCursorToCurrentLine();
  }
  if (event.key === "Enter") {
    event.preventDefault();
    const currentLine = replConsole.value.split("\n").pop();
    const inputCommand = currentLine.slice(4);
    let needsAnotherLine = false;
    if (inputCommand.endsWith(":") || inputCommand.endsWith("\\")) {
      currentIndent += 1;
      needsAnotherLine = true;
    }
    if (currentPrompt === waitingPrompt) needsAnotherLine = true;
    if (inputCommand.trim() == "") needsAnotherLine = false;
    if (event.shiftKey || needsAnotherLine) {
      // Add current input to command buffer for multi-line command
      commandBuffer.push(inputCommand);
      replConsole.value += "\n";
      setPrompt(waitingPrompt);
      if (currentIndent > 0) replConsole.value += "\t".repeat(currentIndent);
    } else {
      // Handle single or multi-line command execution
      commandBuffer.push(inputCommand);
      sendReplCommand(commandBuffer);
      commandBuffer = [];
    }
  } else if (event.key === "Tab") {
    replConsole.value += "\t";
    currentIndent += 1;
    event.preventDefault();
  } else if (event.key === "ArrowUp") {
    navigateHistory(-1);
    event.preventDefault();
  } else if (event.key === "ArrowDown") {
    navigateHistory(1);
    event.preventDefault();
  } else if (event.key === "ArrowLeft") {
    const currentLine = replConsole.value.split("\n").pop();
    const cursorPosition = replConsole.selectionStart;
    if (cursorPosition < replConsole.value.length - currentLine.length + 5) {
      event.preventDefault(); // don't allow going into the prompt
      return;
    }
  } else if (event.key === "Backspace") {
    const currentLine = replConsole.value.split("\n").pop();
    const cursorPosition = replConsole.selectionStart;
    if (cursorPosition < replConsole.value.length - currentLine.length + 5) {
      event.preventDefault(); // don't allow deleting the prompt
      return;
    }
    const beforeCursor = currentLine.slice(0, cursorPosition);
    if (beforeCursor.endsWith("\t")) currentIndent -= 1;
  }
});

replConsole.addEventListener("paste", (event) => {
  const currentLine = replConsole.value.split("\n").pop();
  const preexistingText = currentLine.slice(4);
  let petLen = preexistingText.length;
  if (petLen > 0)
    replConsole.value = replConsole.value.slice(0, petLen);  // temporarily delete existing text
  const pasteText = preexistingText + event.clipboardData.getData("text");
  let pasteLines = pasteText.split("\n");
  pasteLines.forEach(line => {
    commandBuffer.push(line);
    replConsole.value += line + "\n";
    setPrompt(waitingPrompt);
  });
  event.preventDefault();
});

function countLeadingTabs(str) {
  let count = 0;
  for (let char of str) {
    if (char === "\t") {
      count++;
    } else {
      break;
    }
  }
  return count;
}

function navigateHistory(direction) {
  if (commandHistory.length == 0) return;
  historyIndex += direction;
  if (historyIndex < 0) {
    historyIndex = 0;
    return;
  } else if (historyIndex >= commandHistory.length) {
    historyIndex = commandHistory.length;
    return;
  }

  const lines = replConsole.value.split("\n");
  commandBuffer.forEach((element) => {
    lines.pop(); // remove console lines that were taken up by the multiline command
  });
  lines.pop(); // also remove the one we're currently on
  let cmd = [];
  if (historyIndex < commandHistory.length) {
    cmd = commandHistory[historyIndex].split("\n");
  }
  commandBuffer = []; // start fresh
  currentPrompt = normalPrompt;
  replConsole.value = lines.join("\n") + "\n" + currentPrompt;
  let currentCmdLine = cmd.pop(); // remove and grab the last line of the command
  if (cmd.length > 0) {
    currentPrompt = waitingPrompt;
    // step through cmd
    cmd.forEach((line) => {
      commandBuffer.push(line);
      replConsole.value += line + "\n";
      setPrompt(waitingPrompt);
    });
  }
  setPrompt(currentPrompt);
  replConsole.value += currentCmdLine;
  currentIndent = countLeadingTabs(currentCmdLine); // set indent based on number of tabs at front of currentLine
  replConsole.scrollTop = replConsole.scrollHeight;
}

// Initialize the prompt
setPrompt(normalPrompt);

replHeader.onclick = () => toggleReplPanel();

export { toggleReplPanel };
