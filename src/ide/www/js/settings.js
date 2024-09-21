import {
  baseUrl,
  apiBaseUrl,
  darkOverlay,
  showToast,
  showSpinners
} from "./main.js";


const wifiSettingsBtn = document.getElementById("wifi-settings-btn");
const advSettingsBtn = document.getElementById("adv-settings-btn");
const checkUpdatesBtn = document.getElementById("check-updates-btn");
const wifiSettingsDialog = document.getElementById("wifi-dialog");
const advSettingsDialog = document.getElementById("advanced-dialog");
const updatesDialog = document.getElementById("updates-dialog");
const addSsidBtn = document.getElementById("add-ssid-btn");
const chgHostnameBtn = document.getElementById("chg-hostname-btn");
const doUpdatesBtn = document.getElementById("do-updates-btn");
const closeWifiDialogBtn = document.getElementById("close-wifi-dialog-btn");
const closeAdvDialogBtn = document.getElementById("close-adv-dialog-btn");
const closeUpdDialogBtn = document.getElementById("close-upd-dialog-btn");
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

function openUpdatesDialog() {
  updatesDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeUpdDialog;
  checkForUpdates();
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

function checkForUpdates() {
  showSpinners(true);
  let installedRepos = [];
  doUpdatesBtn.disabled = true;

  // Fetch installed versions from /versions API
  fetch(`${apiBaseUrl}/versions`)
    .then((response) => {
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred fetching versions");
        });
      }
      return response.json();
    })
    .then((versionsData) => {
      // Store installed repositories
      installedRepos = versionsData.list;

      // Fetch available updates from /checkupdates API
      return fetch(`${apiBaseUrl}/checkupdates`);
    })
    .then((response) => {
      showSpinners(false);
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || "An error occurred checking updates");
        });
      }
      return response.json();
    })
    .then((checkUpdatesData) => {
      // Process and display updates
      const updatesListElement = document.getElementById("updates-list");
      updatesListElement.innerHTML = ""; // Clear previous entries
      let updatesAvailable = false;

      // Iterate over installed repos
      for (let i = 0; i < installedRepos.length; i++) {
        const repo = installedRepos[i];
        const updateTuple = checkUpdatesData[i];
        const availableVersion = updateTuple[1]; // Second entry is the available version

        const listItem = document.createElement("li");
        if (availableVersion !== null && availableVersion !== "None") {
          updatesAvailable = true;
          listItem.textContent = `${repo.name} ${repo.installed_version} -> ${availableVersion}`;
        } else {
          listItem.textContent = `${repo.name} ${repo.installed_version} (no updates)`;
        }
        updatesListElement.appendChild(listItem);
      }

      if (!updatesAvailable) {
        // No updates to perform, disable the 'Do updates' button
        doUpdatesBtn.disabled = true;
      } else {
        doUpdatesBtn.disabled = false;
      }
    })
    .catch((error) => {
      showSpinners(false);
      console.error("Error:", error);
      // Display error to the user
      showToast(error.message, "error");
    });
}


function doUpdates() {
  // TODO: check if there are any updates to do.
  // Warn the user not to turn the device off during the update.
  if (!confirm('Update will start.\nPlease do not turn off device.')) {
    return;
  }
  showSpinners(true);
  fetch(`${apiBaseUrl}/doupdates`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ 'update': 'doupdates' })  // bogus
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
      showToast("Please wait. Device will restart.", "info");
      closeUpdDialog();
      // TODO: Monitor the logs to see if we get an 'update complete' signal.
    });
}

function closeWifiDialog() {
  wifiSettingsDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

function closeAdvDialog() {
  advSettingsDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

function closeUpdDialog() {
  updatesDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
}

wifiSettingsBtn.onclick = openWifiDialog;
advSettingsBtn.onclick = openAdvDialog;
checkUpdatesBtn.onclick = openUpdatesDialog;
addSsidBtn.onclick = addNewSSID;
closeWifiDialogBtn.onclick = closeWifiDialog;
closeAdvDialogBtn.onclick = closeAdvDialog;
closeUpdDialogBtn.onclick = closeUpdDialog;
chgHostnameBtn.onclick = changeHostname;
doUpdatesBtn.onclick = doUpdates;


export {
  openWifiDialog,
  loadSSIDs,
  removeSSID,
  addNewSSID,
  populateSSID,
  closeWifiDialog,
};
