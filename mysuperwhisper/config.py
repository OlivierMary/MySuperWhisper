"""
Configuration management for MySuperWhisper.
Handles loading/saving settings and XDG directory setup.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

# --- XDG Standard Directories ---
CONFIG_DIR = Path.home() / ".config" / "mysuperwhisper"
DATA_DIR = Path.home() / ".local" / "share" / "mysuperwhisper"
LOG_DIR = DATA_DIR / "logs"
HISTORY_FILE = DATA_DIR / "history.json"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Create directories if they don't exist
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# --- Logging Configuration ---
LOG_FILE = LOG_DIR / "mysuperwhisper.log"

# Main logger
logger = logging.getLogger("MySuperWhisper")
logger.setLevel(logging.DEBUG)

# Log format
log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# File handler (rotation: 5 files of 1MB max)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=1*1024*1024, backupCount=5, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_format)
logger.addHandler(file_handler)

# Note: Rotation happens automatically when file reaches 1MB (maxBytes)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(log_format)
logger.addHandler(console_handler)


def log(message, level="info"):
    """Log a message with the specified level."""
    if level == "debug":
        logger.debug(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    else:
        logger.info(message)


class Config:
    """Application configuration singleton."""

    def __init__(self):
        # Default values
        self.model_size = "medium"
        self.language = None  # Auto-detect if None, or use language code like "en", "fr", "es"
        self.task = "transcribe"  # "transcribe" or "translate"
        self.system_notifications_enabled = True
        self.sound_notifications_enabled = True
        self.input_device = None
        self.output_device = None
        self.restore_clipboard = True

        # Hotkey configuration
        self.record_hotkey = "ctrl_l"  # Key for recording: "ctrl_l", "alt_r", "ctrl_r", etc.
        self.record_press_count = 2  # Number of presses: 1=single, 2=double, 3=triple
        self.history_hotkey = "ctrl_l"  # Key for history popup
        self.history_press_count = 3  # Number of presses for history

    def load(self):
        """Load configuration from file."""
        needs_save = False
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)

                self.model_size = data.get("model_size", "medium")
                self.language = data.get("language")  # None = auto-detect
                self.task = data.get("task", "transcribe")
                self.system_notifications_enabled = data.get("system_notifications_enabled", True)
                self.sound_notifications_enabled = data.get("sound_notifications_enabled", True)
                self.input_device = data.get("input_device")
                self.output_device = data.get("output_device")
                self.restore_clipboard = data.get("restore_clipboard", True)

                # Hotkey configuration
                self.record_hotkey = data.get("record_hotkey", "ctrl_l")
                self.record_press_count = data.get("record_press_count", 2)
                self.history_hotkey = data.get("history_hotkey", "ctrl_l")
                self.history_press_count = data.get("history_press_count", 3)

                log(f"Configuration loaded from {CONFIG_FILE}")
                if self.language:
                    log(f"Language set to: {self.language}")
                log(f"Record hotkey: {self.record_press_count}x {self.record_hotkey}")

                # Check if new fields are missing (for config migration)
                if ("language" not in data or "task" not in data or
                    "record_hotkey" not in data or "record_press_count" not in data or
                    "restore_clipboard" not in data):
                    log("Updating config file with new fields")
                    needs_save = True
            else:
                log(f"No config file found at {CONFIG_FILE}, creating with defaults")
                needs_save = True
        except Exception as e:
            log(f"Error loading config: {e}", "error")
            needs_save = True

        # Save config if needed (first run or migration)
        if needs_save:
            self.save()

    def save(self):
        """Save configuration to file."""
        try:
            data = {
                "model_size": self.model_size,
                "language": self.language,
                "task": self.task,
                "system_notifications_enabled": self.system_notifications_enabled,
                "sound_notifications_enabled": self.sound_notifications_enabled,
                "input_device": self.input_device,
                "output_device": self.output_device,
                "record_hotkey": self.record_hotkey,
                "record_press_count": self.record_press_count,
                "history_hotkey": self.history_hotkey,
                "history_press_count": self.history_press_count,
                "restore_clipboard": self.restore_clipboard
            }

            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)

            log("Configuration saved.")
        except Exception as e:
            log(f"Error saving config: {e}", "error")

    def restore_audio_devices(self):
        """
        Restore audio devices from config.
        Now handled automatically by audio.start_stream() using config.
        """
        pass


# Global config instance
config = Config()
