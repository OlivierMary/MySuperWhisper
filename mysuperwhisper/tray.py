"""
System tray icon and menu for MySuperWhisper.
Provides visual feedback and configuration access.
"""

import subprocess
import threading
import time
import tkinter as tk
import pystray
from PIL import Image, ImageDraw
from .config import log, config, CONFIG_FILE, LOG_FILE, LOG_DIR
from . import audio
from . import transcription

# Global tray icon instance
_tray_icon = None

# Callbacks (set by main module)
_on_quit_callback = None
_save_config_callback = None


def set_callbacks(on_quit, save_config):
    """Set callback functions for tray actions."""
    global _on_quit_callback, _save_config_callback
    _on_quit_callback = on_quit
    _save_config_callback = save_config


def _create_image(width, height, color, level=0.0):
    """
    Generate tray icon image.

    Args:
        width: Image width
        height: Image height
        color: Main circle color
        level: Audio level for test mode gauge (0.0-1.0)

    Returns:
        PIL.Image: Generated icon
    """
    # Create image with transparent background (RGBA)
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)

    padding = 4

    # Draw audio level gauge in test mode
    if audio.is_testing_mic():
        # Gauge background (light gray)
        dc.rectangle(
            (padding, height - padding - 10, width - padding, height - padding),
            fill=(200, 200, 200),
            outline="black"
        )

        if level > 0:
            # Level bar (green -> red)
            bar_width = int((width - 2 * padding) * min(level, 1.0))
            fill_color = "green" if level < 0.7 else "red"
            if bar_width > 0:
                dc.rectangle(
                    (padding, height - padding - 10, padding + bar_width, height - padding),
                    fill=fill_color
                )

    # Draw main status circle
    circle_height = height - padding - 15 if audio.is_testing_mic() else height - padding
    dc.ellipse((padding, padding, width - padding, circle_height), fill=color, outline="black")

    # CPU mode indicator (warning triangle in bottom right)
    if transcription.is_cpu_mode():
        triangle_size = 18
        tx = width - padding - 2
        ty = circle_height - 2
        triangle_points = [
            (tx - triangle_size, ty),
            (tx, ty),
            (tx - triangle_size // 2, ty - triangle_size),
        ]
        dc.polygon(triangle_points, fill=(255, 140, 0), outline="black")
        # Exclamation mark
        excl_x = tx - triangle_size // 2
        excl_y = ty - triangle_size // 2 - 1
        dc.rectangle((excl_x - 1, excl_y - 4, excl_x + 1, excl_y + 1), fill="black")
        dc.rectangle((excl_x - 1, excl_y + 3, excl_x + 1, excl_y + 5), fill="black")

    return image


def update_tray(status, level=0.0):
    """
    Update tray icon and tooltip based on status.

    Args:
        status: One of 'idle', 'recording', 'processing', 'testing', 'loading'
        level: Audio level for test mode (0.0-1.0)
    """
    if _tray_icon is None:
        return

    # Constant prefix to prevent icon reordering
    prefix = "MySuperWhisper: "
    color = "green"
    detail = ""

    if status == "idle":
        # Green = transcribe mode, Purple = translate mode
        color = (138, 43, 226) if config.task == "translate" else "green"
        from .keyboard import _get_hotkey_description
        hotkey_desc = _get_hotkey_description(config.record_hotkey, config.record_press_count)
        task_label = "Translate→EN" if config.task == "translate" else "Transcribe"
        detail = f"Ready ({hotkey_desc}) [{task_label}]"
    elif status == "recording":
        color = "red"
        detail = "Recording..."
    elif status == "processing":
        color = "orange"
        detail = "Transcribing..."
    elif status == "testing":
        color = "blue"
        detail = "Mic Test"
    elif status == "loading":
        color = "yellow"
        detail = "Loading..."

    if audio.is_testing_mic():
        detail = f"Level: {int(level*100)}%"
        if status == "idle":
            color = "blue"

    # Add CPU mode indicator to tooltip
    if transcription.is_cpu_mode() and status != "loading":
        detail += " [CPU]"

    try:
        _tray_icon.icon = _create_image(64, 64, color, level)
        _tray_icon.title = prefix + detail
    except Exception:
        pass  # Avoid crashes if icon is being closed


def _open_file_with_default_app(filepath):
    """Open a file with the system's default application."""
    try:
        subprocess.Popen(["xdg-open", str(filepath)])
        log(f"Opening: {filepath}")
    except Exception as e:
        log(f"Error opening file {filepath}: {e}", "error")


def _on_open_config(icon, item):
    """Open configuration file in default editor."""
    if not CONFIG_FILE.exists() and _save_config_callback:
        _save_config_callback()
    _open_file_with_default_app(CONFIG_FILE)


def _on_open_logs(icon, item):
    """Open log file in default editor."""
    _open_file_with_default_app(LOG_FILE)


def _on_open_log_folder(icon, item):
    """Open logs folder in file manager."""
    _open_file_with_default_app(LOG_DIR)


def _on_toggle_test(icon, item):
    """Toggle microphone test mode."""
    if audio.is_testing_mic():
        audio.stop_mic_test()
        # Wait for worker thread to finish so it doesn't overwrite our idle state
        if audio._test_thread and audio._test_thread.is_alive():
            audio._test_thread.join(timeout=1.0)
        update_tray("idle")
    else:
        def _update_ui(level):
            if audio.is_testing_mic():
                update_tray("testing", level)

        audio.start_mic_test(_update_ui)


def _on_toggle_system_notifications(icon, item):
    """Toggle system notifications."""
    config.system_notifications_enabled = not config.system_notifications_enabled
    if _save_config_callback:
        _save_config_callback()
    log(f"System notifications: {'enabled' if config.system_notifications_enabled else 'disabled'}")


def _on_toggle_sound_notifications(icon, item):
    """Toggle sound notifications."""
    config.sound_notifications_enabled = not config.sound_notifications_enabled
    if _save_config_callback:
        _save_config_callback()
    log(f"Sound notifications: {'enabled' if config.sound_notifications_enabled else 'disabled'}")


def _on_show_history(icon, item):
    """Open history popup."""
    from . import history
    history.open_history_popup_async()


def _on_open_sound_settings(icon, item):
    """Open system sound settings."""
    try:
        # Try different sound settings commands
        for cmd in [
            ["cinnamon-settings", "sound"],  # Cinnamon
            ["gnome-control-center", "sound"],  # GNOME
            ["pavucontrol"],  # PulseAudio Volume Control
            ["xdg-open", "settings://sound"],  # Generic
        ]:
            try:
                subprocess.Popen(cmd)
                log(f"Opened sound settings: {cmd[0]}")
                return
            except FileNotFoundError:
                continue
        log("Could not find sound settings application", "warning")
    except Exception as e:
        log(f"Error opening sound settings: {e}", "error")


def _on_select_model(name):
    """Create handler for model selection."""
    def wrapper(icon, item):
        if config.model_size != name:
            def _reload():
                update_tray("loading")
                transcription.reload_model(name)
                if _save_config_callback:
                    _save_config_callback()
                update_tray("idle")

            threading.Thread(target=_reload, daemon=True).start()
    return wrapper


def _on_select_language(lang_code):
    """Handler for language selection."""
    def wrapper(icon, item):
        if config.language != lang_code:
            config.language = lang_code
            if _save_config_callback:
                _save_config_callback()
            label = lang_code if lang_code else "Auto-detect"
            log(f"Language changed to: {label}")
            icon.menu = _create_menu()
    return wrapper


def _on_select_task(task_name):
    """Handler for task selection."""
    def wrapper(icon, item):
        if config.task != task_name:
            config.task = task_name
            if _save_config_callback:
                _save_config_callback()
            log(f"Task changed to: {task_name}")
            icon.menu = _create_menu()
            update_tray("idle")
    return wrapper


def _on_select_source(name):
    """Handler for microphone selection."""
    def wrapper(icon, item):
        # Determine if selecting "System Default" (name=None)
        if name is None:
            config.input_device = None
            config.save()
            audio.restart_stream()
        else:
            audio.set_default_source(name)
        
        # Refresh menu
        icon.menu = _create_menu()
    return wrapper


def _on_select_sink(name):
    """Handler for speaker selection."""
    def wrapper(icon, item):
        if name is None:
            config.output_device = None
            config.save()
        else:
            audio.set_default_sink(name)
            
        icon.menu = _create_menu()
    return wrapper


def _on_refresh_devices(icon, item):
    """Refresh device list."""
    log("Manual device refresh...")
    icon.menu = _create_menu()


def _show_shortcut_popup(title, current_key, current_count, on_save):
    """
    Show a popup to detect and configure a keyboard shortcut.
    Uses tkinter's own key events (not pynput) to avoid X11 conflicts.
    Stops the pynput listener while the popup is open.
    """
    from .keyboard import (
        _get_key_display_name, _build_combo_string, _get_single_key_display,
        reset_hotkey_state, stop_listener, start_listener, MODIFIER_KEYS
    )

    # Map tkinter keysym to pynput-compatible key names.
    # On Linux, pynput reports left modifiers as generic names
    # (e.g., "ctrl" not "ctrl_l") while right modifiers are specific.
    _TK_KEYSYM_MAP = {
        "Control_L": "ctrl", "Control_R": "ctrl_r",
        "Alt_L": "alt", "Alt_R": "alt_r",
        "ISO_Level3_Shift": "alt_gr",
        "Shift_L": "shift", "Shift_R": "shift_r",
        "Super_L": "cmd", "Super_R": "cmd_r",
        "Caps_Lock": "caps_lock", "Num_Lock": "num_lock",
        "Scroll_Lock": "scroll_lock",
        "Escape": "esc", "Return": "enter", "KP_Enter": "enter",
        "Tab": "tab", "BackSpace": "backspace",
        "space": "space", "Insert": "insert", "Delete": "delete",
        "Home": "home", "End": "end",
        "Prior": "page_up", "Next": "page_down",
        "Up": "up", "Down": "down", "Left": "left", "Right": "right",
        "Print": "print_screen", "Pause": "pause", "Menu": "menu",
    }
    # Add function keys
    for i in range(1, 25):
        _TK_KEYSYM_MAP[f"F{i}"] = f"f{i}"

    def _tk_to_key_name(keysym):
        """Convert tkinter keysym to our config key name."""
        if keysym in _TK_KEYSYM_MAP:
            return _TK_KEYSYM_MAP[keysym]
        if len(keysym) == 1:
            return keysym.lower()
        return keysym.lower()

    result = {"key": current_key, "count": current_count, "confirmed": False}

    def run_popup():
        # Stop pynput listener to avoid X11 conflicts
        stop_listener()
        log("Pynput listener stopped for shortcut popup")

        root = tk.Tk()
        root.title(title)
        root.attributes('-topmost', True)
        root.configure(bg='#2d2d2d')
        root.resizable(False, False)

        window_width = 450
        window_height = 250
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Title
        tk.Label(
            root, text=title, font=('Sans', 13, 'bold'),
            bg='#2d2d2d', fg='#ffffff', pady=15
        ).pack(fill='x')

        # Instruction
        tk.Label(
            root,
            text="Press your shortcut\n(e.g. double Ctrl+A, triple Right Ctrl, F1...)",
            font=('Sans', 10), bg='#2d2d2d', fg='#aaaaaa', pady=5
        ).pack(fill='x')

        # Current shortcut display
        current_display = _get_key_display_name(current_key)
        press_label = {1: "Single", 2: "Double", 3: "Triple"}.get(
            current_count, f"{current_count}x"
        )
        shortcut_var = tk.StringVar(value=f"{press_label} {current_display}")

        tk.Label(
            root, textvariable=shortcut_var,
            font=('Sans', 18, 'bold'),
            bg='#3d3d3d', fg='#5294e2',
            pady=20, padx=20, relief='sunken'
        ).pack(fill='x', padx=30, pady=10)

        # Buttons frame
        btn_frame = tk.Frame(root, bg='#2d2d2d')
        btn_frame.pack(fill='x', padx=30, pady=10)

        def on_ok():
            result["confirmed"] = True
            root.destroy()

        def on_cancel():
            root.destroy()

        tk.Button(
            btn_frame, text="OK", font=('Sans', 11, 'bold'),
            bg='#5294e2', fg='#ffffff', activebackground='#4a84c8',
            width=10, command=on_ok, relief='flat'
        ).pack(side='left', expand=True, padx=5)

        tk.Button(
            btn_frame, text="Cancel", font=('Sans', 11),
            bg='#555555', fg='#ffffff', activebackground='#666666',
            width=10, command=on_cancel, relief='flat'
        ).pack(side='right', expand=True, padx=5)

        # --- Tkinter-based key detection ---
        held_keys = set()
        detect_state = {"combo": None, "count": 0, "last_time": 0, "timer": None}

        def update_display(combo, count):
            display = _get_key_display_name(combo)
            press = {1: "Single", 2: "Double", 3: "Triple"}.get(count, f"{count}x")
            shortcut_var.set(f"{press} {display}")
            result["key"] = combo
            result["count"] = count

        def on_key_press(event):
            key_name = _tk_to_key_name(event.keysym)
            held_keys.add(key_name)

        def on_key_release(event):
            key_name = _tk_to_key_name(event.keysym)
            is_modifier = key_name in MODIFIER_KEYS

            # Build combo from held modifiers + released key
            held_mods = {k for k in held_keys if k in MODIFIER_KEYS and k != key_name}

            # Skip trailing modifier release after a combo
            if is_modifier and detect_state["combo"] and '+' in detect_state["combo"]:
                held_keys.discard(key_name)
                return

            combo = _build_combo_string(held_mods, key_name)
            current_time = time.time()

            # Cancel pending timer
            if detect_state["timer"]:
                root.after_cancel(detect_state["timer"])
                detect_state["timer"] = None

            # Same combo pressed quickly -> increment count
            if (combo == detect_state["combo"]
                    and current_time - detect_state["last_time"] < 0.5):
                detect_state["count"] += 1
            else:
                detect_state["combo"] = combo
                detect_state["count"] = 1

            detect_state["last_time"] = current_time
            update_display(combo, detect_state["count"])

            held_keys.discard(key_name)

        root.bind('<KeyPress>', on_key_press)
        root.bind('<KeyRelease>', on_key_release)
        root.focus_force()

        root.protocol("WM_DELETE_WINDOW", on_cancel)
        root.mainloop()

        # Restart pynput listener
        start_listener()
        log("Pynput listener restarted after shortcut popup")

        # Apply if confirmed
        if result["confirmed"]:
            on_save(result["key"], result["count"])
            reset_hotkey_state()

    threading.Thread(target=run_popup, daemon=True).start()


def _on_configure_record_shortcut(icon, item):
    """Open shortcut configuration popup for record."""
    def on_save(key, count):
        config.record_hotkey = key
        config.record_press_count = count
        if _save_config_callback:
            _save_config_callback()
        from .keyboard import _get_hotkey_description
        desc = _get_hotkey_description(key, count)
        log(f"Record shortcut changed to: {desc}")
        icon.menu = _create_menu()
        update_tray("idle")

    _show_shortcut_popup(
        "Record Shortcut",
        config.record_hotkey, config.record_press_count, on_save
    )


def _on_configure_history_shortcut(icon, item):
    """Open shortcut configuration popup for history."""
    def on_save(key, count):
        config.history_hotkey = key
        config.history_press_count = count
        if _save_config_callback:
            _save_config_callback()
        from .keyboard import _get_hotkey_description
        desc = _get_hotkey_description(key, count)
        log(f"History shortcut changed to: {desc}")
        icon.menu = _create_menu()

    _show_shortcut_popup(
        "History Shortcut",
        config.history_hotkey, config.history_press_count, on_save
    )


def _on_quit(icon, item):
    """Quit application."""
    icon.stop()
    if _on_quit_callback:
        _on_quit_callback()


def _generate_device_menu(devices, current_device_id, on_select_callback):
    """Generate a submenu for device selection."""
    items = []

    # System default option
    items.append(pystray.MenuItem(
        "Use System Default",
        on_select_callback(None),
        checked=lambda item: current_device_id is None,
        radio=True
    ))
    items.append(pystray.Menu.SEPARATOR)

    for device in devices:
        # Truncate long descriptions
        desc = device['description']
        if len(desc) > 50:
            desc = desc[:47] + "..."

        items.append(pystray.MenuItem(
            desc,
            on_select_callback(device['name']),
            checked=lambda item, name=device['name']: current_device_id == name,
            radio=True
        ))
    return pystray.Menu(*items)


def _create_menu():
    """Create the main tray menu."""
    sources = audio.get_pulse_sources()
    sinks = audio.get_pulse_sinks()

    # Determine label for Microphone
    current_mic_bg = "Unknown"
    is_mic_default = config.input_device is None
    
    if is_mic_default:
        for s in sources:
            if s['is_default']:
                current_mic_bg = s['description']
                break
    else:
        for s in sources:
            if s['name'] == config.input_device:
                current_mic_bg = s['description']
                break
        else:
            current_mic_bg = config.input_device

    if len(current_mic_bg) > 30:
        current_mic_bg = current_mic_bg[:27] + "..."
    
    mic_label = f"🎤 {current_mic_bg}" + (" (Default)" if is_mic_default else "")


    # Determine label for Speaker
    current_spk_bg = "Unknown"
    is_spk_default = config.output_device is None

    if is_spk_default:
        for s in sinks:
            if s['is_default']:
                current_spk_bg = s['description']
                break
    else:
        for s in sinks:
            if s['name'] == config.output_device:
                current_spk_bg = s['description']
                break
        else:
            current_spk_bg = config.output_device

    if len(current_spk_bg) > 30:
        current_spk_bg = current_spk_bg[:27] + "..."

    spk_label = f"🔊 {current_spk_bg}" + (" (Default)" if is_spk_default else "")


    # Model menu
    model_menu = pystray.Menu(
        pystray.MenuItem(
            "Tiny (Very fast, less accurate)",
            _on_select_model("tiny"),
            checked=lambda item: config.model_size == "tiny",
            radio=True
        ),
        pystray.MenuItem(
            "Base (Fast)",
            _on_select_model("base"),
            checked=lambda item: config.model_size == "base",
            radio=True
        ),
        pystray.MenuItem(
            "Small (Balanced)",
            _on_select_model("small"),
            checked=lambda item: config.model_size == "small",
            radio=True
        ),
        pystray.MenuItem(
            "Medium (Standard, <2GB VRAM)",
            _on_select_model("medium"),
            checked=lambda item: config.model_size == "medium",
            radio=True
        ),
        pystray.MenuItem(
            "Large-v3 (Best, ~3.3GB VRAM)",
            _on_select_model("large-v3"),
            checked=lambda item: config.model_size == "large-v3",
            radio=True
        )
    )

    # Language menu
    languages = [
        (None, "Auto-detect"),
        ("en", "English"),
        ("fr", "Français"),
        ("es", "Español"),
        ("de", "Deutsch"),
        ("it", "Italiano"),
        ("pt", "Português"),
        ("nl", "Nederlands"),
        ("ja", "日本語"),
        ("zh", "中文"),
        ("ko", "한국어"),
        ("ru", "Русский"),
        ("ar", "العربية"),
        ("pl", "Polski"),
        ("uk", "Українська"),
    ]

    language_menu = pystray.Menu(
        *[
            pystray.MenuItem(
                label,
                _on_select_language(code),
                checked=lambda item, c=code: config.language == c,
                radio=True
            )
            for code, label in languages
        ]
    )

    # Task menu with color legend
    task_menu = pystray.Menu(
        pystray.MenuItem(
            "🟢 Transcribe (keep original language)",
            _on_select_task("transcribe"),
            checked=lambda item: config.task == "transcribe",
            radio=True
        ),
        pystray.MenuItem(
            "🟣 Translate (to English)",
            _on_select_task("translate"),
            checked=lambda item: config.task == "translate",
            radio=True
        ),
    )

    # Hotkey configuration
    from .keyboard import _get_hotkey_description

    record_desc = _get_hotkey_description(config.record_hotkey, config.record_press_count)
    history_desc = _get_hotkey_description(config.history_hotkey, config.history_press_count)

    hotkeys_menu = pystray.Menu(
        pystray.MenuItem(
            f"🎤 Record: {record_desc}  — Configure...",
            _on_configure_record_shortcut
        ),
        pystray.MenuItem(
            f"📜 History: {history_desc}  — Configure...",
            _on_configure_history_shortcut
        ),
    )

    # Files submenu
    files_menu = pystray.Menu(
        pystray.MenuItem("Open configuration", _on_open_config),
        pystray.MenuItem("Open log file", _on_open_logs),
        pystray.MenuItem("Open logs folder", _on_open_log_folder)
    )

    menu = pystray.Menu(
        pystray.MenuItem(
            "System notifications",
            _on_toggle_system_notifications,
            checked=lambda item: config.system_notifications_enabled
        ),
        pystray.MenuItem(
            "Sound notifications",
            _on_toggle_sound_notifications,
            checked=lambda item: config.sound_notifications_enabled
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⌨️ Keyboard Shortcuts", hotkeys_menu),
        pystray.MenuItem("History", _on_show_history),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Mic Test (audio loopback + gauge)",
            _on_toggle_test,
            checked=lambda item: audio.is_testing_mic()
        ),
        pystray.MenuItem("AI Model", model_menu),
        pystray.MenuItem("🌐 Language", language_menu),
        pystray.MenuItem(
            f"📝 Task: {'🟣 Translate→EN' if config.task == 'translate' else '🟢 Transcribe'}",
            task_menu
        ),
        pystray.Menu.SEPARATOR,
        
        # Audio Devices
        pystray.MenuItem(mic_label, _generate_device_menu(sources, config.input_device, _on_select_source)),
        pystray.MenuItem(spk_label, _generate_device_menu(sinks, config.output_device, _on_select_sink)),
        
        pystray.MenuItem("Sound Settings...", _on_open_sound_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Files", files_menu),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit)
    )

    return menu


def create_tray_icon():
    """
    Create and return the tray icon.

    Returns:
        pystray.Icon: The tray icon instance
    """
    global _tray_icon

    menu = _create_menu()
    image = _create_image(64, 64, "yellow")  # Yellow for loading
    _tray_icon = pystray.Icon("MySuperWhisper", image, "MySuperWhisper: Loading...", menu)

    return _tray_icon


def run_tray():
    """Run the tray icon event loop (blocking)."""
    if _tray_icon:
        _tray_icon.run()


def device_monitor_worker():
    """Monitor for audio device changes and update menu."""
    last_device_signature = None

    while True:
        try:
            sources = audio.get_pulse_sources()
            sinks = audio.get_pulse_sinks()

            # Signature based on device names
            current_signature = str([
                (s['name'], s['description']) for s in sources
            ] + [
                (s['name'], s['description']) for s in sinks
            ])

            if last_device_signature is not None and current_signature != last_device_signature:
                log("Audio device change detected: Updating menu...")
                if _tray_icon:
                    try:
                        _tray_icon.menu = _create_menu()
                    except Exception as e:
                        log(f"Menu update error: {e}", "error")

            last_device_signature = current_signature
        except Exception as e:
            log(f"Device monitor error: {e}", "error")

        time.sleep(3)
