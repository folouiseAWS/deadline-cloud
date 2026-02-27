# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
"""
Per-submitter sticky settings for farm, queue and storage profile.

Settings are stored in a JSON file at:
    ~/.deadline/sticky_settings/{submitter_name}.json

Missing keys mean "use global default".
"""

import json
import logging
import os
import re
from configparser import ConfigParser
from pathlib import Path
from typing import Dict

from ..config import config_file

logger = logging.getLogger(__name__)

# The resource settings that can be overridden per-submitter
STICKY_KEYS = ("defaults.farm_id", "defaults.queue_id", "settings.storage_profile_id")

# Cascade: changing farm clears queue and storage profile, changing queue clears storage profile
_CASCADE_ORDER = ["defaults.farm_id", "defaults.queue_id", "settings.storage_profile_id"]


class StickySettingsManager:
    """
    Manages per-submitter sticky settings for farm, queue and storage profile.

    The JSON structure is:
        {
            "defaults.farm_id": "farm-abc123",
            "defaults.queue_id": "queue-xyz789",
            "settings.storage_profile_id": "sp-def456"
        }
    """

    def __init__(self, submitter_name: str) -> None:
        self._submitter_name = re.sub(r"[^\w\-.]", "_", submitter_name)
        self._settings: Dict[str, str] = {}
        self._load()

    def _get_sticky_dir(self) -> Path:
        """Returns the sticky settings directory path."""
        return Path(os.path.expanduser("~")) / ".deadline" / "sticky_settings"

    def _get_sticky_file_path(self) -> Path:
        """Returns the path to this submitter's sticky settings file."""
        return self._get_sticky_dir() / f"{self._submitter_name}.json"

    def _load(self) -> None:
        """Load sticky settings from disk. Handles missing/corrupt files gracefully."""
        path = self._get_sticky_file_path()
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Only keep recognized keys
                self._settings = {k: v for k, v in data.items() if k in STICKY_KEYS}
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load sticky settings from %s: %s", path, e)
                self._settings = {}
        else:
            self._settings = {}

    def _save(self) -> None:
        """Persist sticky settings to disk."""
        path = self._get_sticky_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except OSError as e:
            logger.warning("Failed to save sticky settings to %s: %s", path, e)

    def get_effective_value(self, setting_name: str) -> str:
        """Returns the effective value: sticky override if present, else global default."""
        if setting_name in self._settings:
            return self._settings[setting_name]
        return config_file.get_setting(setting_name)

    def get_global_value(self, setting_name: str) -> str:
        """Returns the global config value (ignoring sticky overrides)."""
        return config_file.get_setting(setting_name)

    def has_sticky_value(self, setting_name: str) -> bool:
        """Returns True if a sticky override exists for this setting (including empty string)."""
        return setting_name in self._settings

    def set_value(self, setting_name: str, value: str) -> None:
        """Sets a sticky override for the given setting and persists to disk."""
        if setting_name in STICKY_KEYS:
            self._settings[setting_name] = value
            self._save()

    def clear_downstream(self, setting_name: str) -> None:
        """
        Clears all sticky settings downstream of the given setting
        in the cascade order (farm -> queue -> storage_profile).
        """
        try:
            idx = _CASCADE_ORDER.index(setting_name)
        except ValueError:
            return
        for key in _CASCADE_ORDER[idx + 1 :]:
            self._settings.pop(key, None)
        self._save()

    def clear(self) -> None:
        """Removes all sticky overrides (reverts to global defaults)."""
        self._settings.clear()
        self._save()

    def build_override_config(self) -> ConfigParser:
        """
        Returns a ConfigParser that merges global config with sticky overrides.
        This config object can be passed to combo boxes via set_config().
        Does not modify the global config singleton.
        """
        # Create a fresh ConfigParser as a copy of the global config
        global_config = config_file.read_config()
        config = ConfigParser(interpolation=None)
        config.read_dict({section: dict(global_config[section]) for section in global_config})
        # Overlay sticky values using set_setting with the config param
        # (this modifies the local ConfigParser without writing to disk)
        for key in STICKY_KEYS:
            if key in self._settings:
                config_file.set_setting(key, self._settings[key], config)
        return config

    def reload(self) -> None:
        """Re-reads sticky settings from disk (e.g., after external changes)."""
        self._load()
