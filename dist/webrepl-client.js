let ws;
const webreplConsole = document.getElementById('webrepl-console');
const webreplInput = document.getElementById('webrepl-input');
let isPanelExpanded = false; // Track the state of the panel

function toggleWebReplPanel() {
    const panel = document.getElementById('webrepl-panel');
    if (isPanelExpanded) {
        panel.style.maxHeight = '50px';
    } else {
        panel.style.maxHeight = '400px';
    }
    isPanelExpanded = !isPanelExpanded; // Toggle the state
}

function connectWebRepl() {
    const hostname = window.location.hostname;
    const wsUrl = `ws://${hostname}:8266`;
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        webreplConsole.value += 'Connected to WebREPL\n';
    };
    
    ws.onmessage = (event) => {
        webreplConsole.value += event.data + '\n';
        webreplConsole.scrollTop = webreplConsole.scrollHeight;
    };
    
    ws.onclose = () => {
        webreplConsole.value += 'Disconnected from WebREPL\n';
    };
    
    ws.onerror = (error) => {
        webreplConsole.value += `WebREPL error: ${error.message || error.type}\n`;
    };
}

webreplInput.addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
        const command = webreplInput.value;
        webreplInput.value = '';
        webreplConsole.value += '> ' + command + '\n';
        ws.send(command);
    }
});

document.addEventListener('DOMContentLoaded', connectWebRepl);
