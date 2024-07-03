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
function sendReplCommand(command) {
  // Save command to history
  if (commandHistory.length >= 10) {
    commandHistory.shift(); // Remove oldest command if history exceeds 10
  }
  commandHistory.push(command);
  historyIndex = commandHistory.length; // Reset history index

  fetch(`${apiBaseUrl}/repl`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd: command }),
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
  replConsole.value += "\n" + message;
  setPrompt(normalPrompt);
}

replConsole.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    const currentLine = replConsole.value.split("\n").pop();
    const inputCommand = currentLine.slice(4);

    if (event.shiftKey) {
      // Add current input to command buffer for multi-line command
      commandBuffer.push(inputCommand);
      replConsole.value += "\n";
      setPrompt(waitingPrompt);
    } else {
      // Handle single or multi-line command execution
      commandBuffer.push(inputCommand);
      const fullCommand = commandBuffer.join("\r\n");
      commandBuffer = [];
      sendReplCommand(fullCommand);
    }
  } else if (event.key === "ArrowUp") {
    navigateHistory(-1);
    event.preventDefault();
  } else if (event.key === "ArrowDown") {
    navigateHistory(1);
    event.preventDefault();
  }
});

replConsole.addEventListener("paste", (event) => {
  const currentLine = replConsole.value.split("\n").pop();
  const preexistingText = currentLine.slice(4);
  replConsole.value = replConsole.value.slice(0, -preexistingText.length);  // temporarily delete existing text
  const pasteText = preexistingText + event.clipboardData.getData("text");
  let pasteLines = pasteText.split("\n");
  pasteLines.forEach(line => {
    commandBuffer.push(line);
    replConsole.value += line + "\n";
    setPrompt(waitingPrompt);
  });
  event.preventDefault();
});

function navigateHistory(direction) {
  historyIndex += direction;
  if (historyIndex < 0) {
    historyIndex = 0;
  } else if (historyIndex >= commandHistory.length) {
    historyIndex = commandHistory.length;
  }

  const lines = replConsole.value.split("\n");
  lines.pop(); // remove last line
  let cmd = "";
  if (historyIndex < commandHistory.length) {
    cmd = commandHistory[historyIndex];
  }
  replConsole.value = lines.join("\n") + "\n" + normalPrompt + cmd;
  replConsole.scrollTop = replConsole.scrollHeight;
}

// Initialize the prompt
setPrompt(normalPrompt);

replHeader.onclick = () => toggleReplPanel();

export { toggleReplPanel };
