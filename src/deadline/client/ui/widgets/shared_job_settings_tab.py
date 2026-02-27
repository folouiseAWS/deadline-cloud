# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

"""
A UI Widget containing the render setup tab
"""

from __future__ import annotations

from configparser import ConfigParser

import threading
from typing import Any, Optional

from qtpy.QtCore import Signal  # type: ignore
from qtpy.QtWidgets import (  # type: ignore
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...config import config_file
from .._utils import CancelationFlag, tr
from .._sticky_settings import StickySettingsManager
from ._resource_combo_boxes import (
    DeadlineFarmListComboBox,
    DeadlineQueueListComboBox,
    DeadlineStorageProfileNameListComboBox,
)
from .openjd_parameters_widget import OpenJDParametersWidget
from ...api import get_queue_parameter_definitions

import logging

logger = logging.getLogger(__name__)


class SharedJobSettingsWidget(QWidget):  # pylint: disable=too-few-public-methods
    """
    Widget that holds Job setup shared across all job types.


    Signals:
        parameter_changed: This is sent whenever a parameter value in the widget changes. The message
            is a copy of the parameter definition with the "value" key containing the new value.

    Args:
        initial_settings: dataclass containing the job-specific settings.
        initial_shared_parameter_values: (dict[str, Any]): A dict of parameter values {<name>, <value>, ...}
            to override default queue parameter values from the queue. For example,
            a Rez queue environment may have a default "" for the RezPackages parameter, but a Maya
            submitter would override that default with "maya-2023" or similar.
        parent: The parent Qt Widget.
    """

    parameter_changed = Signal(dict)

    # Emitted when the queue parameter validity state changes
    valid_parameters = Signal(bool)

    # Emitted when the background refresh thread catches an exception,
    # provides (operation_name, BaseException)
    _background_exception = Signal(str, BaseException)

    # Emitted when an async queue parameters loading thread completes,
    # provides (refresh_id, queue_parameters)
    _queue_parameters_update = Signal(int, list)

    def __init__(
        self,
        *,
        initial_settings: Any,
        initial_shared_parameter_values: dict[str, Any],
        submitter_name: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent=parent)
        layout = QVBoxLayout(self)

        # This is a dictionary {<name>: <value>} containing values to
        # override the queue parameter defaults.
        self.initial_shared_parameter_values = initial_shared_parameter_values

        self.shared_job_properties_box = SharedJobPropertiesWidget(
            initial_settings=initial_settings, parent=self
        )
        layout.addWidget(self.shared_job_properties_box)

        self.deadline_cloud_settings_box = DeadlineCloudSettingsWidget(
            submitter_name=submitter_name, parent=self
        )
        layout.addWidget(self.deadline_cloud_settings_box)

        self.queue_parameters_box = OpenJDParametersWidget(
            async_loading_state="Loading Queue Environments...", parent=self
        )
        layout.addWidget(self.queue_parameters_box)
        self.queue_parameters_box.parameter_changed.connect(
            lambda message: self.parameter_changed.emit(message)
        )

        self.__refresh_queue_parameters_thread: Optional[threading.Thread] = None
        self.__refresh_queue_parameters_id = 0
        self.__valid_queue = False
        self.canceled = CancelationFlag()
        self.destroyed.connect(self.canceled.set_canceled)
        self._queue_parameters_update.connect(self._handle_queue_parameters_update)
        self._background_exception.connect(self._handle_background_queue_parameters_exception)
        self._start_load_queue_parameters_thread()

        # Set any "deadline:*" parameters, like deadline:priority.
        # The queue parameters will be set asynchronously by the background thread.
        for name, value in initial_shared_parameter_values.items():
            if name.startswith("deadline:"):
                self.set_parameter_value({"name": name, "value": value})

    def __del__(self):
        self.canceled.set_canceled()
        if (
            self.__refresh_queue_parameters_thread
            and self.__refresh_queue_parameters_thread.is_alive()
        ):
            self.__refresh_queue_parameters_thread.join()

    def refresh_ui(self, job_settings: Any, load_new_bundle: bool = False):
        # Refresh the job settings in the UI
        self.shared_job_properties_box.refresh_ui(job_settings)

        if load_new_bundle:
            # Update the initial shared parameter values corresponding to the new job bundle
            self.initial_shared_parameter_values = {}
            for parameter in job_settings.parameters:
                if "default" in parameter or "value" in parameter:
                    self.initial_shared_parameter_values[parameter["name"]] = parameter.get(
                        "value", parameter.get("default")
                    )
        self.refresh_queue_parameters(load_new_bundle)

    def refresh_queue_parameters(self, load_new_bundle: bool = False):
        """
        If the default queue id or job bundle has changed, refresh the queue parameters.
        """
        farm_id = self.deadline_cloud_settings_box.get_farm_id()
        queue_id = self.deadline_cloud_settings_box.get_queue_id()
        if not farm_id or not queue_id:
            self.queue_parameters_box.rebuild_ui(async_loading_state="")
            return  # If the user has not selected a farm or queue ID, don't try to load
        if (
            self.queue_parameters_box.async_loading_state
            or queue_id != self.queue_id
            or load_new_bundle
        ):
            self.queue_parameters_box.rebuild_ui(
                async_loading_state="Reloading Queue Environments..."
            )
            # Join the thread if the queue id or job bundle has changed and the thread is running
            if (
                (queue_id != self.queue_id or load_new_bundle)
                and self.__refresh_queue_parameters_thread
                and self.__refresh_queue_parameters_thread.is_alive()
            ):
                self.__refresh_queue_parameters_thread.join()

            # Start the thread if it doesn't exist or is not alive
            if (
                not self.__refresh_queue_parameters_thread
                or not self.__refresh_queue_parameters_thread.is_alive()
            ):
                self._start_load_queue_parameters_thread()

    def _handle_background_queue_parameters_exception(self, title: str, error: BaseException):
        self.__valid_queue = False
        self.valid_parameters.emit(False)
        if self.__refresh_queue_parameters_thread:
            self.canceled.set_canceled()
            self.__refresh_queue_parameters_thread.join()
        self.queue_parameters_box.rebuild_ui(
            async_loading_state="Error loading queue environments: {}\n\nError traceback: {}".format(
                title, error
            )
        )

    def _start_load_queue_parameters_thread(self):
        """
        Starts a background thread to load the queue parameters.
        """
        self.farm_id = farm_id = self.deadline_cloud_settings_box.get_farm_id()
        self.queue_id = queue_id = self.deadline_cloud_settings_box.get_queue_id()
        if not self.farm_id or not self.queue_id:
            # If the user has not selected a farm or queue ID, don't bother starting
            # the thread.
            return
        self.__refresh_queue_parameters_id += 1
        self.canceled = CancelationFlag()
        self.__refresh_queue_parameters_thread = threading.Thread(
            target=self._load_queue_parameters_thread_function,
            name="AWS Deadline Cloud load queue parameters thread",
            args=(self.__refresh_queue_parameters_id, farm_id, queue_id),
        )
        self.__refresh_queue_parameters_thread.start()

    def is_queue_valid(self) -> bool:
        return self.__valid_queue

    def _handle_queue_parameters_update(self, refresh_id, queue_parameters):
        # Apply the refresh if it's still for the latest call
        if refresh_id == self.__refresh_queue_parameters_id:
            self.__valid_queue = True
            self.valid_parameters.emit(True)
            # Apply the initial queue parameter values
            for parameter in queue_parameters:
                if parameter["name"] in self.initial_shared_parameter_values:
                    parameter["value"] = self.initial_shared_parameter_values[parameter["name"]]
            self.queue_parameters_box.rebuild_ui(parameter_definitions=queue_parameters)

    def _load_queue_parameters_thread_function(self, refresh_id: int, farm_id: str, queue_id: str):
        """
        This function gets started in a background thread to refresh the list.
        """
        try:
            queue_parameters = get_queue_parameter_definitions(farmId=farm_id, queueId=queue_id)
            if not self.canceled:
                self._queue_parameters_update.emit(refresh_id, queue_parameters)
        except BaseException as e:
            if not self.canceled:
                self._background_exception.emit("Invalid queue parameters", e)

    def update_settings(self, settings):
        self.shared_job_properties_box.update_settings(settings)

    def get_parameters(self):
        """
        Returns a list of OpenJD parameter definition dicts with
        a "value" key filled from the widget.
        """
        queue_parameters = self.queue_parameters_box.get_parameters()
        deadline_shared_job_parameters = self.shared_job_properties_box.get_parameters()

        return queue_parameters + deadline_shared_job_parameters

    def set_parameter_value(self, parameter: dict[str, Any]):
        """
        Given an OpenJD parameter definition with a "value" key,
        set the parameter value in the widget.

        If the parameter value cannot be set, raises a KeyError.
        """
        if parameter["name"].startswith("deadline:"):
            self.shared_job_properties_box.set_parameter_value(parameter)
        else:
            self.queue_parameters_box.set_parameter_value(parameter)


class SharedJobPropertiesWidget(QGroupBox):  # pylint: disable=too-few-public-methods
    """
    UI element to hold top level description components of the submission

    The settings object should be a dataclass with:
      - `name: str`        The name of the Job to submit.
      - `description: str`  The description of the Job to submit.
    """

    def __init__(self, *, initial_settings, parent: Optional[QWidget] = None):
        super().__init__(tr("Job Properties"), parent=parent)

        self._build_ui()
        self.refresh_ui(initial_settings)

    def _build_ui(self):
        self.layout = QFormLayout(self)
        self.layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.sub_name_edit = QLineEdit()
        self.sub_name_edit.setMaxLength(128)
        self.layout.addRow("Name", self.sub_name_edit)

        self.desc_label = QLabel(tr("Description"))
        self.desc_edit = QLineEdit()
        self.desc_edit.setMaxLength(2048)
        self.layout.addRow(self.desc_label, self.desc_edit)

        self.priority_box_label = QLabel(tr("Priority"))
        self.priority_box = QSpinBox(parent=self)
        self.priority_box.setRange(0, 100)
        self.layout.addRow(self.priority_box_label, self.priority_box)

        self.initial_status_box_label = QLabel(tr("Initial state"))
        self.initial_status_box = QComboBox(parent=self)
        self.initial_status_box.addItems(["READY", "SUSPENDED"])
        self.layout.addRow(self.initial_status_box_label, self.initial_status_box)

        self.max_failed_tasks_count_box_label = QLabel(tr("Maximum failed tasks count"))
        self.max_failed_tasks_count_box_label.setToolTip(
            "Maximum number of tasks that can fail before the job will be marked as failed."
        )
        self.max_failed_tasks_count_box = QSpinBox(parent=self)
        self.max_failed_tasks_count_box.setRange(0, 2147483647)
        self.layout.addRow(self.max_failed_tasks_count_box_label, self.max_failed_tasks_count_box)

        self.max_retries_per_task_box_label = QLabel(tr("Maximum retries per task"))
        self.max_retries_per_task_box_label.setToolTip(
            "Maximum number of times that a task will retry before it's marked as failed."
        )
        self.max_retries_per_task_box = QSpinBox(parent=self)
        self.max_retries_per_task_box.setRange(0, 2147483647)
        self.layout.addRow(self.max_retries_per_task_box_label, self.max_retries_per_task_box)

        self.max_worker_count_box_label = QLabel(tr("Maximum worker count"))
        self.max_worker_count_box_label.setToolTip(tr("Maximum worker count of job."))
        self.max_worker_count_box = QSpinBox()
        self.max_worker_count_box.setRange(1, 2147483647)
        self.unlimited_max_worker_count = QRadioButton(tr("No max worker count"))
        self.limited_max_worker_count = QRadioButton(tr("Set max worker count"))
        self.limited_max_worker_count.toggled.connect(
            self.limited_max_worker_count_radio_button_toggled
        )
        self.max_worker_count_layout = QVBoxLayout()
        self.max_worker_count_layout.addWidget(self.unlimited_max_worker_count)
        self.max_worker_count_layout.addWidget(self.limited_max_worker_count)
        self.max_worker_count_layout.addWidget(self.max_worker_count_box)
        self.layout.addRow(self.max_worker_count_box_label, self.max_worker_count_layout)

    def limited_max_worker_count_radio_button_toggled(self, state):
        """
        Enable the max worker count text box when limited max worker count radio button is enabled.
        """
        self.max_worker_count_box.setHidden(not state)

    def _has_compatible_attr(self, obj, attr_name, expected_type):
        """
        Determine if attribute exists and if the type is correct.
        """
        # DCCs can have anything in the settings object since they define their own dataclass to pass in.
        # Changing what we look for below may cause breaking changes in usage of this library.
        return isinstance(getattr(obj, attr_name, None), expected_type)

    def refresh_ui(self, settings: Any):
        self.sub_name_edit.setText(settings.name)
        self.desc_edit.setText(settings.description)

        # Set all fields with type checking
        self.initial_status_box.setCurrentText(
            settings.initial_status
            if self._has_compatible_attr(settings, "initial_status", str)
            else "READY"
        )
        self.max_failed_tasks_count_box.setValue(
            settings.max_failed_tasks_count
            if self._has_compatible_attr(settings, "max_failed_tasks_count", int)
            else 20
        )
        self.max_retries_per_task_box.setValue(
            settings.max_retries_per_task
            if self._has_compatible_attr(settings, "max_retries_per_task", int)
            else 5
        )
        self.priority_box.setValue(
            settings.priority if self._has_compatible_attr(settings, "priority", int) else 50
        )

        has_limited_max_worker_count = (
            (settings.max_worker_count > 0)
            if self._has_compatible_attr(settings, "max_worker_count", int)
            else False
        )
        self.unlimited_max_worker_count.setChecked(not has_limited_max_worker_count)
        self.limited_max_worker_count.setChecked(has_limited_max_worker_count)
        self.max_worker_count_box.setHidden(not has_limited_max_worker_count)
        if has_limited_max_worker_count:
            self.max_worker_count_box.setValue(settings.max_worker_count)

    def set_parameter_value(self, parameter: dict[str, Any]):
        """
        Given an OpenJD parameter definition with a "value" key,
        set the parameter value in the widget.

        If the parameter value cannot be set, raises a KeyError.
        """
        parameter_name = parameter["name"]
        if parameter_name == "deadline:targetTaskRunStatus":
            self.initial_status_box.setCurrentText(parameter["value"])
        elif parameter_name == "deadline:maxFailedTasksCount":
            self.max_failed_tasks_count_box.setValue(parameter["value"])
        elif parameter_name == "deadline:maxRetriesPerTask":
            self.max_retries_per_task_box.setValue(parameter["value"])
        elif parameter_name == "deadline:priority":
            self.priority_box.setValue(parameter["value"])
        elif parameter_name == "deadline:maxWorkerCount":
            if parameter["value"] == -1:
                self.unlimited_max_worker_count.setChecked(True)
                self.limited_max_worker_count.setChecked(False)
                self.max_worker_count_box.setHidden(True)
            else:
                self.unlimited_max_worker_count.setChecked(False)
                self.limited_max_worker_count.setChecked(True)
                self.max_worker_count_box.setHidden(False)
                self.max_worker_count_box.setValue(parameter["value"])
        else:
            raise KeyError(parameter_name)

    def get_parameters(self):
        """
        Returns a list of OpenJD parameter definition dicts with
        a "value" key filled from the widget.
        """
        job_parameters = [
            {
                "name": "deadline:targetTaskRunStatus",
                "type": "STRING",
                "userInterface": {
                    "control": "DROPDOWN_LIST",
                    "label": "Initial state",
                },
                "allowedValues": ["READY", "SUSPENDED"],
                "value": self.initial_status_box.currentText(),
            },
            {
                "name": "deadline:maxFailedTasksCount",
                "description": "Maximum number of Tasks that can fail before the Job will be marked as failed.",
                "type": "INT",
                "userInterface": {
                    "control": "SPIN_BOX",
                    "label": "Maximum failed tasks count",
                },
                "minValue": 0,
                "value": self.max_failed_tasks_count_box.value(),
            },
            {
                "name": "deadline:maxRetriesPerTask",
                "description": "Maximum number of times that a task will retry before it's marked as failed.",
                "type": "INT",
                "userInterface": {
                    "control": "SPIN_BOX",
                    "label": "Maximum retries per task",
                },
                "minValue": 0,
                "value": self.max_retries_per_task_box.value(),
            },
            {"name": "deadline:priority", "type": "INT", "value": self.priority_box.value()},
        ]
        if not self.unlimited_max_worker_count.isChecked():
            job_parameters.append(
                {
                    "name": "deadline:maxWorkerCount",
                    "type": "INT",
                    "value": self.max_worker_count_box.value(),
                }
            )
        return job_parameters

    def update_settings(self, settings):
        """
        Update a given instance of scene settings with updated values.
        """
        # TODO: Extract sticky settings from per-DCC implementation to centralized.
        settings.name = self.sub_name_edit.text()
        settings.description = self.desc_edit.text()

        # Set all fields with type checking
        if self._has_compatible_attr(settings, "initial_status", str):
            settings.initial_status = self.initial_status_box.currentText()

        if self._has_compatible_attr(settings, "max_failed_tasks_count", int):
            settings.max_failed_tasks_count = self.max_failed_tasks_count_box.value()

        if self._has_compatible_attr(settings, "max_retries_per_task", int):
            settings.max_retries_per_task = self.max_retries_per_task_box.value()

        if self._has_compatible_attr(settings, "priority", int):
            settings.priority = self.priority_box.value()

        # Handle `max_worker_count` based on UI selection:
        # Preserve unlimited worker setting by using -1 instead of overriding with spin box value
        if self._has_compatible_attr(settings, "max_worker_count", int):
            if self.unlimited_max_worker_count.isChecked():
                settings.max_worker_count = -1  # -1 denotes no max worker count limits.
            else:
                settings.max_worker_count = self.max_worker_count_box.value()


class DeadlineCloudSettingsWidget(QGroupBox):
    """
    UI component for Deadline Cloud settings in the submit dialog.
    Uses editable combo boxes instead of read-only labels.
    """

    # Emitted when queue or storage profile changes
    settings_changed = Signal()

    def __init__(
        self,
        *,
        submitter_name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(tr("Deadline Cloud settings"), parent=parent)
        self._submitter_name = submitter_name
        self._sticky_mgr: Optional[StickySettingsManager] = None
        if submitter_name:
            self._sticky_mgr = StickySettingsManager(submitter_name)

        self.layout = QFormLayout(self)
        self.layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._refreshing = False
        self._build_ui()

    def _build_ui(self) -> None:
        """
        Creates editable combo boxes for farm, queue, and storage profile.
        Farm is read-only if only one farm exists.
        """
        self.farm_box_label = QLabel(tr("Farm"))
        self.farm_box = DeadlineFarmListComboBox()
        self.farm_box.box.currentIndexChanged.connect(self._on_farm_changed)
        self.farm_box.background_exception.connect(self._handle_background_exception)
        self.farm_box._list_update.connect(self._on_farm_list_updated)
        self.layout.addRow(self.farm_box_label, self.farm_box)

        self.queue_box_label = QLabel(tr("Queue"))
        self.queue_box = DeadlineQueueListComboBox()
        self.queue_box.box.currentIndexChanged.connect(self._on_queue_changed)
        self.queue_box.background_exception.connect(self._handle_background_exception)
        self.queue_box._list_update.connect(self._on_queue_list_updated)
        self.layout.addRow(self.queue_box_label, self.queue_box)

        self.storage_profile_box_label = QLabel(tr("Storage profile"))
        self.storage_profile_box = DeadlineStorageProfileNameListComboBox()
        self.storage_profile_box.box.currentIndexChanged.connect(self._on_storage_profile_changed)
        self.storage_profile_box.background_exception.connect(self._handle_background_exception)
        self.storage_profile_box._list_update.connect(self._on_storage_profile_list_updated)
        self.layout.addRow(self.storage_profile_box_label, self.storage_profile_box)

        # Set initial config
        self._rebuild_override_config()

    def _handle_background_exception(self, title: str, e: BaseException) -> None:
        """Handles background thread exceptions from combo boxes."""
        logger.warning("Background exception in %s: %s", title, e)

    def _on_farm_list_updated(self, refresh_id: int, items_list: list) -> None:
        """
        Called when farm list is loaded. Makes farm read-only if only one farm exists.
        """
        single_farm = len(items_list) == 1
        self.farm_box.box.setEnabled(not single_farm)
        self.farm_box.box.setToolTip("You have access to one farm." if single_farm else "")

    def _on_queue_list_updated(self, refresh_id: int, items_list: list) -> None:
        """
        Called when queue list is loaded. Makes queue read-only if only one queue exists.
        """
        single_queue = len(items_list) == 1
        self.queue_box.box.setEnabled(not single_queue)
        self.queue_box.box.setToolTip("You have access to one queue." if single_queue else "")

    def _on_storage_profile_list_updated(self, refresh_id: int, items_list: list) -> None:
        """
        Called when storage profile list is loaded. Makes read-only with "None" if empty.
        """
        # Check if only item is "<none selected>" with empty ID (meaning no real profiles)
        has_profiles = any(item[1] for item in items_list)  # item[1] is the ID
        if not has_profiles:
            self.storage_profile_box.box.setEnabled(False)
            self.storage_profile_box.box.setToolTip("No storage profiles available.")
            # Replace "<none selected>" with "None"
            if self.storage_profile_box.box.count() > 0:
                self.storage_profile_box.box.setItemText(0, "None")
        else:
            self.storage_profile_box.box.setEnabled(True)
            self.storage_profile_box.box.setToolTip("")

    def _on_farm_changed(self, index: int) -> None:
        """
        Handles farm selection change. Updates sticky only (not global).
        Clears downstream queue and storage profile.
        """
        if self._refreshing:
            return
        new_farm_id = self.farm_box.box.itemData(index) or ""
        if not new_farm_id:
            return

        if self._sticky_mgr:
            self._sticky_mgr.set_value("defaults.farm_id", new_farm_id)
            self._sticky_mgr.clear_downstream("defaults.farm_id")

        self._rebuild_override_config()
        self.queue_box.refresh_list()
        self.storage_profile_box.clear_list()
        self.storage_profile_box.refresh_selected_id()
        self.settings_changed.emit()

    def _maybe_set_global_default(self, setting_name: str, value: str) -> None:
        """
        First-time-sets-default behavior: if the global default is empty,
        write to global config. Once global is non-empty, do nothing.
        """
        if not self._sticky_mgr:
            return
        global_val = self._sticky_mgr.get_global_value(setting_name)
        if not global_val and value:
            config_file.set_setting(setting_name, value)

    def _on_queue_changed(self, index: int) -> None:
        """
        Handles queue selection change with cascade clearing.
        """
        if self._refreshing:
            return
        new_queue_id = self.queue_box.box.itemData(index) or ""
        if not new_queue_id:
            return

        self._maybe_set_global_default("defaults.queue_id", new_queue_id)

        if self._sticky_mgr:
            self._sticky_mgr.set_value("defaults.queue_id", new_queue_id)
            self._sticky_mgr.clear_downstream("defaults.queue_id")

        self._rebuild_override_config()
        self.storage_profile_box.refresh_list()
        self.settings_changed.emit()

    def _on_storage_profile_changed(self, index: int) -> None:
        """
        Handles storage profile selection change.
        """
        if self._refreshing:
            return
        new_sp_id = self.storage_profile_box.box.itemData(index) or ""

        self._maybe_set_global_default("settings.storage_profile_id", new_sp_id)

        if self._sticky_mgr:
            self._sticky_mgr.set_value("settings.storage_profile_id", new_sp_id)

        self._rebuild_override_config()
        self.settings_changed.emit()

    def _rebuild_override_config(self) -> None:
        """
        Rebuilds the ConfigParser with sticky overrides and
        calls set_config() on each combo box.
        """
        self._override_config = self._build_override_config()
        self.farm_box.set_config(self._override_config)
        self.queue_box.set_config(self._override_config)
        self.storage_profile_box.set_config(self._override_config)

    def _build_override_config(self) -> ConfigParser:
        if self._sticky_mgr:
            return self._sticky_mgr.build_override_config()
        return config_file.read_config()

    def get_config(self) -> ConfigParser:
        """Returns the current config with sticky overrides applied."""
        return self._override_config

    def refresh_setting_controls(self, deadline_authorized: bool) -> None:
        """
        Refreshes combo boxes. Reloads sticky settings, builds override config,
        and triggers list refresh if authorized.

        Args:
            deadline_authorized (bool): Should be the result of a call to
                    api.check_deadline_available, for example from
                    an AWS Deadline Cloud Status Widget.
        """
        self._refreshing = True
        try:
            if self._sticky_mgr:
                self._sticky_mgr.reload()
            self._rebuild_override_config()

            if deadline_authorized:
                self.farm_box.refresh_list()
                self.queue_box.refresh_list()
                self.storage_profile_box.refresh_list()
            else:
                self.farm_box.refresh_selected_id()
                self.queue_box.refresh_selected_id()
                self.storage_profile_box.refresh_selected_id()
        finally:
            self._refreshing = False

    def get_farm_id(self) -> str:
        """Returns the currently selected farm ID."""
        return self.farm_box.box.currentData() or ""

    def get_queue_id(self) -> str:
        """Returns the currently selected queue ID."""
        return self.queue_box.box.currentData() or ""

    def get_storage_profile_id(self) -> str:
        """Returns the currently selected storage profile ID."""
        return self.storage_profile_box.box.currentData() or ""
