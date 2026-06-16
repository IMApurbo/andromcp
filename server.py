"""
Android MCP Server — two-phase UI dump
Phase 1: get_ui_skeleton   → tiny structural map (ids, classes, content-descs)
Phase 2: get_element_detail / get_elements_by_class → full info for chosen nodes only
"""

import subprocess
import xml.etree.ElementTree as ET
import json
import tempfile
import os
import sys
import logging
import traceback
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ──────────────────────────────────────────────────────────────────────────────
# Logging setup — writes to ~/andro-mcp/debug.log and stderr
# ──────────────────────────────────────────────────────────────────────────────

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("android-mcp")

log.info("=" * 60)
log.info("Android MCP Server starting")
log.info(f"Python: {sys.version}")
log.info(f"PID: {os.getpid()}")
log.info(f"PATH: {os.environ.get('PATH', '(not set)')}")
log.info(f"Log file: {LOG_FILE}")
log.info("=" * 60)

mcp = FastMCP("android-mcp")
log.info("FastMCP instance created")


# ──────────────────────────────────────────────────────────────────────────────
# ADB helpers
# ──────────────────────────────────────────────────────────────────────────────

ADB = "adb"  # change to full path e.g. "/usr/lib/android-sdk/platform-tools/adb" if needed

def _adb(*args: str, timeout: int = 15) -> str:
    """Run an adb command and return stdout as a string."""
    cmd = [ADB, *args]
    log.debug(f"adb cmd: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        log.error(f"adb binary not found at '{ADB}'. Set ADB to the full path.")
        raise
    except subprocess.TimeoutExpired:
        log.error(f"adb command timed out after {timeout}s: {' '.join(cmd)}")
        raise

    log.debug(f"adb returncode: {result.returncode}")
    if result.stdout:
        log.debug(f"adb stdout: {result.stdout[:200]}")
    if result.stderr:
        log.debug(f"adb stderr: {result.stderr[:200]}")

    if result.returncode != 0:
        log.error(f"adb failed: {result.stderr.strip()}")
        raise RuntimeError(f"adb error: {result.stderr.strip()}")
    return result.stdout


def _dump_xml() -> ET.Element:
    """Pull a fresh UI dump from the device and return the parsed XML root."""
    log.info("_dump_xml: starting UI dump")
    tmp = "/sdcard/_mcp_uidump.xml"
    local = tempfile.mktemp(suffix=".xml")
    try:
        log.debug(f"_dump_xml: running uiautomator dump → {tmp}")
        _adb("shell", "uiautomator", "dump", tmp)

        log.debug(f"_dump_xml: pulling {tmp} → {local}")
        _adb("pull", tmp, local)

        log.debug(f"_dump_xml: parsing XML at {local}")
        tree = ET.parse(local)
        root = tree.getroot()
        node_count = sum(1 for _ in root.iter())
        log.info(f"_dump_xml: success — {node_count} nodes parsed")
        return root
    except Exception as e:
        log.error(f"_dump_xml failed: {e}")
        log.debug(traceback.format_exc())
        raise
    finally:
        try:
            os.remove(local)
            log.debug(f"_dump_xml: removed temp file {local}")
        except FileNotFoundError:
            pass
        try:
            _adb("shell", "rm", "-f", tmp)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Skeleton builder  (Phase 1)
# ──────────────────────────────────────────────────────────────────────────────

def _node_skeleton(node: ET.Element, depth: int = 0) -> dict:
    """
    Extract only the structural identity of a node — nothing verbose.
    Keeps the payload tiny so the AI can read the whole tree at once.
    """
    a = node.attrib
    resource_id  = a.get("resource-id", "")
    class_name   = a.get("class", "").split(".")[-1]   # short name, e.g. TextView
    content_desc = a.get("content-desc", "")
    text_preview = (a.get("text", "") or "")[:40]       # first 40 chars max
    index        = a.get("index", "")
    clickable    = a.get("clickable", "false") == "true"
    scrollable   = a.get("scrollable", "false") == "true"
    enabled      = a.get("enabled", "true") == "true"

    entry: dict = {"d": depth}
    if resource_id:   entry["id"]   = resource_id
    if class_name:    entry["cls"]  = class_name
    if content_desc:  entry["desc"] = content_desc
    if text_preview:  entry["txt"]  = text_preview
    if index:         entry["idx"]  = index
    if clickable:     entry["click"] = True
    if scrollable:    entry["scroll"] = True
    if not enabled:   entry["disabled"] = True

    children = [_node_skeleton(c, depth + 1) for c in node]
    if children:
        entry["ch"] = children
    return entry


def _collect_ids_classes(root: ET.Element) -> dict:
    """
    Walk the full tree once and collect:
      - all unique resource-ids
      - all unique class names (short)
      - all unique content-descs
    Gives the AI a quick index to query against.
    """
    ids, classes, descs = set(), set(), set()
    for node in root.iter():
        a = node.attrib
        if a.get("resource-id"):
            ids.add(a["resource-id"])
        cls = a.get("class", "").split(".")[-1]
        if cls:
            classes.add(cls)
        if a.get("content-desc"):
            descs.add(a["content-desc"])
    return {
        "resource_ids": sorted(ids),
        "classes":      sorted(classes),
        "content_descs": sorted(descs),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Rich node builder  (Phase 2)
# ──────────────────────────────────────────────────────────────────────────────

def _node_full(node: ET.Element, include_children: bool = True) -> dict:
    """Return every attribute plus optional subtree for a single node."""
    a = node.attrib
    entry = {
        "resource_id":   a.get("resource-id", ""),
        "class":         a.get("class", ""),
        "text":          a.get("text", ""),
        "content_desc":  a.get("content-desc", ""),
        "bounds":        a.get("bounds", ""),
        "index":         a.get("index", ""),
        "package":       a.get("package", ""),
        "clickable":     a.get("clickable", "false") == "true",
        "long_clickable":a.get("long-clickable", "false") == "true",
        "scrollable":    a.get("scrollable", "false") == "true",
        "enabled":       a.get("enabled", "true") == "true",
        "focusable":     a.get("focusable", "false") == "true",
        "focused":       a.get("focused", "false") == "true",
        "selected":      a.get("selected", "false") == "true",
        "checkable":     a.get("checkable", "false") == "true",
        "checked":       a.get("checked", "false") == "true",
        "password":      a.get("password", "false") == "true",
    }
    # Remove empty/False noise to keep output clean
    entry = {k: v for k, v in entry.items() if v not in ("", False, None)}

    if include_children:
        children = [_node_full(c, include_children=True) for c in node]
        if children:
            entry["children"] = children
    return entry


def _find_by_resource_id(root: ET.Element, resource_id: str) -> list[ET.Element]:
    return [n for n in root.iter() if n.attrib.get("resource-id") == resource_id]


def _find_by_class(root: ET.Element, class_fragment: str) -> list[ET.Element]:
    frag = class_fragment.lower()
    return [n for n in root.iter() if frag in n.attrib.get("class", "").lower()]


def _find_by_content_desc(root: ET.Element, desc: str) -> list[ET.Element]:
    return [n for n in root.iter() if n.attrib.get("content-desc") == desc]


def _find_by_text(root: ET.Element, text: str, exact: bool = False) -> list[ET.Element]:
    if exact:
        return [n for n in root.iter() if n.attrib.get("text") == text]
    text_lower = text.lower()
    return [n for n in root.iter() if text_lower in n.attrib.get("text", "").lower()]


# ──────────────────────────────────────────────────────────────────────────────
# MCP TOOLS
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_ui_skeleton() -> str:
    """
    PHASE 1 — Call this first.

    Dumps the Android UI hierarchy and returns a compact skeleton containing
    only the structural identity of each node (resource-id, short class name,
    content-desc, first 40 chars of text, depth, clickable/scrollable flags).

    Also returns a top-level index of every unique resource-id, class name,
    and content-desc found in the hierarchy so you can decide exactly which
    elements to query in Phase 2.

    Use the index to choose targets, then call get_element_detail() or
    get_elements_by_class() for the full information on only those elements.
    """
    log.info("TOOL get_ui_skeleton called")
    try:
        root = _dump_xml()
        skeleton = _node_skeleton(root)
        index    = _collect_ids_classes(root)
        result = json.dumps({"index": index, "skeleton": skeleton}, ensure_ascii=False)
        log.info(f"TOOL get_ui_skeleton OK — response {len(result)} bytes")
        return result
    except Exception as e:
        log.error(f"TOOL get_ui_skeleton FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_element_detail(
    resource_id:  Optional[str] = None,
    content_desc: Optional[str] = None,
    include_children: bool = True,
) -> str:
    """
    PHASE 2 — Targeted fetch by resource-id or content-desc.

    Provide exactly one of:
      resource_id  — e.g. "com.example.app:id/login_button"
      content_desc — e.g. "Search"

    Returns full detail (all attributes + optional subtree) for every matching
    node. Use include_children=False to get only the node itself.

    Prefer this over get_elements_by_class when you have a specific id/desc.
    """
    log.info(f"TOOL get_element_detail called — resource_id={resource_id!r} content_desc={content_desc!r} include_children={include_children}")
    try:
        if not resource_id and not content_desc:
            log.warning("get_element_detail: no query params provided")
            return json.dumps({"error": "Provide resource_id or content_desc."})

        root = _dump_xml()

        if resource_id:
            nodes = _find_by_resource_id(root, resource_id)
        else:
            nodes = _find_by_content_desc(root, content_desc)  # type: ignore[arg-type]

        log.info(f"get_element_detail: found {len(nodes)} node(s)")
        if not nodes:
            return json.dumps({"error": "No matching elements found.", "query": {
                "resource_id": resource_id,
                "content_desc": content_desc,
            }})

        result = json.dumps(
            [_node_full(n, include_children=include_children) for n in nodes],
            ensure_ascii=False,
        )
        log.info(f"TOOL get_element_detail OK — {len(result)} bytes")
        return result
    except Exception as e:
        log.error(f"TOOL get_element_detail FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_elements_by_class(
    class_fragment: str,
    include_children: bool = False,
    max_results: int = 30,
) -> str:
    """
    PHASE 2 — Targeted fetch by class name fragment.

    class_fragment is matched case-insensitively as a substring, e.g.:
      "TextView", "RecyclerView", "Button", "EditText"

    Returns full detail for up to max_results matching nodes.
    include_children defaults to False to keep the response concise —
    set True only if you need the subtree of each matched node.

    Use this when you want all elements of a type (e.g. all buttons).
    """
    log.info(f"TOOL get_elements_by_class called — class_fragment={class_fragment!r} max_results={max_results}")
    try:
        root = _dump_xml()
        nodes = _find_by_class(root, class_fragment)[:max_results]
        log.info(f"get_elements_by_class: found {len(nodes)} node(s)")

        if not nodes:
            return json.dumps({"error": "No elements matched.", "class_fragment": class_fragment})

        result = json.dumps(
            [_node_full(n, include_children=include_children) for n in nodes],
            ensure_ascii=False,
        )
        log.info(f"TOOL get_elements_by_class OK — {len(result)} bytes")
        return result
    except Exception as e:
        log.error(f"TOOL get_elements_by_class FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_elements_by_text(
    text: str,
    exact: bool = False,
    include_children: bool = False,
) -> str:
    """
    PHASE 2 — Targeted fetch by visible text.

    text is matched case-insensitively as a substring (exact=False) or
    verbatim (exact=True).

    Returns full detail for every element whose `text` attribute matches.
    Useful for finding a specific label, button caption, or list item.
    """
    log.info(f"TOOL get_elements_by_text called — text={text!r} exact={exact}")
    try:
        root = _dump_xml()
        nodes = _find_by_text(root, text, exact=exact)
        log.info(f"get_elements_by_text: found {len(nodes)} node(s)")

        if not nodes:
            return json.dumps({"error": "No elements matched.", "text": text, "exact": exact})

        result = json.dumps(
            [_node_full(n, include_children=include_children) for n in nodes],
            ensure_ascii=False,
        )
        log.info(f"TOOL get_elements_by_text OK — {len(result)} bytes")
        return result
    except Exception as e:
        log.error(f"TOOL get_elements_by_text FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_clickable_elements() -> str:
    """
    PHASE 2 convenience — returns all clickable elements with their
    resource-id, class, text, content-desc, and bounds.

    Useful when you want a quick action map of the current screen
    without reading the full skeleton first.
    """
    log.info("TOOL get_clickable_elements called")
    try:
        root = _dump_xml()
        clickable = [
            n for n in root.iter()
            if n.attrib.get("clickable") == "true" and n.attrib.get("enabled") == "true"
        ]
        log.info(f"get_clickable_elements: found {len(clickable)} clickable node(s)")
        results = []
        for n in clickable:
            a = n.attrib
            results.append({
                "resource_id":  a.get("resource-id", ""),
                "class":        a.get("class", "").split(".")[-1],
                "text":         a.get("text", ""),
                "content_desc": a.get("content-desc", ""),
                "bounds":       a.get("bounds", ""),
            })
        result = json.dumps(results, ensure_ascii=False)
        log.info(f"TOOL get_clickable_elements OK — {len(result)} bytes")
        return result
    except Exception as e:
        log.error(f"TOOL get_clickable_elements FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Basic action tools (tap, input, scroll, screenshot)
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def tap_element(resource_id: str) -> str:
    """
    Tap the centre of the element identified by resource_id.
    Looks up the element's bounds live, computes the centre, and sends
    an `adb shell input tap x y` command.
    """
    log.info(f"TOOL tap_element called — resource_id={resource_id!r}")
    try:
        root = _dump_xml()
        nodes = _find_by_resource_id(root, resource_id)
        if not nodes:
            log.warning(f"tap_element: element not found: {resource_id}")
            return json.dumps({"error": f"Element not found: {resource_id}"})

        bounds = nodes[0].attrib.get("bounds", "")
        log.debug(f"tap_element: bounds={bounds}")
        try:
            parts = bounds.replace("][", ",").strip("[]").split(",")
            left, top, right, bottom = map(int, parts)
            cx, cy = (left + right) // 2, (top + bottom) // 2
        except Exception as e:
            log.error(f"tap_element: cannot parse bounds '{bounds}': {e}")
            return json.dumps({"error": f"Cannot parse bounds: {bounds}"})

        log.info(f"tap_element: tapping at ({cx}, {cy})")
        _adb("shell", "input", "tap", str(cx), str(cy))
        log.info(f"TOOL tap_element OK")
        return json.dumps({"tapped": resource_id, "at": [cx, cy]})
    except Exception as e:
        log.error(f"TOOL tap_element FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_text(resource_id: str, text: str) -> str:
    """
    Tap an input field by resource_id, clear it, then type text.
    Special characters are escaped for the shell.
    """
    log.info(f"TOOL input_text called — resource_id={resource_id!r} text={text!r}")
    try:
        tap_result = json.loads(tap_element(resource_id))
        if "error" in tap_result:
            log.warning(f"input_text: tap failed: {tap_result}")
            return json.dumps(tap_result)

        log.debug("input_text: clearing field")
        _adb("shell", "input", "keyevent", "KEYCODE_CTRL_A")
        _adb("shell", "input", "keyevent", "KEYCODE_DEL")

        safe = text.replace("'", "'\\''")
        log.debug(f"input_text: typing text (escaped: {safe!r})")
        _adb("shell", "input", "text", f"'{safe}'")
        log.info("TOOL input_text OK")
        return json.dumps({"typed": text, "into": resource_id})
    except Exception as e:
        log.error(f"TOOL input_text FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def scroll_screen(direction: str = "down", steps: int = 5) -> str:
    """
    Swipe the screen.
    direction: "down" | "up" | "left" | "right"
    steps: number of 100-pixel increments (default 5 = 500px swipe)
    """
    log.info(f"TOOL scroll_screen called — direction={direction!r} steps={steps}")
    try:
        swipes = {
            "down":  ("500", "800", "500", "200"),
            "up":    ("500", "200", "500", "800"),
            "left":  ("800", "500", "200", "500"),
            "right": ("200", "500", "800", "500"),
        }
        if direction not in swipes:
            log.warning(f"scroll_screen: unknown direction '{direction}'")
            return json.dumps({"error": f"Unknown direction: {direction}. Use down/up/left/right."})
        x1, y1, x2, y2 = swipes[direction]
        log.debug(f"scroll_screen: swipe ({x1},{y1}) → ({x2},{y2}) duration={steps*100}ms")
        _adb("shell", "input", "swipe", x1, y1, x2, y2, str(steps * 100))
        log.info("TOOL scroll_screen OK")
        return json.dumps({"scrolled": direction, "steps": steps})
    except Exception as e:
        log.error(f"TOOL scroll_screen FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def take_screenshot() -> str:
    """
    Capture a screenshot, pull it to /tmp, and return the local file path.
    Useful for visual verification after actions.
    """
    log.info("TOOL take_screenshot called")
    try:
        remote = "/sdcard/_mcp_screen.png"
        local  = "/tmp/android_screen.png"
        _adb("shell", "screencap", "-p", remote)
        _adb("pull", remote, local)
        _adb("shell", "rm", "-f", remote)
        size = os.path.getsize(local) if os.path.exists(local) else -1
        log.info(f"TOOL take_screenshot OK — saved to {local} ({size} bytes)")
        return json.dumps({"screenshot": local})
    except Exception as e:
        log.error(f"TOOL take_screenshot FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


@mcp.tool()
def press_key(keycode: str) -> str:
    """
    Send a keyevent. Common keycodes:
      KEYCODE_BACK, KEYCODE_HOME, KEYCODE_ENTER,
      KEYCODE_DPAD_UP/DOWN/LEFT/RIGHT, KEYCODE_TAB
    """
    log.info(f"TOOL press_key called — keycode={keycode!r}")
    try:
        _adb("shell", "input", "keyevent", keycode)
        log.info("TOOL press_key OK")
        return json.dumps({"pressed": keycode})
    except Exception as e:
        log.error(f"TOOL press_key FAILED: {e}")
        log.debug(traceback.format_exc())
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Server config / state
# ──────────────────────────────────────────────────────────────────────────────

_config = {
    "developer_mode": False,
    "screenshot_dir": "/tmp",
    "active_device": None,   # None = default adb device
}


def _adb_device(*args: str, timeout: int = 15) -> str:
    """Run adb with the active device serial if one is selected."""
    serial = _config.get("active_device")
    if serial:
        return _adb("-s", serial, *args, timeout=timeout)
    return _adb(*args, timeout=timeout)


def _require_dev_mode() -> Optional[str]:
    if not _config["developer_mode"]:
        return json.dumps({"error": "Developer mode is disabled. Call config_set_developer_mode(true) first."})
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Device management
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def devices_list() -> str:
    """
    Discover all connected devices (USB + network).
    Returns a list of device serials, states, and basic info.
    """
    log.info("TOOL devices_list called")
    try:
        output = _adb("devices", "-l")
        lines = output.strip().splitlines()
        devices = []
        for line in lines[1:]:  # skip header
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state  = parts[1]
                info   = " ".join(parts[2:]) if len(parts) > 2 else ""
                devices.append({"serial": serial, "state": state, "info": info})
        log.info(f"devices_list: found {len(devices)} device(s)")
        return json.dumps({"devices": devices})
    except Exception as e:
        log.error(f"TOOL devices_list FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def devices_use(serial: str) -> str:
    """
    Set the active device for multi-device setups.
    All subsequent commands will target this serial until changed.
    Pass an empty string to reset to default device.
    """
    log.info(f"TOOL devices_use called — serial={serial!r}")
    _config["active_device"] = serial if serial else None
    return json.dumps({"active_device": _config["active_device"]})


@mcp.tool()
def devices_current() -> str:
    """Show which device is currently selected."""
    log.info("TOOL devices_current called")
    return json.dumps({"active_device": _config.get("active_device") or "(default)"})


@mcp.tool()
def device_info() -> str:
    """
    Return battery level, WiFi state, storage summary, Android version,
    and device model for the active device.
    """
    log.info("TOOL device_info called")
    try:
        battery_raw = _adb_device("shell", "dumpsys", "battery")
        level = next(
            (l.split(":")[1].strip() for l in battery_raw.splitlines() if "level" in l),
            "unknown",
        )
        wifi_raw = _adb_device("shell", "settings", "get", "global", "wifi_on")
        storage_raw = _adb_device("shell", "df", "/sdcard")
        model   = _adb_device("shell", "getprop", "ro.product.model").strip()
        version = _adb_device("shell", "getprop", "ro.build.version.release").strip()
        result = {
            "model":           model,
            "android_version": version,
            "battery_level":   level,
            "wifi_on":         wifi_raw.strip() == "1",
            "storage":         storage_raw.strip().splitlines()[-1] if storage_raw.strip() else "unknown",
        }
        log.info("TOOL device_info OK")
        return json.dumps(result)
    except Exception as e:
        log.error(f"TOOL device_info FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def device_properties() -> str:
    """
    Batch getprop — returns model, SoC, versions, serial, and ABI.
    """
    log.info("TOOL device_properties called")
    try:
        props = [
            "ro.product.model",
            "ro.product.brand",
            "ro.product.manufacturer",
            "ro.hardware",
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.build.fingerprint",
            "ro.serialno",
            "ro.product.cpu.abi",
            "ro.product.cpu.abilist",
        ]
        result = {}
        for prop in props:
            val = _adb_device("shell", "getprop", prop).strip()
            result[prop] = val
        log.info("TOOL device_properties OK")
        return json.dumps(result)
    except Exception as e:
        log.error(f"TOOL device_properties FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Connectivity
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def adb_connect(host: str, port: int = 5555) -> str:
    """
    Connect to a device over TCP/IP.
    host: IP address of the device.
    port: ADB port (default 5555).
    """
    log.info(f"TOOL adb_connect called — {host}:{port}")
    try:
        out = _adb("connect", f"{host}:{port}")
        log.info("TOOL adb_connect OK")
        return json.dumps({"output": out.strip()})
    except Exception as e:
        log.error(f"TOOL adb_connect FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def adb_disconnect(host: str = "", port: int = 5555) -> str:
    """
    Disconnect a network device.
    Leave host empty to disconnect all network devices.
    """
    log.info(f"TOOL adb_disconnect called — host={host!r}")
    try:
        if host:
            out = _adb("disconnect", f"{host}:{port}")
        else:
            out = _adb("disconnect")
        log.info("TOOL adb_disconnect OK")
        return json.dumps({"output": out.strip()})
    except Exception as e:
        log.error(f"TOOL adb_disconnect FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def adb_pair(host: str, port: int, pairing_code: str) -> str:
    """
    Wireless debugging pairing for Android 11+.
    host: IP address shown in Developer Options → Wireless debugging.
    port: Pairing port (NOT the connection port).
    pairing_code: 6-digit code shown on device.
    """
    log.info(f"TOOL adb_pair called — {host}:{port}")
    try:
        out = _adb("pair", f"{host}:{port}", pairing_code)
        log.info("TOOL adb_pair OK")
        return json.dumps({"output": out.strip()})
    except Exception as e:
        log.error(f"TOOL adb_pair FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def adb_tcpip(port: int = 5555) -> str:
    """
    Switch the currently connected USB device into TCP/IP mode on the given port.
    Requires developer mode.
    """
    log.info(f"TOOL adb_tcpip called — port={port}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("tcpip", str(port))
        log.info("TOOL adb_tcpip OK")
        return json.dumps({"output": out.strip(), "port": port})
    except Exception as e:
        log.error(f"TOOL adb_tcpip FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Input (extended)
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def input_tap(x: int, y: int) -> str:
    """Tap at exact screen coordinates (x, y)."""
    log.info(f"TOOL input_tap called — x={x} y={y}")
    try:
        _adb_device("shell", "input", "tap", str(x), str(y))
        log.info("TOOL input_tap OK")
        return json.dumps({"tapped": [x, y]})
    except Exception as e:
        log.error(f"TOOL input_tap FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """
    Swipe between two points.
    (x1,y1) → (x2,y2) over duration_ms milliseconds.
    """
    log.info(f"TOOL input_swipe called — ({x1},{y1})→({x2},{y2}) {duration_ms}ms")
    try:
        _adb_device("shell", "input", "swipe",
                    str(x1), str(y1), str(x2), str(y2), str(duration_ms))
        log.info("TOOL input_swipe OK")
        return json.dumps({"swiped": {"from": [x1, y1], "to": [x2, y2], "duration_ms": duration_ms}})
    except Exception as e:
        log.error(f"TOOL input_swipe FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_scroll_down() -> str:
    """Scroll down — auto-detects screen size and performs a centred swipe."""
    log.info("TOOL input_scroll_down called")
    try:
        size_raw = _adb_device("shell", "wm", "size").strip()
        # e.g. "Physical size: 1080x2340"
        parts = size_raw.split(":")[-1].strip().split("x")
        w, h = int(parts[0]), int(parts[1])
        cx = w // 2
        _adb_device("shell", "input", "swipe",
                    str(cx), str(int(h * 0.7)), str(cx), str(int(h * 0.3)), "400")
        log.info("TOOL input_scroll_down OK")
        return json.dumps({"scrolled": "down"})
    except Exception as e:
        log.error(f"TOOL input_scroll_down FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_scroll_up() -> str:
    """Scroll up — auto-detects screen size and performs a centred swipe."""
    log.info("TOOL input_scroll_up called")
    try:
        size_raw = _adb_device("shell", "wm", "size").strip()
        parts = size_raw.split(":")[-1].strip().split("x")
        w, h = int(parts[0]), int(parts[1])
        cx = w // 2
        _adb_device("shell", "input", "swipe",
                    str(cx), str(int(h * 0.3)), str(cx), str(int(h * 0.7)), "400")
        log.info("TOOL input_scroll_up OK")
        return json.dumps({"scrolled": "up"})
    except Exception as e:
        log.error(f"TOOL input_scroll_up FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_back() -> str:
    """Press the Back button."""
    log.info("TOOL input_back called")
    try:
        _adb_device("shell", "input", "keyevent", "KEYCODE_BACK")
        log.info("TOOL input_back OK")
        return json.dumps({"pressed": "BACK"})
    except Exception as e:
        log.error(f"TOOL input_back FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_home() -> str:
    """Press the Home button."""
    log.info("TOOL input_home called")
    try:
        _adb_device("shell", "input", "keyevent", "KEYCODE_HOME")
        log.info("TOOL input_home OK")
        return json.dumps({"pressed": "HOME"})
    except Exception as e:
        log.error(f"TOOL input_home FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_recent_apps() -> str:
    """Open the recent apps / app switcher."""
    log.info("TOOL input_recent_apps called")
    try:
        _adb_device("shell", "input", "keyevent", "KEYCODE_APP_SWITCH")
        log.info("TOOL input_recent_apps OK")
        return json.dumps({"pressed": "RECENT_APPS"})
    except Exception as e:
        log.error(f"TOOL input_recent_apps FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_long_press(x: int, y: int, duration_ms: int = 1000) -> str:
    """
    Long press at coordinates (x, y) for duration_ms milliseconds.
    Requires developer mode.
    """
    log.info(f"TOOL input_long_press called — ({x},{y}) {duration_ms}ms")
    err = _require_dev_mode()
    if err:
        return err
    try:
        _adb_device("shell", "input", "swipe",
                    str(x), str(y), str(x), str(y), str(duration_ms))
        log.info("TOOL input_long_press OK")
        return json.dumps({"long_pressed": [x, y], "duration_ms": duration_ms})
    except Exception as e:
        log.error(f"TOOL input_long_press FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def input_key(keycode: str) -> str:
    """
    Send any key event by name, e.g. VOLUME_UP, VOLUME_DOWN, ENTER,
    KEYCODE_CAMERA, KEYCODE_DPAD_UP, etc.
    """
    log.info(f"TOOL input_key called — keycode={keycode!r}")
    try:
        # Accept both "VOLUME_UP" and "KEYCODE_VOLUME_UP"
        kc = keycode if keycode.startswith("KEYCODE_") else f"KEYCODE_{keycode}"
        _adb_device("shell", "input", "keyevent", kc)
        log.info("TOOL input_key OK")
        return json.dumps({"sent_keyevent": kc})
    except Exception as e:
        log.error(f"TOOL input_key FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def tap_text(text: str, exact: bool = False) -> str:
    """
    Find an element by its visible text and tap its centre.
    exact=False (default) does a case-insensitive substring match.
    exact=True requires an exact match.
    """
    log.info(f"TOOL tap_text called — text={text!r} exact={exact}")
    try:
        root = _dump_xml()
        nodes = _find_by_text(root, text, exact=exact)
        if not nodes:
            return json.dumps({"error": f"No element with text={text!r} found."})

        bounds = nodes[0].attrib.get("bounds", "")
        parts  = bounds.replace("][", ",").strip("[]").split(",")
        left, top, right, bottom = map(int, parts)
        cx, cy = (left + right) // 2, (top + bottom) // 2
        _adb_device("shell", "input", "tap", str(cx), str(cy))
        log.info(f"TOOL tap_text OK — tapped '{text}' at ({cx},{cy})")
        return json.dumps({"tapped_text": text, "at": [cx, cy]})
    except Exception as e:
        log.error(f"TOOL tap_text FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def clipboard_set(text: str, auto_paste: bool = False) -> str:
    """
    Set the clipboard to text (handles special characters safely).
    auto_paste=True will also send Ctrl+V after setting.
    """
    log.info(f"TOOL clipboard_set called — text={text!r} auto_paste={auto_paste}")
    try:
        # Use am broadcast to set clipboard safely
        escaped = text.replace("'", "'\\''").replace('"', '\\"')
        _adb_device("shell", "am", "broadcast",
                    "-a", "clipper.set",
                    "-e", "text", f"'{escaped}'")
        if auto_paste:
            _adb_device("shell", "input", "keyevent", "KEYCODE_CTRL_V")
        log.info("TOOL clipboard_set OK")
        return json.dumps({"clipboard": text, "auto_pasted": auto_paste})
    except Exception as e:
        log.error(f"TOOL clipboard_set FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def clipboard_get() -> str:
    """Read the current clipboard contents."""
    log.info("TOOL clipboard_get called")
    try:
        # Works on Android 10+ via input manager shell
        out = _adb_device("shell",
            "am", "broadcast", "-a", "clipper.get")
        # Fallback: try service call clipboard
        result_raw = _adb_device("shell",
            "service", "call", "clipboard", "2", "i32", "1", "i32", "0", "i32", "0")
        log.info("TOOL clipboard_get OK")
        return json.dumps({"clipboard_raw": result_raw.strip(),
                           "broadcast_output": out.strip()})
    except Exception as e:
        log.error(f"TOOL clipboard_get FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Apps
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def app_launch(package: str, activity: str = "") -> str:
    """
    Launch an app by package name.
    Optionally specify a fully-qualified activity to start a specific screen.
    Example: app_launch("com.android.settings")
    """
    log.info(f"TOOL app_launch called — package={package!r} activity={activity!r}")
    try:
        if activity:
            _adb_device("shell", "am", "start", "-n", f"{package}/{activity}")
        else:
            _adb_device("shell", "monkey", "-p", package,
                        "-c", "android.intent.category.LAUNCHER", "1")
        log.info("TOOL app_launch OK")
        return json.dumps({"launched": package, "activity": activity or "(default)"})
    except Exception as e:
        log.error(f"TOOL app_launch FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_open_url(url: str) -> str:
    """Open a URL in the default browser (or the app registered for that scheme)."""
    log.info(f"TOOL app_open_url called — url={url!r}")
    try:
        _adb_device("shell", "am", "start",
                    "-a", "android.intent.action.VIEW",
                    "-d", url)
        log.info("TOOL app_open_url OK")
        return json.dumps({"opened_url": url})
    except Exception as e:
        log.error(f"TOOL app_open_url FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_close(package: str) -> str:
    """Force stop an app by package name."""
    log.info(f"TOOL app_close called — package={package!r}")
    try:
        _adb_device("shell", "am", "force-stop", package)
        log.info("TOOL app_close OK")
        return json.dumps({"stopped": package})
    except Exception as e:
        log.error(f"TOOL app_close FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_current() -> str:
    """Get the package name and activity of the currently focused / foreground app."""
    log.info("TOOL app_current called")
    try:
        out = _adb_device("shell",
            "dumpsys", "window", "windows")
        # Look for "mCurrentFocus" or "mFocusedApp"
        package, activity = "", ""
        for line in out.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                # Typical format: u0 com.package.name/com.package.name.MainActivity
                import re
                m = re.search(r"(\S+)/(\S+)", line)
                if m:
                    package  = m.group(1)
                    activity = m.group(2)
                    break
        log.info("TOOL app_current OK")
        return json.dumps({"package": package, "activity": activity})
    except Exception as e:
        log.error(f"TOOL app_current FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_list_packages(filter_str: str = "", system: bool = False) -> str:
    """
    List installed packages.
    filter_str: optional substring to filter package names.
    system: if True, include system packages; otherwise only user-installed.
    Requires developer mode.
    """
    log.info(f"TOOL app_list_packages called — filter={filter_str!r} system={system}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        flag = "" if system else "-3"
        args = ["shell", "pm", "list", "packages"]
        if flag:
            args.append(flag)
        out = _adb_device(*args)
        packages = [
            l.replace("package:", "").strip()
            for l in out.splitlines()
            if l.startswith("package:")
        ]
        if filter_str:
            fl = filter_str.lower()
            packages = [p for p in packages if fl in p.lower()]
        log.info(f"TOOL app_list_packages OK — {len(packages)} packages")
        return json.dumps({"packages": packages, "count": len(packages)})
    except Exception as e:
        log.error(f"TOOL app_list_packages FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_install(apk_path: str) -> str:
    """
    Install an APK from the host machine onto the device.
    apk_path: local path to the .apk file.
    Requires developer mode.
    """
    log.info(f"TOOL app_install called — apk_path={apk_path!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("install", "-r", apk_path, timeout=120)
        log.info("TOOL app_install OK")
        return json.dumps({"installed": apk_path, "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL app_install FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_uninstall(package: str, confirm: bool = False) -> str:
    """
    Remove an app by package name.
    confirm must be True to execute (destructive operation).
    Requires developer mode.
    """
    log.info(f"TOOL app_uninstall called — package={package!r} confirm={confirm}")
    err = _require_dev_mode()
    if err:
        return err
    if not confirm:
        return json.dumps({"error": "Set confirm=True to uninstall the app. This is destructive."})
    try:
        out = _adb_device("uninstall", package)
        log.info("TOOL app_uninstall OK")
        return json.dumps({"uninstalled": package, "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL app_uninstall FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def app_clear_data(package: str, confirm: bool = False) -> str:
    """
    Wipe all data for an app (equivalent to Settings → App → Clear Data).
    confirm must be True to execute (destructive operation).
    Requires developer mode.
    """
    log.info(f"TOOL app_clear_data called — package={package!r} confirm={confirm}")
    err = _require_dev_mode()
    if err:
        return err
    if not confirm:
        return json.dumps({"error": "Set confirm=True to clear app data. This is destructive."})
    try:
        out = _adb_device("shell", "pm", "clear", package)
        log.info("TOOL app_clear_data OK")
        return json.dumps({"cleared": package, "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL app_clear_data FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def activity_start(
    package: str,
    activity: str,
    action: str = "",
    data_uri: str = "",
    extras: str = "",
) -> str:
    """
    Launch an activity with full intent control.
    extras: space-separated key/value pairs, e.g. "--es key value --ei count 5"
    Requires developer mode.
    """
    log.info(f"TOOL activity_start called — {package}/{activity}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        cmd = ["shell", "am", "start"]
        if action:
            cmd += ["-a", action]
        if data_uri:
            cmd += ["-d", data_uri]
        cmd += ["-n", f"{package}/{activity}"]
        if extras:
            cmd += extras.split()
        out = _adb_device(*cmd)
        log.info("TOOL activity_start OK")
        return json.dumps({"started": f"{package}/{activity}", "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL activity_start FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def broadcast_send(action: str, extras: str = "", package: str = "") -> str:
    """
    Send a broadcast intent.
    action: intent action, e.g. "android.intent.action.BOOT_COMPLETED"
    extras: space-separated extras, e.g. "--es key value"
    package: optional target package for explicit broadcast.
    Requires developer mode.
    """
    log.info(f"TOOL broadcast_send called — action={action!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        cmd = ["shell", "am", "broadcast", "-a", action]
        if package:
            cmd += ["-p", package]
        if extras:
            cmd += extras.split()
        out = _adb_device(*cmd)
        log.info("TOOL broadcast_send OK")
        return json.dumps({"broadcast": action, "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL broadcast_send FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Screen
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def screen_size() -> str:
    """Get the display resolution (physical size in pixels)."""
    log.info("TOOL screen_size called")
    try:
        out = _adb_device("shell", "wm", "size").strip()
        # "Physical size: 1080x2340" or "Override size: ..."
        size = out.split(":")[-1].strip()
        w, h = size.split("x")
        log.info("TOOL screen_size OK")
        return json.dumps({"width": int(w), "height": int(h), "raw": out})
    except Exception as e:
        log.error(f"TOOL screen_size FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_density() -> str:
    """Get the display DPI (dots per inch)."""
    log.info("TOOL screen_density called")
    try:
        out = _adb_device("shell", "wm", "density").strip()
        dpi = out.split(":")[-1].strip()
        log.info("TOOL screen_density OK")
        return json.dumps({"dpi": int(dpi), "raw": out})
    except Exception as e:
        log.error(f"TOOL screen_density FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_on() -> str:
    """Wake / turn on the display."""
    log.info("TOOL screen_on called")
    try:
        _adb_device("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        log.info("TOOL screen_on OK")
        return json.dumps({"screen": "on"})
    except Exception as e:
        log.error(f"TOOL screen_on FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_off() -> str:
    """Put the display to sleep."""
    log.info("TOOL screen_off called")
    try:
        _adb_device("shell", "input", "keyevent", "KEYCODE_SLEEP")
        log.info("TOOL screen_off OK")
        return json.dumps({"screen": "off"})
    except Exception as e:
        log.error(f"TOOL screen_off FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_record(
    output_path: str = "/tmp/screen_record.mp4",
    duration_sec: int = 30,
    bit_rate: str = "4M",
) -> str:
    """
    Record the screen to an MP4 file.
    duration_sec: recording length in seconds (max 180).
    bit_rate: video bitrate, e.g. "4M", "8M".
    Requires developer mode.
    """
    log.info(f"TOOL screen_record called — {output_path} {duration_sec}s {bit_rate}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        remote = "/sdcard/_mcp_screenrecord.mp4"
        _adb_device("shell", "screenrecord",
                    "--time-limit", str(min(duration_sec, 180)),
                    "--bit-rate", bit_rate,
                    remote,
                    timeout=duration_sec + 10)
        _adb_device("pull", remote, output_path)
        _adb_device("shell", "rm", "-f", remote)
        size = os.path.getsize(output_path) if os.path.exists(output_path) else -1
        log.info("TOOL screen_record OK")
        return json.dumps({"recorded": output_path, "bytes": size})
    except Exception as e:
        log.error(f"TOOL screen_record FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_set_size(width: int, height: int) -> str:
    """
    Override the display resolution (e.g. for testing different screen sizes).
    Requires developer mode.
    """
    log.info(f"TOOL screen_set_size called — {width}x{height}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        _adb_device("shell", "wm", "size", f"{width}x{height}")
        log.info("TOOL screen_set_size OK")
        return json.dumps({"size_set": f"{width}x{height}"})
    except Exception as e:
        log.error(f"TOOL screen_set_size FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_reset_size() -> str:
    """Restore the original display resolution after screen_set_size. Requires developer mode."""
    log.info("TOOL screen_reset_size called")
    err = _require_dev_mode()
    if err:
        return err
    try:
        _adb_device("shell", "wm", "size", "reset")
        log.info("TOOL screen_reset_size OK")
        return json.dumps({"size": "reset"})
    except Exception as e:
        log.error(f"TOOL screen_reset_size FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Settings, notifications, media
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def settings_get(namespace: str, key: str) -> str:
    """
    Read any system setting.
    namespace: "system" | "global" | "secure"
    key: setting key, e.g. "wifi_on", "screen_brightness"
    """
    log.info(f"TOOL settings_get called — {namespace}/{key}")
    try:
        val = _adb_device("shell", "settings", "get", namespace, key).strip()
        log.info("TOOL settings_get OK")
        return json.dumps({"namespace": namespace, "key": key, "value": val})
    except Exception as e:
        log.error(f"TOOL settings_get FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def settings_put(namespace: str, key: str, value: str) -> str:
    """
    Write a system setting.
    namespace: "system" | "global" | "secure"
    Requires developer mode.
    """
    log.info(f"TOOL settings_put called — {namespace}/{key}={value!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        _adb_device("shell", "settings", "put", namespace, key, value)
        log.info("TOOL settings_put OK")
        return json.dumps({"set": {namespace: {key: value}}})
    except Exception as e:
        log.error(f"TOOL settings_put FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def notification_list() -> str:
    """List recent notifications (title, text, package) via dumpsys."""
    log.info("TOOL notification_list called")
    try:
        raw = _adb_device("shell", "dumpsys", "notification", "--noredact")
        notifications = []
        current: dict = {}
        for line in raw.splitlines():
            line = line.strip()
            if "NotificationRecord" in line:
                if current:
                    notifications.append(current)
                current = {}
            if "pkg=" in line:
                import re
                m = re.search(r"pkg=(\S+)", line)
                if m:
                    current["package"] = m.group(1)
            if line.startswith("android.title"):
                current["title"] = line.split("=", 1)[-1].strip()
            if line.startswith("android.text"):
                current["text"] = line.split("=", 1)[-1].strip()
        if current:
            notifications.append(current)
        log.info(f"TOOL notification_list OK — {len(notifications)} notifications")
        return json.dumps({"notifications": notifications})
    except Exception as e:
        log.error(f"TOOL notification_list FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def media_control(action: str) -> str:
    """
    Control media playback.
    action: "play" | "pause" | "play_pause" | "next" | "previous" | "stop" |
            "volume_up" | "volume_down"
    """
    log.info(f"TOOL media_control called — action={action!r}")
    key_map = {
        "play":        "KEYCODE_MEDIA_PLAY",
        "pause":       "KEYCODE_MEDIA_PAUSE",
        "play_pause":  "KEYCODE_MEDIA_PLAY_PAUSE",
        "next":        "KEYCODE_MEDIA_NEXT",
        "previous":    "KEYCODE_MEDIA_PREVIOUS",
        "stop":        "KEYCODE_MEDIA_STOP",
        "volume_up":   "KEYCODE_VOLUME_UP",
        "volume_down": "KEYCODE_VOLUME_DOWN",
    }
    kc = key_map.get(action.lower())
    if not kc:
        return json.dumps({"error": f"Unknown action '{action}'. Use: {list(key_map)}"})
    try:
        _adb_device("shell", "input", "keyevent", kc)
        log.info("TOOL media_control OK")
        return json.dumps({"media_action": action, "keyevent": kc})
    except Exception as e:
        log.error(f"TOOL media_control FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def wifi_toggle(enable: bool) -> str:
    """Enable or disable WiFi. Requires developer mode."""
    log.info(f"TOOL wifi_toggle called — enable={enable}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        state = "enable" if enable else "disable"
        _adb_device("shell", "svc", "wifi", state)
        log.info("TOOL wifi_toggle OK")
        return json.dumps({"wifi": state})
    except Exception as e:
        log.error(f"TOOL wifi_toggle FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def bluetooth_toggle(enable: bool) -> str:
    """Enable or disable Bluetooth. Requires developer mode."""
    log.info(f"TOOL bluetooth_toggle called — enable={enable}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        state = "enable" if enable else "disable"
        _adb_device("shell", "svc", "bluetooth", state)
        log.info("TOOL bluetooth_toggle OK")
        return json.dumps({"bluetooth": state})
    except Exception as e:
        log.error(f"TOOL bluetooth_toggle FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def airplane_mode_toggle(enable: bool, confirm: bool = False) -> str:
    """
    Toggle airplane mode.
    confirm must be True (destructive — drops all network connections).
    Requires developer mode.
    """
    log.info(f"TOOL airplane_mode_toggle called — enable={enable} confirm={confirm}")
    err = _require_dev_mode()
    if err:
        return err
    if not confirm:
        return json.dumps({"error": "Set confirm=True to toggle airplane mode (drops network)."})
    try:
        val = "1" if enable else "0"
        _adb_device("shell", "settings", "put", "global", "airplane_mode_on", val)
        _adb_device("shell", "am", "broadcast",
                    "-a", "android.intent.action.AIRPLANE_MODE",
                    "--ez", "state", "true" if enable else "false")
        log.info("TOOL airplane_mode_toggle OK")
        return json.dumps({"airplane_mode": enable})
    except Exception as e:
        log.error(f"TOOL airplane_mode_toggle FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_brightness(level: int) -> str:
    """
    Set screen brightness (0–255).
    Requires developer mode.
    """
    log.info(f"TOOL screen_brightness called — level={level}")
    err = _require_dev_mode()
    if err:
        return err
    if not 0 <= level <= 255:
        return json.dumps({"error": "level must be 0–255."})
    try:
        # Disable auto-brightness first
        _adb_device("shell", "settings", "put", "system",
                    "screen_brightness_mode", "0")
        _adb_device("shell", "settings", "put", "system",
                    "screen_brightness", str(level))
        log.info("TOOL screen_brightness OK")
        return json.dumps({"brightness": level})
    except Exception as e:
        log.error(f"TOOL screen_brightness FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def screen_timeout(milliseconds: int) -> str:
    """
    Set the screen timeout duration in milliseconds.
    e.g. 30000 = 30 s, 300000 = 5 min, -1 = never.
    Requires developer mode.
    """
    log.info(f"TOOL screen_timeout called — {milliseconds}ms")
    err = _require_dev_mode()
    if err:
        return err
    try:
        _adb_device("shell", "settings", "put", "system",
                    "screen_off_timeout", str(milliseconds))
        log.info("TOOL screen_timeout OK")
        return json.dumps({"screen_timeout_ms": milliseconds})
    except Exception as e:
        log.error(f"TOOL screen_timeout FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def config_status() -> str:
    """Show current server configuration (developer mode, screenshot dir, active device)."""
    log.info("TOOL config_status called")
    return json.dumps(_config)


@mcp.tool()
def config_set_developer_mode(enabled: bool) -> str:
    """
    Toggle developer tools on or off.
    When enabled, destructive tools (uninstall, clear data, reboot, delete,
    shell commands, etc.) become available.
    """
    log.info(f"TOOL config_set_developer_mode called — enabled={enabled}")
    _config["developer_mode"] = enabled
    return json.dumps({"developer_mode": enabled})


@mcp.tool()
def config_set_screenshot_dir(directory: str) -> str:
    """Set the local directory where screenshots are saved."""
    log.info(f"TOOL config_set_screenshot_dir called — directory={directory!r}")
    _config["screenshot_dir"] = directory
    return json.dumps({"screenshot_dir": directory})


# ──────────────────────────────────────────────────────────────────────────────
# Developer-mode: shell, logcat, files, reboot
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def shell_command(command: str) -> str:
    """
    Run any shell command on the device and return stdout + stderr.
    Requires developer mode.
    """
    log.info(f"TOOL shell_command called — command={command!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("shell", command, timeout=30)
        log.info("TOOL shell_command OK")
        return json.dumps({"command": command, "output": out})
    except Exception as e:
        log.error(f"TOOL shell_command FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def device_reboot(confirm: bool = False) -> str:
    """
    Reboot the device.
    confirm must be True (destructive).
    Requires developer mode.
    """
    log.info(f"TOOL device_reboot called — confirm={confirm}")
    err = _require_dev_mode()
    if err:
        return err
    if not confirm:
        return json.dumps({"error": "Set confirm=True to reboot the device."})
    try:
        _adb_device("reboot", timeout=10)
        log.info("TOOL device_reboot OK")
        return json.dumps({"rebooting": True})
    except Exception as e:
        log.error(f"TOOL device_reboot FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def logcat_capture(
    lines: int = 100,
    filter_spec: str = "*:W",
    timeout_sec: int = 5,
) -> str:
    """
    Capture recent system logs.
    filter_spec: logcat filter, e.g. "MyApp:D *:S" or "*:W" (default).
    lines: maximum log lines to return.
    Requires developer mode.
    """
    log.info(f"TOOL logcat_capture called — filter={filter_spec!r} lines={lines}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        cmd = [ADB, "logcat", "-d", "-t", str(lines)]
        cmd += filter_spec.split()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        output = result.stdout or result.stderr
        log.info(f"TOOL logcat_capture OK — {len(output)} chars")
        return json.dumps({"logcat": output})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "logcat timed out"})
    except Exception as e:
        log.error(f"TOOL logcat_capture FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def logcat_clear() -> str:
    """Clear the logcat ring buffer. Requires developer mode."""
    log.info("TOOL logcat_clear called")
    err = _require_dev_mode()
    if err:
        return err
    try:
        subprocess.run([ADB, "logcat", "-c"], capture_output=True, timeout=10)
        log.info("TOOL logcat_clear OK")
        return json.dumps({"logcat": "cleared"})
    except Exception as e:
        log.error(f"TOOL logcat_clear FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def file_push(local_path: str, remote_path: str) -> str:
    """
    Transfer a file from the host machine to the device.
    Requires developer mode.
    """
    log.info(f"TOOL file_push called — {local_path!r} → {remote_path!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("push", local_path, remote_path, timeout=60)
        log.info("TOOL file_push OK")
        return json.dumps({"pushed": {"local": local_path, "remote": remote_path},
                           "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL file_push FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def file_pull(remote_path: str, local_path: str = "/tmp/") -> str:
    """
    Transfer a file from the device to the host machine.
    Requires developer mode.
    """
    log.info(f"TOOL file_pull called — {remote_path!r} → {local_path!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("pull", remote_path, local_path, timeout=60)
        log.info("TOOL file_pull OK")
        return json.dumps({"pulled": {"remote": remote_path, "local": local_path},
                           "output": out.strip()})
    except Exception as e:
        log.error(f"TOOL file_pull FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def file_list(remote_path: str = "/sdcard/") -> str:
    """
    List directory contents on the device.
    Requires developer mode.
    """
    log.info(f"TOOL file_list called — {remote_path!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        out = _adb_device("shell", "ls", "-la", remote_path)
        entries = [l.strip() for l in out.splitlines() if l.strip()]
        log.info(f"TOOL file_list OK — {len(entries)} entries")
        return json.dumps({"path": remote_path, "entries": entries})
    except Exception as e:
        log.error(f"TOOL file_list FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def file_delete(remote_path: str, confirm: bool = False) -> str:
    """
    Delete a file on the device.
    confirm must be True (destructive).
    Requires developer mode.
    """
    log.info(f"TOOL file_delete called — {remote_path!r} confirm={confirm}")
    err = _require_dev_mode()
    if err:
        return err
    if not confirm:
        return json.dumps({"error": "Set confirm=True to delete the file. This is destructive."})
    try:
        _adb_device("shell", "rm", "-f", remote_path)
        log.info("TOOL file_delete OK")
        return json.dumps({"deleted": remote_path})
    except Exception as e:
        log.error(f"TOOL file_delete FAILED: {e}")
        return json.dumps({"error": str(e)})


@mcp.tool()
def file_exists(remote_path: str) -> str:
    """
    Check whether a file or directory exists on the device.
    Requires developer mode.
    """
    log.info(f"TOOL file_exists called — {remote_path!r}")
    err = _require_dev_mode()
    if err:
        return err
    try:
        result = subprocess.run(
            [ADB, "shell", f"[ -e '{remote_path}' ] && echo yes || echo no"],
            capture_output=True, text=True, timeout=10,
        )
        exists = result.stdout.strip() == "yes"
        log.info(f"TOOL file_exists OK — {exists}")
        return json.dumps({"path": remote_path, "exists": exists})
    except Exception as e:
        log.error(f"TOOL file_exists FAILED: {e}")
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Wait / poll helpers
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def wait_for_text(
    text: str,
    timeout_sec: int = 30,
    poll_interval_sec: float = 1.0,
    exact: bool = False,
) -> str:
    """
    Poll the UI until the given text appears on screen.
    Returns as soon as the text is found, or an error after timeout_sec.
    exact=False (default) does a case-insensitive substring match.
    """
    log.info(f"TOOL wait_for_text called — text={text!r} timeout={timeout_sec}s")
    import time
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            root = _dump_xml()
            nodes = _find_by_text(root, text, exact=exact)
            if nodes:
                log.info(f"TOOL wait_for_text OK — found after poll")
                return json.dumps({"found": True, "text": text})
        except Exception:
            pass
        time.sleep(poll_interval_sec)
    log.warning(f"TOOL wait_for_text TIMEOUT — text={text!r}")
    return json.dumps({"found": False, "text": text, "error": f"Timed out after {timeout_sec}s"})


@mcp.tool()
def wait_for_text_gone(
    text: str,
    timeout_sec: int = 30,
    poll_interval_sec: float = 1.0,
    exact: bool = False,
) -> str:
    """
    Poll the UI until the given text disappears from screen.
    Returns as soon as the text is gone, or an error after timeout_sec.
    """
    log.info(f"TOOL wait_for_text_gone called — text={text!r} timeout={timeout_sec}s")
    import time
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            root = _dump_xml()
            nodes = _find_by_text(root, text, exact=exact)
            if not nodes:
                log.info(f"TOOL wait_for_text_gone OK — text gone")
                return json.dumps({"gone": True, "text": text})
        except Exception:
            pass
        time.sleep(poll_interval_sec)
    log.warning(f"TOOL wait_for_text_gone TIMEOUT — text={text!r}")
    return json.dumps({"gone": False, "text": text, "error": f"Timed out after {timeout_sec}s"})


# ──────────────────────────────────────────────────────────────────────────────
# URI resources
# ──────────────────────────────────────────────────────────────────────────────

@mcp.resource("adb://devices")
def resource_devices() -> str:
    """Connected device list."""
    return devices_list()


@mcp.resource("adb://apps/current")
def resource_current_app() -> str:
    """Currently focused app."""
    return app_current()


@mcp.resource("adb://screen/info")
def resource_screen_info() -> str:
    """Screen resolution and DPI."""
    size   = json.loads(screen_size())
    density = json.loads(screen_density())
    return json.dumps({**size, **density})


@mcp.resource("adb://help")
def resource_help() -> str:
    """Tool reference and tips."""
    return json.dumps({
        "phases": {
            "1_ui_inspect": ["get_ui_skeleton"],
            "2_ui_target":  ["get_element_detail", "get_elements_by_class",
                             "get_elements_by_text", "get_clickable_elements"],
        },
        "devices":      ["devices_list", "devices_use", "devices_current",
                         "device_info", "device_properties"],
        "connectivity": ["adb_connect", "adb_disconnect", "adb_pair", "adb_tcpip"],
        "input":        ["input_tap", "input_swipe", "input_scroll_down",
                         "input_scroll_up", "input_back", "input_home",
                         "input_recent_apps", "input_key", "input_text",
                         "input_long_press", "tap_text", "tap_element",
                         "clipboard_set", "clipboard_get"],
        "apps":         ["app_launch", "app_open_url", "app_close", "app_current",
                         "app_list_packages", "app_install", "app_uninstall",
                         "app_clear_data", "activity_start", "broadcast_send"],
        "screen":       ["take_screenshot", "screen_size", "screen_density",
                         "screen_on", "screen_off", "screen_record",
                         "screen_set_size", "screen_reset_size",
                         "screen_brightness", "screen_timeout"],
        "settings":     ["settings_get", "settings_put", "notification_list",
                         "media_control", "wifi_toggle", "bluetooth_toggle",
                         "airplane_mode_toggle"],
        "wait":         ["wait_for_text", "wait_for_text_gone"],
        "developer":    ["shell_command", "device_reboot", "logcat_capture",
                         "logcat_clear", "file_push", "file_pull", "file_list",
                         "file_delete", "file_exists"],
        "config":       ["config_status", "config_set_developer_mode",
                         "config_set_screenshot_dir"],
        "tip": "Enable developer mode with config_set_developer_mode(true) to unlock power tools.",
    })


if __name__ == "__main__":
    log.info("Entering mcp.run() — waiting for MCP client connections via stdio")
    try:
        mcp.run()
    except Exception as e:
        log.critical(f"mcp.run() crashed: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)
