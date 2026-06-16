# AndroMCP 🤖📱

Android MCP server that gives Claude Code and other MCP-compatible AI assistants the ability to inspect, understand, and control Android devices through ADB.

AndroMCP allows AI agents to:

* Read Android UI hierarchies
* Analyze screens and app states
* Tap buttons and interact with apps
* Enter text and complete forms
* Take screenshots
* Manage applications
* Retrieve device information
* Automate Android workflows
* Navigate messaging, productivity, and social apps
* Execute multi-step tasks based on natural language instructions

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
* Screen state understanding
* Context-aware element selection

### 👆 Device Interaction

* Tap elements
* Tap by visible text
* Long press
* Swipe gestures
* Scroll up/down
* Home, Back, and Recent Apps navigation
* Key event injection
* Multi-step workflow automation

### ⌨️ Text Input

* Enter text into fields
* Clipboard management
* Keyboard automation
* Form completion
* Search field interaction

### 📸 Screenshots & Recording

* Capture screenshots
* Record screen sessions
* Retrieve display information
* Visual verification of actions

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

### Read WhatsApp Messages

```text
Open WhatsApp and tell me what unread messages I have.
```

### Reply to a Contact

```text
Open WhatsApp, find the chat with John, read the latest messages, and draft an appropriate reply.
```

### Reply Based on Conversation Context

```text
Read my latest WhatsApp messages from John and reply accordingly that I'll join the meeting in 15 minutes.
```

### Send a Message

```text
Open WhatsApp and send "I'm on my way" to Sarah.
```

### Check Notifications

```text
Review my notifications and summarize anything important.
```

### Complete a Multi-Step Task

```text
Open Gmail, find the latest email from my manager, summarize it, then create a reminder in Google Tasks.
```

### Book a Ride Workflow

```text
Open my ride-sharing app, check the estimated fare to the airport, and tell me the available options.
```

### Shopping Assistance

```text
Open Amazon, search for wireless earbuds under $100, and summarize the top results.
```

### Calendar Management

```text
Check my calendar for tomorrow and summarize all scheduled meetings.
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

Some operations are intentionally protected because they can modify the device or interact with personal data.

Examples:

* Installing APKs
* Uninstalling applications
* Clearing app data
* Running shell commands
* Rebooting devices
* Modifying system settings
* Sending messages
* Interacting with personal accounts
* Accessing notifications and app content

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
* Automation workflow errors

---

## Repository

GitHub:

https://github.com/IMApurbo/andromcp

---

## License

MIT License

---

## Disclaimer

AndroMCP is intended for development, testing, automation, and device management on Android devices that you own or are authorized to control. Features that interact with personal applications, messages, notifications, emails, or account data should only be used with appropriate authorization and user consent. Users are responsible for complying with applicable laws, policies, privacy requirements, and security obligations.
