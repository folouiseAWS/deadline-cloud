# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

import json
from configparser import ConfigParser
from unittest.mock import MagicMock, patch

import pytest

from deadline.client.ui._sticky_settings import (
    StickySettingsManager,
)


@pytest.fixture
def sticky_dir(tmp_path):
    """Provides a temporary sticky settings directory."""
    d = tmp_path / ".deadline" / "sticky_settings"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def mock_config_file():
    """Patches config_file used by StickySettingsManager."""
    with patch("deadline.client.ui._sticky_settings.config_file") as mock_cf:
        mock_cf.get_setting.return_value = ""
        mock_cf.read_config.return_value = ConfigParser()
        mock_cf.set_setting = MagicMock()
        yield mock_cf


class TestStickySettingsManagerLoad:
    """Tests for _load behavior."""

    def test_load_missing_file(self, tmp_path, mock_config_file):
        """When no sticky file exists, settings should be empty."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=tmp_path):
            mgr = StickySettingsManager("test_submitter")
        assert mgr._settings == {}

    def test_load_valid_json(self, sticky_dir, mock_config_file):
        """Valid JSON with recognized keys should be loaded."""
        data = {"defaults.queue_id": "queue-456", "settings.storage_profile_id": "sp-789"}
        (sticky_dir / "test_submitter.json").write_text(json.dumps(data), encoding="utf-8")

        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
        assert mgr._settings == data

    def test_load_corrupt_json(self, sticky_dir, mock_config_file):
        """Corrupt JSON should result in empty settings with a warning."""
        (sticky_dir / "test_submitter.json").write_text("not valid json{{{", encoding="utf-8")

        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
        assert mgr._settings == {}

    def test_load_filters_unrecognized_keys(self, sticky_dir, mock_config_file):
        """Unrecognized keys in the JSON should be silently dropped."""
        data = {
            "defaults.queue_id": "queue-123",
            "bogus.key": "should-be-dropped",
            "another_unknown": "also-dropped",
        }
        (sticky_dir / "test_submitter.json").write_text(json.dumps(data), encoding="utf-8")

        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
        assert mgr._settings == {"defaults.queue_id": "queue-123"}
        assert "bogus.key" not in mgr._settings


class TestStickySettingsManagerSaveAndRoundTrip:
    """Tests for _save and reload round-trip."""

    def test_save_and_reload(self, sticky_dir, mock_config_file):
        """Saving and reloading should produce identical settings."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "queue-xyz")
            mgr.set_value("settings.storage_profile_id", "sp-def")

            # Reload from disk
            mgr.reload()
        assert mgr._settings == {
            "defaults.queue_id": "queue-xyz",
            "settings.storage_profile_id": "sp-def",
        }


class TestStickySettingsManagerGetEffectiveValue:
    """Tests for get_effective_value."""

    def test_returns_sticky_when_present(self, sticky_dir, mock_config_file):
        """When a sticky override exists, it should be returned."""
        mock_config_file.get_setting.return_value = "global-queue"
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "sticky-queue")
        assert mgr.get_effective_value("defaults.queue_id") == "sticky-queue"

    def test_falls_back_to_global(self, sticky_dir, mock_config_file):
        """When no sticky override exists, global default should be returned."""
        mock_config_file.get_setting.return_value = "global-queue"
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
        assert mgr.get_effective_value("defaults.queue_id") == "global-queue"

    def test_empty_sticky_falls_back_to_global(self, sticky_dir, mock_config_file):
        """An empty string sticky value should fall back to global."""
        mock_config_file.get_setting.return_value = "global-queue"
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "")
        assert mgr.get_effective_value("defaults.queue_id") == "global-queue"


class TestStickySettingsManagerClearDownstream:
    """Tests for clear_downstream."""

    def test_queue_clears_storage_profile(self, sticky_dir, mock_config_file):
        """Clearing downstream of queue should remove storage profile."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "queue-1")
            mgr.set_value("settings.storage_profile_id", "sp-1")

            mgr.clear_downstream("defaults.queue_id")

        assert mgr._settings == {
            "defaults.queue_id": "queue-1",
        }

    def test_storage_profile_clears_nothing(self, sticky_dir, mock_config_file):
        """Clearing downstream of storage profile should remove nothing."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "queue-1")
            mgr.set_value("settings.storage_profile_id", "sp-1")

            mgr.clear_downstream("settings.storage_profile_id")

        assert mgr._settings == {
            "defaults.queue_id": "queue-1",
            "settings.storage_profile_id": "sp-1",
        }


class TestStickySettingsManagerBuildOverrideConfig:
    """Tests for build_override_config."""

    def test_merges_sticky_onto_global(self, sticky_dir, mock_config_file):
        """build_override_config should overlay sticky values onto global config."""
        global_config = ConfigParser()
        global_config["defaults"] = {"farm_id": "global-farm", "queue_id": "global-queue"}
        mock_config_file.read_config.return_value = global_config

        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "sticky-queue")

            result = mgr.build_override_config()

        # set_setting should have been called with the sticky value and the new config
        mock_config_file.set_setting.assert_called_with("defaults.queue_id", "sticky-queue", result)


class TestStickySettingsManagerClear:
    """Tests for clear."""

    def test_clear_removes_all(self, sticky_dir, mock_config_file):
        """clear() should remove all sticky values."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", "queue-1")
            mgr.set_value("settings.storage_profile_id", "sp-1")

            mgr.clear()

        assert mgr._settings == {}


class TestStickySettingsManagerSanitization:
    """Tests for submitter name sanitization."""

    def test_special_chars_replaced(self, sticky_dir, mock_config_file):
        """Special characters in submitter name should be replaced with underscores."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("My App/v2.0 (beta)")
        assert mgr._submitter_name == "My_App_v2.0__beta_"

    def test_safe_chars_preserved(self, sticky_dir, mock_config_file):
        """Word chars, hyphens, and dots should be preserved."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("maya-2024.1")
        assert mgr._submitter_name == "maya-2024.1"

    def test_path_separators_replaced(self, sticky_dir, mock_config_file):
        """Path separators should be replaced to prevent directory traversal."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("../../etc/passwd")
        assert "/" not in mgr._submitter_name
        assert "\\" not in mgr._submitter_name


class TestStickySettingsManagerSetValue:
    """Tests for set_value."""

    def test_unrecognized_key_ignored(self, sticky_dir, mock_config_file):
        """Setting an unrecognized key should produce no change."""
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=sticky_dir):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("bogus.key", "some-value")
        assert "bogus.key" not in mgr._settings
