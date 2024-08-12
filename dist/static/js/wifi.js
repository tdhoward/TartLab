import {
  baseUrl,
  apiBaseUrl,
  darkOverlay,
  showToast,
  showSpinners
} from "./main.js";


const wifiSettings = document.getElementById("wifi-settings-btn");
const wifiSettingsDialog = document.getElementById("wifi-dialog");
const addSsidBtn = document.getElementById("add-ssid-btn");
const closeWifiDialogBtn = document.getElementById("close-wifi-dialog-btn");
const storedSSIDsDiv = document.getElementById("storedSSIDs");
const scannedSSIDsDiv = document.getElementById("scannedSSIDs");
const newSsid = document.getElementById("newSSID");
const newPassword = document.getElementById("newPassword");


function openWifiDialog() {
  wifiSettingsDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeWifiDialog;
  loadSSIDs();
}

function loadSSIDs() {
  showSpinners(true);
  fetch(`${apiBaseUrl}/ssids`)
    .then((response) => {
      showSpinners(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred");
        });
      }
      return response.json();
    })
    .then((data) => {
      storedSSIDsDiv.innerHTML = "";
      data.stored.forEach((ssid) => {
        const ssidItem = document.createElement("div");
        ssidItem.classList.add("ssid-item");
        ssidItem.innerHTML = `
                    <span>${ssid}</span>
                    <button onclick="removeSSID('${ssid}')">X</button>
                `;
        storedSSIDsDiv.appendChild(ssidItem);
      });
      scannedSSIDsDiv.innerHTML = "";
      data.scanned.forEach((ssid) => {
        const ssidItem = document.createElement("div");
        ssidItem.classList.add("ssid-item");
        ssidItem.innerHTML = `<span onclick="populateSSID('${ssid}')">${ssid}</span>`;
        scannedSSIDsDiv.appendChild(ssidItem);
      });
    });
}

function populateSSID(ssid) {
  newSsid.value = ssid;
}

function removeSSID(ssid) {
  if (confirm(`Are you sure you want to remove SSID: ${ssid}?`)) {
    showSpinners(true);
    fetch(`${apiBaseUrl}/remove_ssid/${encodeURIComponent(ssid)}`, {
      method: "DELETE",
    })
      .then((response) => {
        showSpinners(false);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.error || "An error occurred");
          });
        }
        return response.json();
      })
      .then(() => {
        loadSSIDs();
      });
  }
}

function addNewSSID() {
  const ssid = newSsid.value;
  const password = newPassword.value;
  if (ssid && password) {
    showSpinners(true);
    fetch(`${apiBaseUrl}/add_ssid`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ssid: ssid, password: password }),
    })
      .then((response) => {
        showSpinners(false);
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.error || "An error occurred");
          });
        }
        return response.json();
      })
      .then(() => {
        newSsid.value = "";
        newPassword.value = "";
        loadSSIDs();
      });
  } else {
    showToast("Please enter both SSID and password.", 'warning');
  }
}

function closeWifiDialog() {
  wifiSettingsDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

wifiSettings.onclick = openWifiDialog;
addSsidBtn.onclick = addNewSSID;
closeWifiDialogBtn.onclick = closeWifiDialog;

export {
  openWifiDialog,
  loadSSIDs,
  removeSSID,
  addNewSSID,
  populateSSID,
  closeWifiDialog,
};
