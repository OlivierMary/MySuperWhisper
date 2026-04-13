"""
Text pasting functionality for MySuperWhisper.
Uses clipboard paste (Ctrl+V) for speed and reliability.
"""

import os
import subprocess
import time
import pyperclip
from .config import log, config


def detect_session_type():
    """Detect if running on Wayland or X11."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def _is_terminal(session_type):
    """
    Check if the active window is a terminal emulator.
    Uses xdotool/xprop on X11 and compatible Wayland environments.
    """
    try:
        # 1. Get Active Window ID
        # Note: xdotool might not work on native Wayland windows, 
        # but often works for XWayland or if disabled security.
        cmd_id = ["xdotool", "getactivewindow"]
        result_id = subprocess.run(cmd_id, capture_output=True, text=True, timeout=0.5)
        
        if result_id.returncode != 0:
            return False
            
        window_id = result_id.stdout.strip()
        if not window_id:
            return False

        # 2. Get Window Class
        cmd_prop = ["xprop", "-id", window_id, "WM_CLASS"]
        result_prop = subprocess.run(cmd_prop, capture_output=True, text=True, timeout=0.5)
        
        if result_prop.returncode != 0:
            return False

        # Check for terminal keywords
        # Original keywords: term, console, kitty, warp
        class_info = result_prop.stdout.lower()
        term_keywords = ["term", "console", "kitty", "warp"]
        return any(k in class_info for k in term_keywords)

    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        # Tools not installed or other error -> assume not terminal
        return False


def paste_text(text, press_enter=False):
    """
    Paste text into the active application using clipboard.

    Strategy:
    1. Copy text to clipboard
    2. Send Ctrl+V to paste (fast, single operation)
    3. Handle newlines with Shift+Return for soft breaks

    Args:
        text: Text to paste
        press_enter: If True, press Enter after pasting
    """
    session_type = detect_session_type()
    
    # Check if we are in a terminal
    if _is_terminal(session_type):
        # Terminals (mostly) use Ctrl+Shift+V for paste
        # and handle multiline paste better as a single block.
        _paste_clipboard(text, session_type, force_ctrl_shift_v=True)
    else:
        # Standard GUI App logic
        has_newlines = '\n' in text

        if has_newlines:
            # For text with newlines, paste line by line with Shift+Return
            # This prevents validation in chat apps
            _paste_with_newlines(text, session_type)
        else:
            # Simple text: clipboard paste (Ctrl+V)
            _paste_clipboard(text, session_type)

    if press_enter:
        time.sleep(0.05)
        _press_key("Return", session_type)


def _get_clipboard_backup(session_type):
    """Save current clipboard content for later restore.

    Text uses pyperclip: a direct `xclip -o -t utf8_string` can return empty
    bytes after an earlier `pyperclip.copy` in the same process (xclip daemon
    ownership quirk), which would clobber the clipboard on restore. Binary
    still goes through the native tool since pyperclip is text-only.
    """
    try:
        text = pyperclip.paste()
    except (UnicodeDecodeError, pyperclip.PyperclipException):
        # Clipboard holds non-text bytes (e.g. PNG) — fall through to binary.
        text = None
    if text:
        return text, "text"

    try:
        if session_type == "wayland":
            res = subprocess.run(["wl-paste", "--list-types"], capture_output=True, text=True, timeout=1.0)
            if res.returncode != 0 or not res.stdout.strip():
                return None, None
            available = [t.strip() for t in res.stdout.splitlines() if t.strip()]
            binary_mime = next(
                (t for t in available if not t.startswith("text/") and t.lower() != "utf8_string"),
                None,
            )
            if not binary_mime:
                return None, None
            res_data = subprocess.run(["wl-paste", "--type", binary_mime], capture_output=True, timeout=2.0)
        else:
            res = subprocess.run(["xclip", "-selection", "clipboard", "-o", "-t", "TARGETS"], capture_output=True, text=True, timeout=1.0)
            if res.returncode != 0 or "image/png" not in res.stdout.lower():
                return None, None
            binary_mime = "image/png"
            res_data = subprocess.run(["xclip", "-selection", "clipboard", "-o", "-t", "image/png"], capture_output=True, timeout=2.0)

        if res_data.returncode != 0 or not res_data.stdout:
            return None, None
        return res_data.stdout, binary_mime
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None, None


def _restore_clipboard_backup(data, mime_type, session_type):
    """Restore saved clipboard content."""
    if not data or not mime_type:
        return
    try:
        if mime_type == "text":
            pyperclip.copy(data)
            return
        if session_type == "wayland":
            subprocess.run(["wl-copy", "--type", mime_type], input=data, timeout=2.0)
        else:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", mime_type], input=data, timeout=2.0)
    except (FileNotFoundError, subprocess.SubprocessError, TimeoutError, OSError):
        pass


def _paste_clipboard(text, session_type, force_ctrl_shift_v=False):
    """Paste text using clipboard (Ctrl+V or Ctrl+Shift+V)."""
    old_data, old_mime = None, None
    if config.restore_clipboard:
        old_data, old_mime = _get_clipboard_backup(session_type)

    pyperclip.copy(text)
    time.sleep(0.05)

    try:
        if session_type == "wayland":
            if force_ctrl_shift_v:
                subprocess.run(["wtype", "-M", "ctrl", "-M", "shift", "-k", "v", "-m", "shift", "-m", "ctrl"])
            else:
                subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"])
        else:
            key_combo = "ctrl+shift+v" if force_ctrl_shift_v else "ctrl+v"
            subprocess.run(["xdotool", "key", "--clearmodifiers", key_combo])
    except FileNotFoundError as e:
        log(f"Paste tool not found: {e}", "error")

    if config.restore_clipboard and old_data:
        # Let the target consume the paste event before we overwrite the clipboard.
        time.sleep(0.15)
        _restore_clipboard_backup(old_data, old_mime, session_type)


def _paste_with_newlines(text, session_type):
    """Paste text with newlines, using Shift+Return for soft breaks."""
    lines = text.split('\n')

    for i, line in enumerate(lines):
        if line:
            _paste_clipboard(line, session_type)

        # Add soft newline (Shift+Return) between lines
        if i < len(lines) - 1:
            time.sleep(0.03)
            _press_key("shift+Return", session_type)
            time.sleep(0.02)


def _press_key(key, session_type):
    """Press a key or key combination."""
    try:
        if session_type == "wayland":
            if '+' in key:
                # Handle modifier+key combo (e.g., "shift+Return")
                parts = key.split('+')
                modifier = parts[0].lower()
                keyname = parts[1]
                subprocess.run(["wtype", "-M", modifier, "-k", keyname, "-m", modifier])
            else:
                subprocess.run(["wtype", "-k", key])
        else:
            subprocess.run(["xdotool", "key", "--clearmodifiers", key])
    except FileNotFoundError as e:
        log(f"Key press tool not found: {e}", "error")


def press_enter_key():
    """Simulate pressing the Enter key."""
    session_type = detect_session_type()
    _press_key("Return", session_type)
