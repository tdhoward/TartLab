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
const logDialogBtn = document.getElementById("log-dialog-btn");

const wifiSettingsDialog = document.getElementById("wifi-dialog");
const advSettingsDialog = document.getElementById("advanced-dialog");
const updatesDialog = document.getElementById("updates-dialog");
const logDialog = document.getElementById("log-dialog");

const addSsidBtn = document.getElementById("add-ssid-btn");
const chgHostnameBtn = document.getElementById("chg-hostname-btn");
const doUpdatesBtn = document.getElementById("do-updates-btn");

const closeWifiDialogBtn = document.getElementById("close-wifi-dialog-btn");
const closeAdvDialogBtn = document.getElementById("close-adv-dialog-btn");
const closeUpdDialogBtn = document.getElementById("close-upd-dialog-btn");
const closeLogDialogBtn = document.getElementById("close-log-dialog-btn");

const storedSSIDsDiv = document.getElementById("storedSSIDs");
const scannedSSIDsDiv = document.getElementById("scannedSSIDs");
const newSsid = document.getElementById("newSSID");
const newPassword = document.getElementById("newPassword");
const hostnameInput = document.getElementById("hostname");
var logContainer = document.getElementById("log-container");


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

function openLogDialog() {
  logDialog.classList.remove("hidden");
  darkOverlay.classList.remove("hidden");
  darkOverlay.onclick = closeLogDialog;
  startPollingLogs();
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
  doUpdatesBtn.disabled = true;
  doUpdatesBtn.innerHTML = 'Checking versions...'
  showSpinners(true);
  let installedRepos = [];

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

      // Process and display versions
      const updatesListElement = document.getElementById("updates-list");
      updatesListElement.innerHTML = ""; // Clear previous entries

      // Iterate over installed repos
      for (let i = 0; i < installedRepos.length; i++) {
        const repo = installedRepos[i];
        const listItem = document.createElement("li");
        listItem.textContent = `${repo.name} ${repo.installed_version}`;
        updatesListElement.appendChild(listItem);
      }
      doUpdatesBtn.innerHTML = "Checking updates...";

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
          listItem.textContent = `${repo.name} ${repo.installed_version} ⇒ ${availableVersion}`;
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
      doUpdatesBtn.innerHTML = "Do updates";
    })
    .catch((error) => {
      showSpinners(false);
      doUpdatesBtn.disabled = true;
      doUpdatesBtn.innerHTML = "Do updates";
      console.error("Error:", error);
      // Display error to the user
      showToast(error.message, "error");
    });
}


function doUpdates() {
  if (!confirm('Update will start.\nPlease do not turn off device.')) {
    return;
  }
  doUpdatesBtn.disabled = true;
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
    .then((res) => {
      showToast("Please wait. Device will restart.", "info");
      closeUpdDialog();
      // TODO: Monitor the logs to see if we get an 'update complete' signal.
    });
}


// -------- Logs stuff

var lastLogs = "";
var pollingInterval = null;

function fetchLogs() {
  var controller = new AbortController();
  var signal = controller.signal;

  var timeoutId = setTimeout(function () {
    controller.abort();
  }, 4000); // Timeout after 4 seconds

  fetch("/api/logs", { signal })
    .then((response) => {
      clearTimeout(timeoutId);

      if (!response.ok) {
        // If the response is not OK, throw an error to be caught in the catch block
        throw new Error("Network response was not ok");
      }

      return response.json();
    })
    .then((data) => {
      try {
        var newLogs = data.logs || "";
        if (newLogs !== lastLogs) {
          // Check if the user is at the bottom before updating
          var isAtBottom =
            Math.abs(
              logContainer.scrollHeight -
                logContainer.scrollTop -
                logContainer.clientHeight
            ) < 1;

          // Update the logs
          logContainer.textContent = newLogs;
          lastLogs = newLogs;

          if (isAtBottom) {
            // Scroll to the bottom
            logContainer.scrollTop = logContainer.scrollHeight;
          }
        }
      } catch (error) {
        console.error("Error processing logs:", error);
      }
    })
    .catch((error) => {
      clearTimeout(timeoutId);
      // Ignore fetch errors, but log them for debugging
      console.error("Error fetching logs:", error);
    });
}


function startPollingLogs() {
  fetchLogs(); // Fetch immediately
  pollingInterval = setInterval(fetchLogs, 5000);
}

function stopPollingLogs() {
  clearInterval(pollingInterval);
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

function closeLogDialog() {
  logDialog.classList.add("hidden");
  darkOverlay.classList.add("hidden");
  stopPollingLogs();
}

wifiSettingsBtn.onclick = openWifiDialog;
advSettingsBtn.onclick = openAdvDialog;
checkUpdatesBtn.onclick = openUpdatesDialog;
logDialogBtn.onclick = openLogDialog;

closeWifiDialogBtn.onclick = closeWifiDialog;
closeAdvDialogBtn.onclick = closeAdvDialog;
closeUpdDialogBtn.onclick = closeUpdDialog;
closeLogDialogBtn.onclick = closeLogDialog;

addSsidBtn.onclick = addNewSSID;
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
