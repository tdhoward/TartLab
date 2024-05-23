let ws;
const webreplConsole = document.getElementById('webrepl-console');
const webreplInput = document.getElementById('webrepl-input');

function toggleWebReplPanel() {
    const panel = document.getElementById('webrepl-panel');
    panel.style.maxHeight = panel.style.maxHeight === '0px' ? '400px' : '0px';
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
        webreplConsole.value += 'WebREPL error: ' + error + '\n';
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
