import {
  baseUrl,
  apiBaseUrl,
  darkOverlay,
  showToast,
  showSpinners
} from "./main.js";


const wifiSettings = document.getElementById("wifi-settings-btn");
const advSettings = document.getElementById("adv-settings-btn");
const wifiSettingsDialog = document.getElementById("wifi-dialog");
const advSettingsDialog = document.getElementById("advanced-dialog");
const addSsidBtn = document.getElementById("add-ssid-btn");
const chgHostnameBtn = document.getElementById("chg-hostname-btn");
const closeWifiDialogBtn = document.getElementById("close-wifi-dialog-btn");
const closeAdvDialogBtn = document.getElementById("close-adv-dialog-btn");
const storedSSIDsDiv = document.getElementById("storedSSIDs");
const scannedSSIDsDiv = document.getElementById("scannedSSIDs");
const newSsid = document.getElementById("newSSID");
const newPassword = document.getElementById("newPassword");
const hostnameInput = document.getElementById("hostname");


function openWifiDialog() {
  wifiSettingsDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeWifiDialog;
  loadSSIDs();
}

function openAdvDialog() {
  advSettingsDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeAdvDialog;
  loadHostname();
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
        const ssidSpan = document.createElement("span");
        ssidSpan.innerHTML = `${ssid}`;
        ssidItem.appendChild(ssidSpan);
        const removeSsidBtn = document.createElement("button");
        removeSsidBtn.innerHTML = `&times;`;
        removeSsidBtn.onclick = () => removeSSID(ssid);
        ssidItem.appendChild(removeSsidBtn);
        storedSSIDsDiv.appendChild(ssidItem);
      });
      scannedSSIDsDiv.innerHTML = "";
      data.scanned.forEach((ssid) => {
        const ssidItem = document.createElement("div");
        ssidItem.classList.add("ssid-item");
        const ssidSpan = document.createElement("span");
        ssidSpan.onclick = () => populateSSID(ssid);
        ssidSpan.innerHTML = `${ssid}`;
        ssidItem.appendChild(ssidSpan);
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

function loadHostname() {
  showSpinners(true);
  fetch(`${apiBaseUrl}/hostname`)
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
      hostnameInput.value = data.hostname;
    });
}

function changeHostname() {
  const hostname = hostnameInput.value;
  if (hostname) {
    showSpinners(true);
    fetch(`${apiBaseUrl}/hostname`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ hostname: hostname }),
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
        hostnameInput.value = "";
        loadHostname();
        showToast("Change will take effect after restart.", "info");
      });
  } else {
    showToast("Please enter hostname.", "warning");
  }
}

function closeAdvDialog() {
  advSettingsDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

wifiSettings.onclick = openWifiDialog;
advSettings.onclick = openAdvDialog;
addSsidBtn.onclick = addNewSSID;
closeWifiDialogBtn.onclick = closeWifiDialog;
closeAdvDialogBtn.onclick = closeAdvDialog;
chgHostnameBtn.onclick = changeHostname;

export {
  openWifiDialog,
  loadSSIDs,
  removeSSID,
  addNewSSID,
  populateSSID,
  closeWifiDialog,
};
