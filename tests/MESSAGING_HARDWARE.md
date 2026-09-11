# Nearby Chat example

`src/files/help/messaging.py` is a standalone modern LVGL example listed under
Examples in the help menu. Copy it to user files and launch `messaging.py` on
each supported ESP32 touch device. Display dimensions and radio interfaces
come from the public platform; there are no board-specific branches.

## Using the app

1. Tap **My name** to choose a nickname (up to 16 UTF-8 bytes).
2. Tap **Add group**, enter a group name, then a password. Use the keyboard's
   checkmark to advance each step. Match both values on the other devices.
   Names are case-sensitive; surrounding whitespace in group names is removed.
   Password whitespace is significant.
3. Open a group, tap **Write message**, and send with the checkmark. **Cancel**
   saves the current draft in RAM. The keyboard is bottom-aligned and at most
   160 pixels high; short screens shrink it to preserve the input field.
4. **Groups** returns to the list. All joined groups keep receiving while
   another group or the keyboard is open; the list shows unread counts.
5. **Leave** asks before removing the local membership and history. **Exit**
   resets to the launcher. Select the app from user files to run it again.

Up to eight groups are saved in `/state/espnow_chat.json`, along with the
nickname and derived group keys. Original passwords are not saved. Each group
keeps its last 20 messages and a draft in RAM; these clear on reset. Messages
allow 160 UTF-8 bytes, group names 32, and passwords 64. No control characters
are accepted. The native keyboard primarily supports Latin text.

Creating and joining are the same operation: there is no group server, owner,
membership approval or password checker. A wrong password creates an isolated
local membership that cannot authenticate the intended group's messages.
Leave and re-add a group to correct its password.

## Radio behavior and limits

The app temporarily takes over Wi-Fi on channel 6, disconnecting the station
and disabling the IDE access point while chat runs. No router or internet is
required. Reset/Exit restores normal boot behavior and configured Wi-Fi.
There is no mesh routing or offline mailbox; peers need to be nearby and awake.

The wire format uses versioned binary frames below the ESP-NOW v1 250-byte
limit. It includes a group ID, random message ID, sending MAC, nickname, text,
and a truncated HMAC-SHA256 tag. Every group uses the same radio channel.
Passwords derive authentication keys; **message contents are not encrypted**.
This example is for casual use: short passwords can be guessed, saved keys
grant membership, and duplicate suppression is a bounded RAM cache rather
than durable replay protection. It is not a secure messaging protocol.

Broadcasts are retried at most three times, 800 ms apart. Matching recipients
send authenticated application acknowledgments. **Peer received** means at
least one other group member received the message, not every member or that
any person read it. **No reply** means no confirmation arrived within the
retry window; the message may still have arrived. There is no peer roster.

## Deterministic checks

Host checks:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_messaging -q
```

Two-device checks (replace the port names as needed):

```powershell
.\.venv\Scripts\python.exe tools/messaging_device.py check --ports COM3 COM18
```

This interrupts the running apps, loads the example in RAM, and exercises
two-way delivery and ACKs, duplicates, password rejection, background groups,
native keyboard send/cancel, group/name forms, and save/reload/leave on isolated
temporary settings files. The files are removed afterward; existing user
settings and apps are not modified. Screens and radio interfaces are restored
on exit; previous apps are interrupted and can be relaunched after reset.
Radio checks assume two devices within reliable range; failures are not passes.

Results and full error details go under `tmp/messaging-check`. `result.json`
records the source hash and machine-reported display/channel/payload data.
`observations.md` is the operator form for physical typing, readability,
scrolling, layout and reset/relaunch checks. Automated UI event injection
does not certify the physical touch experience. This is a focused example-app
check, not a modern firmware release qualification.

Install and start the checked-in example on connected devices:

```powershell
.\.venv\Scripts\python.exe tools/messaging_device.py install --ports COM3 COM18
```

Only `/files/user/messaging.py` is installed, with a verified SHA-256. Any
different existing content is backed up in the host artifact directory first.
The launcher selection and other user files stay as configured. Serial ports
are released once the app reports it is running.

Protocol API references: [MicroPython ESP-NOW](https://docs.micropython.org/en/latest/library/espnow.html)
and [WLAN configuration](https://docs.micropython.org/en/latest/library/network.WLAN.html).
