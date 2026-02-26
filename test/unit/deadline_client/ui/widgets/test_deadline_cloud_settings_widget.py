# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Unit tests for DeadlineCloudSettingsWidget with combo boxes.
"""

from configparser import ConfigParser
from unittest.mock import MagicMock, patch

import pytest

try:
    from deadline.client.ui.widgets.shared_job_settings_tab import DeadlineCloudSettingsWidget
    from deadline.client.ui.widgets._resource_combo_boxes import (
        DeadlineQueueListComboBox,
        DeadlineStorageProfileNameListComboBox,
    )
except ImportError:
    pytest.importorskip("deadline.client.ui.widgets.shared_job_settings_tab")


MODULE_PATH = "deadline.client.ui.widgets.shared_job_settings_tab"


@pytest.fixture
def mock_config_file():
    """Patches config_file used by DeadlineCloudSettingsWidget and StickySettingsManager."""
    with patch(f"{MODULE_PATH}.config_file") as mock_cf:
        mock_cf.get_setting.return_value = ""
        mock_cf.read_config.return_value = ConfigParser()
        mock_cf.set_setting = MagicMock()
        yield mock_cf


@pytest.fixture
def mock_sticky_mgr():
    """Patches StickySettingsManager constructor."""
    with patch(f"{MODULE_PATH}.StickySettingsManager") as mock_cls:
        instance = MagicMock()
        instance.build_override_config.return_value = ConfigParser()
        instance.get_global_value.return_value = ""
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def widget_no_sticky(qtbot, mock_config_file):
    """Creates a DeadlineCloudSettingsWidget without sticky settings."""
    w = DeadlineCloudSettingsWidget(submitter_name="", parent=None)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def widget_with_sticky(qtbot, mock_config_file, mock_sticky_mgr):
    """Creates a DeadlineCloudSettingsWidget with sticky settings."""
    w = DeadlineCloudSettingsWidget(submitter_name="TestSubmitter", parent=None)
    qtbot.addWidget(w)
    return w


class TestBuildUI:
    """Tests for _build_ui creating combo boxes."""

    def test_creates_queue_combo_box(self, widget_no_sticky):
        assert isinstance(widget_no_sticky.queue_box, DeadlineQueueListComboBox)

    def test_creates_storage_profile_combo_box(self, widget_no_sticky):
        assert isinstance(
            widget_no_sticky.storage_profile_box, DeadlineStorageProfileNameListComboBox
        )

    def test_has_settings_changed_signal(self, widget_no_sticky):
        """The widget should have a settings_changed signal."""
        assert hasattr(widget_no_sticky, "settings_changed")

    def test_refreshing_flag_initialized_false(self, widget_no_sticky):
        assert widget_no_sticky._refreshing is False


class TestQueueChangeCascade:
    """Tests that queue change cascades to storage profile."""

    def test_queue_change_clears_downstream_sticky(self, widget_with_sticky, mock_sticky_mgr):
        """Queue change should clear storage profile from sticky."""
        widget_with_sticky.queue_box.box.addItem("Queue A", "queue-aaa")
        widget_with_sticky.queue_box.box.setCurrentIndex(
            widget_with_sticky.queue_box.box.count() - 1
        )

        mock_sticky_mgr.set_value.assert_any_call("defaults.queue_id", "queue-aaa")
        mock_sticky_mgr.clear_downstream.assert_called_with("defaults.queue_id")

    def test_queue_change_refreshes_storage_profile(self, widget_with_sticky, mock_sticky_mgr):
        """Queue change should refresh storage profile list."""
        with patch.object(
            widget_with_sticky.storage_profile_box, "refresh_list"
        ) as mock_sp_refresh:
            widget_with_sticky.queue_box.box.addItem("Queue B", "queue-bbb")
            widget_with_sticky.queue_box.box.setCurrentIndex(
                widget_with_sticky.queue_box.box.count() - 1
            )
            mock_sp_refresh.assert_called()


class TestSettingsChangedSignal:
    """Tests that settings_changed signal is emitted on combo box changes."""

    def test_emitted_on_queue_change(self, qtbot, widget_with_sticky):
        with qtbot.waitSignal(widget_with_sticky.settings_changed, timeout=1000):
            widget_with_sticky.queue_box.box.addItem("Queue A", "queue-aaa")
            widget_with_sticky.queue_box.box.setCurrentIndex(
                widget_with_sticky.queue_box.box.count() - 1
            )

    def test_emitted_on_storage_profile_change(self, qtbot, widget_with_sticky):
        with qtbot.waitSignal(widget_with_sticky.settings_changed, timeout=1000):
            widget_with_sticky.storage_profile_box.box.addItem("SP A", "sp-aaa")
            widget_with_sticky.storage_profile_box.box.setCurrentIndex(
                widget_with_sticky.storage_profile_box.box.count() - 1
            )


class TestRefreshSettingControls:
    """Tests for refresh_setting_controls."""

    def test_authorized_calls_refresh_list(self, widget_with_sticky, mock_sticky_mgr):
        """When authorized, refresh_list should be called on all boxes."""
        with patch.object(widget_with_sticky.queue_box, "refresh_list") as mock_q, patch.object(
            widget_with_sticky.storage_profile_box, "refresh_list"
        ) as mock_sp:
            widget_with_sticky.refresh_setting_controls(deadline_authorized=True)
            mock_q.assert_called_once()
            mock_sp.assert_called_once()

    def test_unauthorized_calls_refresh_selected_id(self, widget_with_sticky, mock_sticky_mgr):
        """When not authorized, only refresh_selected_id should be called."""
        with patch.object(
            widget_with_sticky.queue_box, "refresh_selected_id"
        ) as mock_q, patch.object(
            widget_with_sticky.storage_profile_box, "refresh_selected_id"
        ) as mock_sp:
            widget_with_sticky.refresh_setting_controls(deadline_authorized=False)
            mock_q.assert_called_once()
            mock_sp.assert_called_once()

    def test_reloads_sticky_settings(self, widget_with_sticky, mock_sticky_mgr):
        """refresh_setting_controls should reload sticky settings."""
        widget_with_sticky.refresh_setting_controls(deadline_authorized=False)
        mock_sticky_mgr.reload.assert_called_once()

    def test_refreshing_flag_reset_on_exception(self, widget_with_sticky, mock_sticky_mgr):
        """_refreshing should be reset to False even if an exception occurs."""
        mock_sticky_mgr.reload.side_effect = RuntimeError("test error")
        with pytest.raises(RuntimeError):
            widget_with_sticky.refresh_setting_controls(deadline_authorized=True)
        assert widget_with_sticky._refreshing is False


class TestRefreshingFlagSuppression:
    """Tests that _refreshing flag suppresses change handlers."""

    def test_queue_change_suppressed_when_refreshing(self, widget_with_sticky, mock_sticky_mgr):
        """When _refreshing is True, queue change handler should do nothing."""
        widget_with_sticky._refreshing = True
        mock_sticky_mgr.set_value.reset_mock()

        widget_with_sticky.queue_box.box.addItem("Queue X", "queue-xxx")
        widget_with_sticky.queue_box.box.setCurrentIndex(
            widget_with_sticky.queue_box.box.count() - 1
        )

        mock_sticky_mgr.set_value.assert_not_called()

    def test_storage_profile_change_suppressed_when_refreshing(
        self, widget_with_sticky, mock_sticky_mgr
    ):
        """When _refreshing is True, storage profile change handler should do nothing."""
        widget_with_sticky._refreshing = True
        mock_sticky_mgr.set_value.reset_mock()

        widget_with_sticky.storage_profile_box.box.addItem("SP X", "sp-xxx")
        widget_with_sticky.storage_profile_box.box.setCurrentIndex(
            widget_with_sticky.storage_profile_box.box.count() - 1
        )

        mock_sticky_mgr.set_value.assert_not_called()


class TestGetConfigReturnsOverride:
    """Tests that get_config() returns the override config, not global."""

    def test_get_config_has_sticky_values(
        self, widget_with_sticky, mock_sticky_mgr, mock_config_file
    ):
        """get_config() should return the config built from sticky overrides."""
        override_config = ConfigParser()
        override_config["defaults"] = {"farm_id": "sticky-farm", "queue_id": "sticky-queue"}
        mock_sticky_mgr.build_override_config.return_value = override_config

        widget_with_sticky._rebuild_override_config()
        result = widget_with_sticky.get_config()

        assert result is override_config

    def test_get_config_without_sticky_returns_global(self, widget_no_sticky, mock_config_file):
        """Without sticky manager, get_config() should return global config."""
        global_config = ConfigParser()
        global_config["defaults"] = {"farm_id": "global-farm"}
        mock_config_file.read_config.return_value = global_config

        widget_no_sticky._rebuild_override_config()
        result = widget_no_sticky.get_config()

        assert result.get("defaults", "farm_id") == "global-farm"
