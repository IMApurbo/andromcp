# AndroMCP 🤖📱

Android MCP server that gives Claude Code and other MCP-compatible AI assistants the ability to inspect, understand, and control Android devices through ADB.

AndroMCP allows AI agents to:

* Read Android UI hierarchies
* Analyze screens
* Tap buttons and interact with apps
* Enter text
* Take screenshots
* Manage applications
* Retrieve device information
* Automate Android workflows

---

## Features

### 📱 UI Understanding

* UI hierarchy inspection
* Search elements by:

  * Resource ID
  * Text
  * Content Description
  * Class Name
* Clickable element discovery
* UiAutomator integration
* AI-friendly structured UI analysis

### 👆 Device Interaction

* Tap elements
* Tap by visible text
* Long press
* Swipe gestures
* Scroll up/down
* Home, Back, and Recent Apps navigation
* Key event injection

### ⌨️ Text Input

* Enter text into fields
* Clipboard management
* Keyboard automation

### 📸 Screenshots & Recording

* Capture screenshots
* Record screen sessions
* Retrieve display information

### 📱 App Management

* Launch applications
* Stop applications
* Open URLs
* List installed apps
* Install APKs
* Uninstall apps
* Clear app data

### 📡 Device Management

* Multi-device support
* Battery information
* Storage information
* Android version details
* Device properties

### 🌐 Wireless ADB

* ADB over Wi-Fi
* Android 11+ wireless pairing
* Remote device connections

### ⚙️ System Controls

* Wi-Fi management
* Bluetooth management
* Brightness control
* Airplane mode
* Screen timeout settings

### 🛠 Developer Utilities

* Shell commands
* Logcat capture
* Device reboot
* Broadcast intents
* Activity launching
* File transfer tools

---

## Requirements

Before using AndroMCP, ensure you have:

* Python 3.10+
* Android SDK Platform Tools
* ADB available in PATH
* USB Debugging enabled on your Android device
* Claude Code (optional but recommended)

Verify ADB:

```bash
adb devices
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/IMApurbo/andromcp.git
cd andromcp
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install AndroMCP:

```bash
pip install .
```

Verify installation:

```bash
python -m andromcp --help
```

---

## Claude Code Setup

Add AndroMCP to Claude Code:

```bash
claude mcp add andromcp -- python -m andromcp
```

If AndroMCP is installed in a custom Python environment, use that environment's Python executable:

### Find your Python path

Linux/macOS:

```bash
which python
```

Windows:

```powershell
where python
```

Then configure Claude Code:

```bash
claude mcp add andromcp -- <python-path> -m andromcp
```

Example:

```bash
claude mcp add andromcp -- /home/user/miniconda3/envs/andromcp/bin/python -m andromcp
```

Verify:

```bash
claude mcp list
```

---

## Android Setup

Enable Developer Options:

1. Open Settings
2. Open About Phone
3. Tap Build Number 7 times

Enable USB Debugging:

1. Open Developer Options
2. Enable USB Debugging
3. Connect the device

Verify connection:

```bash
adb devices
```

Expected output:

```text
List of devices attached
XXXXXXXXXX    device
```

---

## Example Usage

### Analyze Current Screen

```text
Analyze the current Android screen.
```

### Take a Screenshot

```text
Take a screenshot of my device.
```

### Open Settings

```text
Open the Android Settings application.
```

### Fill a Login Form

```text
Find the username field and enter "admin".
```

### Show Device Information

```text
Display battery level, Android version, and storage information.
```

---

## Multi-Device Support

List connected devices:

```bash
adb devices
```

AndroMCP supports:

* USB devices
* Wireless devices
* Multiple connected devices
* Device selection

---

## Security

Some operations are intentionally protected because they can modify the device.

Examples:

* Installing APKs
* Uninstalling applications
* Clearing app data
* Running shell commands
* Rebooting devices
* Modifying system settings

Always review AI-generated actions before executing them.

---

## Troubleshooting

### Device Not Detected

```bash
adb kill-server
adb start-server
adb devices
```

### Unauthorized Device

Reconnect the device and accept the USB debugging prompt.

### Claude Code Cannot Find AndroMCP

Verify:

```bash
claude mcp list
```

Ensure the Python executable used by Claude Code is the same one where AndroMCP is installed.

---

## Logging

Logs are written to:

```text
debug.log
```

Useful for diagnosing:

* ADB connection issues
* Tool failures
* Device communication problems

---

## Repository

GitHub:

https://github.com/IMApurbo/andromcp

---

## License

MIT License

---

## Disclaimer

AndroMCP is intended for development, testing, automation, and device management on Android devices that you own or are authorized to control. Users are responsible for complying with applicable laws, policies, and security requirements.
