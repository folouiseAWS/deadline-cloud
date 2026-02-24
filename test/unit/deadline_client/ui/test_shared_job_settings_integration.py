# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
Unit tests for SharedJobSettingsWidget and SubmitJobToDeadlineDialog
integration with combo boxes and sticky settings (Task 5).
"""

from configparser import ConfigParser
from unittest.mock import MagicMock, patch

import pytest

try:
    from qtpy.QtCore import Signal  # type: ignore
    from qtpy.QtWidgets import QWidget  # type: ignore

    from deadline.client.ui.widgets.shared_job_settings_tab import (
        SharedJobSettingsWidget,
    )
    from deadline.client.ui.dialogs.submit_job_to_deadline_dialog import (
        SubmitJobToDeadlineDialog,
    )
    from deadline.client.ui.dataclasses import JobBundleSettings
    from deadline.client.job_bundle.submission import AssetReferences
    from deadline.client.dataclasses import SubmitterInfo
except ImportError:
    pytest.importorskip("deadline.client.ui.widgets.shared_job_settings_tab")

WIDGET_MODULE = "deadline.client.ui.widgets.shared_job_settings_tab"
DIALOG_MODULE = "deadline.client.ui.dialogs.submit_job_to_deadline_dialog"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_file():
    """Patches config_file in the widget module."""
    with patch(f"{WIDGET_MODULE}.config_file") as mock_cf:
        mock_cf.get_setting.return_value = ""
        mock_cf.read_config.return_value = ConfigParser()
        mock_cf.set_setting = MagicMock()
        yield mock_cf


@pytest.fixture
def mock_sticky_mgr():
    """Patches StickySettingsManager constructor in the widget module."""
    with patch(f"{WIDGET_MODULE}.StickySettingsManager") as mock_cls:
        instance = MagicMock()
        instance.build_override_config.return_value = ConfigParser()
        instance.get_global_value.return_value = ""
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_get_queue_params():
    """Patches get_queue_parameter_definitions to avoid real API calls."""
    with patch(f"{WIDGET_MODULE}.get_queue_parameter_definitions", return_value=[]) as mock_gqp:
        yield mock_gqp


# ---------------------------------------------------------------------------
# SharedJobSettingsWidget tests
# ---------------------------------------------------------------------------


class TestSharedJobSettingsSubmitterName:
    """Tests that submitter_name is passed through to DeadlineCloudSettingsWidget."""

    def test_submitter_name_passed_to_dcsw(
        self, qtbot, mock_config_file, mock_sticky_mgr, mock_get_queue_params
    ):
        """submitter_name should reach DeadlineCloudSettingsWidget and create a StickySettingsManager."""
        settings = JobBundleSettings()
        w = SharedJobSettingsWidget(
            initial_settings=settings,
            initial_shared_parameter_values={},
            submitter_name="Blender",
            parent=None,
        )
        qtbot.addWidget(w)

        # The StickySettingsManager was constructed with the submitter name
        # Verify the widget stored the submitter name
        assert w.deadline_cloud_settings_box._submitter_name == "Blender"

    def test_empty_submitter_name_no_sticky_manager(
        self, qtbot, mock_config_file, mock_get_queue_params
    ):
        """Empty submitter_name should result in no StickySettingsManager."""
        settings = JobBundleSettings()
        w = SharedJobSettingsWidget(
            initial_settings=settings,
            initial_shared_parameter_values={},
            submitter_name="",
            parent=None,
        )
        qtbot.addWidget(w)

        assert w.deadline_cloud_settings_box._sticky_mgr is None

    def test_default_submitter_name_is_empty(self, qtbot, mock_config_file, mock_get_queue_params):
        """Default submitter_name should be empty for backward compatibility."""
        settings = JobBundleSettings()
        w = SharedJobSettingsWidget(
            initial_settings=settings,
            initial_shared_parameter_values={},
            parent=None,
        )
        qtbot.addWidget(w)

        assert w.deadline_cloud_settings_box._sticky_mgr is None


class TestQueueParameterRefreshUsesComboBoxGetters:
    """Tests that refresh_queue_parameters reads from combo box getters."""

    def test_refresh_reads_from_combo_box(
        self, qtbot, mock_config_file, mock_sticky_mgr, mock_get_queue_params
    ):
        """refresh_queue_parameters should use get_farm_id/get_queue_id, not get_setting."""
        settings = JobBundleSettings()
        w = SharedJobSettingsWidget(
            initial_settings=settings,
            initial_shared_parameter_values={},
            submitter_name="TestApp",
            parent=None,
        )
        qtbot.addWidget(w)

        # Add items to combo boxes so getters return real IDs
        dcsw = w.deadline_cloud_settings_box
        dcsw.farm_box.box.addItem("Farm A", "farm-aaa")
        dcsw.farm_box.box.setCurrentIndex(dcsw.farm_box.box.count() - 1)
        dcsw.queue_box.box.addItem("Queue A", "queue-aaa")
        dcsw.queue_box.box.setCurrentIndex(dcsw.queue_box.box.count() - 1)

        # Reset mock to track only the refresh call
        mock_get_queue_params.reset_mock()

        w.refresh_queue_parameters()

        # The thread should have been started with the combo box values
        assert w.farm_id == "farm-aaa"
        assert w.queue_id == "queue-aaa"

    def test_refresh_with_empty_combo_does_not_start_thread(
        self, qtbot, mock_config_file, mock_sticky_mgr, mock_get_queue_params
    ):
        """When combo boxes are empty, no background thread should start."""
        settings = JobBundleSettings()
        w = SharedJobSettingsWidget(
            initial_settings=settings,
            initial_shared_parameter_values={},
            submitter_name="TestApp",
            parent=None,
        )
        qtbot.addWidget(w)

        # Combo boxes are empty by default (no items added)
        mock_get_queue_params.reset_mock()
        w.refresh_queue_parameters()

        # Should not have tried to load queue params
        mock_get_queue_params.assert_not_called()


# ---------------------------------------------------------------------------
# SubmitJobToDeadlineDialog tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth_status():
    """Patches DeadlineAuthenticationStatus for dialog tests."""
    with patch(f"{DIALOG_MODULE}.DeadlineAuthenticationStatus") as mock_cls:
        instance = MagicMock()
        instance.api_availability = True
        instance.api_availability_changed = MagicMock()
        instance.api_availability_changed.connect = MagicMock()
        mock_cls.getInstance.return_value = instance
        yield instance


class _FakeJobSettingsWidget(QWidget):
    """A real QWidget that can be placed inside a QScrollArea."""

    parameter_changed = Signal(dict)

    def __init__(self, *, initial_settings=None, parent=None):
        super().__init__(parent=parent)

    def update_settings(self, settings):
        pass


@pytest.fixture
def mock_job_settings_widget():
    """Return a real QWidget subclass so QScrollArea.setWidget() works."""
    return _FakeJobSettingsWidget


def _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget, submitter_name="TestApp"):
    """Helper to create a SubmitJobToDeadlineDialog with standard mocks."""
    settings = JobBundleSettings()
    dialog = SubmitJobToDeadlineDialog(
        job_setup_widget_type=mock_job_settings_widget,
        initial_job_settings=settings,
        initial_shared_parameter_values={},
        auto_detected_attachments=AssetReferences(),
        attachments=AssetReferences(),
        on_create_job_bundle_callback=MagicMock(),
        submitter_info=SubmitterInfo(submitter_name=submitter_name),
    )
    qtbot.addWidget(dialog)
    return dialog


class TestSubmitDialogPassesSubmitterName:
    """Tests that submitter_name flows from dialog to DeadlineCloudSettingsWidget."""

    def test_submitter_name_reaches_dcsw(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """The submitter_name from SubmitterInfo should reach DeadlineCloudSettingsWidget."""
        dialog = _create_dialog(
            qtbot, mock_auth_status, mock_job_settings_widget, submitter_name="Maya"
        )
        dcsw = dialog.shared_job_settings.deadline_cloud_settings_box
        assert dcsw._submitter_name == "Maya"


class TestSubmitButtonUsesComboBoxValues:
    """Tests that submit button state reads from combo box getters."""

    def test_button_enabled_when_combo_boxes_have_values(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """Submit button should be enabled when API available and combo boxes have IDs."""
        mock_auth_status.api_availability = True
        dialog = _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget)

        dcsw = dialog.shared_job_settings.deadline_cloud_settings_box
        dcsw.farm_box.box.addItem("Farm A", "farm-aaa")
        dcsw.farm_box.box.setCurrentIndex(dcsw.farm_box.box.count() - 1)
        dcsw.queue_box.box.addItem("Queue A", "queue-aaa")
        dcsw.queue_box.box.setCurrentIndex(dcsw.queue_box.box.count() - 1)

        # Mark queue as valid
        with patch.object(dialog.shared_job_settings, "is_queue_valid", return_value=True):
            dialog._set_submit_button_state()

        assert dialog.submit_button.isEnabled()

    def test_button_disabled_when_farm_empty(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """Submit button should be disabled when farm combo box is empty."""
        mock_auth_status.api_availability = True
        dialog = _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget)

        # Queue has value but farm is empty
        dcsw = dialog.shared_job_settings.deadline_cloud_settings_box
        dcsw.queue_box.box.addItem("Queue A", "queue-aaa")
        dcsw.queue_box.box.setCurrentIndex(dcsw.queue_box.box.count() - 1)

        with patch.object(dialog.shared_job_settings, "is_queue_valid", return_value=True):
            dialog._set_submit_button_state()

        assert not dialog.submit_button.isEnabled()

    def test_button_disabled_when_queue_empty(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """Submit button should be disabled when queue combo box is empty."""
        mock_auth_status.api_availability = True
        dialog = _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget)

        dcsw = dialog.shared_job_settings.deadline_cloud_settings_box
        dcsw.farm_box.box.addItem("Farm A", "farm-aaa")
        dcsw.farm_box.box.setCurrentIndex(dcsw.farm_box.box.count() - 1)

        with patch.object(dialog.shared_job_settings, "is_queue_valid", return_value=True):
            dialog._set_submit_button_state()

        assert not dialog.submit_button.isEnabled()


class TestSettingsChangedSignalWiring:
    """Tests that settings_changed signal triggers button state and queue refresh."""

    def test_settings_changed_triggers_button_state(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """settings_changed signal should trigger _set_submit_button_state."""
        dialog = _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget)

        with patch.object(dialog, "_set_submit_button_state") as mock_btn:
            dialog.shared_job_settings.deadline_cloud_settings_box.settings_changed.emit()
            mock_btn.assert_called()

    def test_settings_changed_triggers_queue_refresh(
        self,
        qtbot,
        mock_auth_status,
        mock_job_settings_widget,
        mock_config_file,
        mock_sticky_mgr,
        mock_get_queue_params,
    ):
        """settings_changed signal should trigger refresh_queue_parameters."""
        dialog = _create_dialog(qtbot, mock_auth_status, mock_job_settings_widget)

        with patch.object(dialog.shared_job_settings, "refresh_queue_parameters") as mock_rqp:
            dialog.shared_job_settings.deadline_cloud_settings_box.settings_changed.emit()
            mock_rqp.assert_called()
