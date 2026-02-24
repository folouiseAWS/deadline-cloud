# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from unittest.mock import MagicMock, patch

import pytest

try:
    from qtpy.QtCore import Signal  # type: ignore
    from qtpy.QtWidgets import QWidget  # type: ignore

    from deadline.client.ui.dialogs.submit_job_to_deadline_dialog import SubmitJobToDeadlineDialog
    from deadline.client.ui.dataclasses import JobBundleSettings
    from deadline.client.job_bundle.submission import AssetReferences
except ImportError:
    pytest.importorskip("deadline.client.ui.dialogs.submit_job_to_deadline_dialog")


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


@patch("deadline.client.ui.dialogs.submit_job_to_deadline_dialog.DeadlineAuthenticationStatus")
def test_load_bundle_button_shown_when_browse_enabled(
    mock_auth_status, qtbot, mock_job_settings_widget
):
    """Test that the Load a different job bundle button is shown when browse_enabled is True."""
    mock_auth_status.getInstance.return_value = MagicMock()

    settings = JobBundleSettings(browse_enabled=True)

    dialog = SubmitJobToDeadlineDialog(
        job_setup_widget_type=mock_job_settings_widget,
        initial_job_settings=settings,
        initial_shared_parameter_values={},
        auto_detected_attachments=AssetReferences(),
        attachments=AssetReferences(),
        on_create_job_bundle_callback=MagicMock(),
    )
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "load_bundle_button")
    assert dialog.load_bundle_button.text() == "Load Bundle"


@patch("deadline.client.ui.dialogs.submit_job_to_deadline_dialog.DeadlineAuthenticationStatus")
def test_load_bundle_button_hidden_when_browse_disabled(
    mock_auth_status, qtbot, mock_job_settings_widget
):
    """Test that the Load a different job bundle button is not shown when browse_enabled is False."""
    mock_auth_status.getInstance.return_value = MagicMock()

    settings = JobBundleSettings(browse_enabled=False)

    dialog = SubmitJobToDeadlineDialog(
        job_setup_widget_type=mock_job_settings_widget,
        initial_job_settings=settings,
        initial_shared_parameter_values={},
        auto_detected_attachments=AssetReferences(),
        attachments=AssetReferences(),
        on_create_job_bundle_callback=MagicMock(),
    )
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "load_bundle_button")
