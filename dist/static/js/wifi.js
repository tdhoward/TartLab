import {
  baseUrl,
  apiBaseUrl,
  darkOverlay,
  showToast,
  showSpinner
} from "./main.js";


const wifiSettings = document.getElementById("wifi-settings-btn");
const wifiSettingsDialog = document.getElementById("wifi-dialog");
const addSsidBtn = document.getElementById("add-ssid-btn");
const scanSsidsBtn = document.getElementById("scan-ssids-btn");
const closeWifiDialogBtn = document.getElementById("close-wifi-dialog-btn");


function openWifiDialog() {
  wifiSettingsDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeWifiDialog;
}

function loadStoredSSIDs() {
  fetch(`${apiBaseUrl}/stored_ssids`)
    .then((response) => {
      showSpinner(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred");
        });
      }
      return response.json();
    })
    .then((data) => {
      const storedSSIDsDiv = document.getElementById("storedSSIDs");
      storedSSIDsDiv.innerHTML = "";
      data.ssids.forEach((ssid) => {
        const ssidItem = document.createElement("div");
        ssidItem.classList.add("ssid-item");
        ssidItem.innerHTML = `
                    <span>${ssid}</span>
                    <button onclick="removeSSID('${ssid}')">X</button>
                `;
        storedSSIDsDiv.appendChild(ssidItem);
      });
    });
}

function removeSSID(ssid) {
  if (confirm(`Are you sure you want to remove SSID: ${ssid}?`)) {
    fetch(`${apiBaseUrl}/remove_ssid/${encodeURIComponent(ssid)}`, {
      method: "DELETE",
    })
      .then((response) => {
        showSpinner(false);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.error || "An error occurred");
          });
        }
        return response.json();
      })
      .then(() => {
        loadStoredSSIDs();
      });
  }
}

function addNewSSID() {
  const ssid = document.getElementById("newSSID").value;
  const password = document.getElementById("newPassword").value;
  if (ssid && password) {
    fetch(`${apiBaseUrl}/add_ssid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ssid, password }),
    })
      .then((response) => {
        showSpinner(false);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.error || "An error occurred");
          });
        }
        return response.json();
      })
      .then(() => {
        document.getElementById("newSSID").value = "";
        document.getElementById("newPassword").value = "";
        loadStoredSSIDs();
      });
  } else {
    showToast("Please enter both SSID and password.", 'warning');
  }
}

function scanForSSIDs() {
  fetch("/api/scan_ssids")
    .then((response) => {
      showSpinner(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred");
        });
      }
      return response.json();
    })
    .then((data) => {
      const ssidList = data.ssids
        .map((ssid) => `<option value="${ssid}">${ssid}</option>`)
        .join("");
      const ssidSelect = document.createElement("select");
      ssidSelect.innerHTML = ssidList;
      const ssidInput = document.getElementById("newSSID");
      ssidInput.replaceWith(ssidSelect);
      ssidSelect.id = "newSSID";
    });
}

function closeWifiDialog() {
  wifiSettingsDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

wifiSettings.onclick = openWifiDialog;
addSsidBtn.onclick = addNewSSID;
scanSsidsBtn.onclick = scanForSSIDs;
closeWifiDialogBtn.onclick = closeWifiDialog;

export {
  openWifiDialog,
  loadStoredSSIDs,
  removeSSID,
  addNewSSID,
  scanForSSIDs,
  closeWifiDialog,
};
