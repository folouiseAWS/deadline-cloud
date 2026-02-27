# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# -*- coding: utf-8 -*
# mypy: disable-error-code="attr-defined"

import gui_submitter_locators
import squish
import test
import time


def _wait_for_combo_loaded(locator, timeout=10):
    """Wait for a combo box inside a resource list widget to finish loading."""
    combo = squish.waitForObject({"container": locator, "type": "QComboBox", "visible": 1})
    deadline = time.time() + timeout
    while time.time() < deadline:
        if str(combo.currentText) != "<refreshing>":
            return combo
        squish.snooze(0.5)
    return combo


def navigate_shared_job_settings():
    # click on Shared job settings tab
    test.log("Navigate to Shared job settings tab.")
    squish.clickTab(
        squish.waitForObject(gui_submitter_locators.shared_jobsettings_tab), "Shared job settings"
    )
    # verify on shared job settings tab
    test.compare(
        squish.waitForObjectExists(
            gui_submitter_locators.shared_jobsettings_properties_box
        ).visible,
        True,
        "Expect user to be on Shared job settings tab.",
    )


def navigate_job_specific_settings():
    # click on Job-specific settings tab
    test.log("Navigate to Job-specific settings tab.")
    squish.clickTab(
        squish.waitForObject(gui_submitter_locators.job_specificsettings_tab),
        "Job-specific settings",
    )
    # verify on job specific settings tab
    test.compare(
        squish.waitForObjectExists(gui_submitter_locators.job_specificsettings_properties).visible,
        True,
        "Expect user to be on Job-specific settings tab.",
    )


def verify_shared_job_settings(
    job_name: str,
    farm_name: str = "",
    queue_name: str = "",
    storage_profile: str = "",
):
    # click on shared job settings tab to navigate and ensure tests are on correct tab
    navigate_shared_job_settings()
    # verify job name is set correctly
    test.compare(
        str(
            squish.waitForObjectExists(gui_submitter_locators.job_properties_name_input).displayText
        ),
        job_name,
        "Expect correct job bundle job name to be displayed by default.",
    )
    # verify farm, queue and storage profile combo box values if provided
    if farm_name:
        verify_submitter_farm(farm_name)
    if queue_name:
        verify_submitter_queue(queue_name)
    if storage_profile:
        verify_submitter_storage_profile(storage_profile)


def set_submitter_queue(queue_name: str):
    """Select a queue by name in the queue combo box."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_queue_name)
    for i in range(combo.count):
        if str(combo.itemText(i)) == queue_name:
            combo.setCurrentIndex(i)
            return
    test.fail(f"Queue '{queue_name}' not found in combo box.")


def set_submitter_storage_profile(storage_profile: str):
    """Select a storage profile by name in the storage profile combo box."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_storage_profile)
    for i in range(combo.count):
        if str(combo.itemText(i)) == storage_profile:
            combo.setCurrentIndex(i)
            return
    test.fail(f"Storage profile '{storage_profile}' not found in combo box.")


def verify_submitter_queue(queue_name: str):
    """Verify the queue combo box shows the expected queue name."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_queue_name)
    test.compare(
        str(combo.currentText),
        queue_name,
        f"Expect queue combo box to show '{queue_name}'.",
    )


def verify_submitter_storage_profile(storage_profile: str):
    """Verify the storage profile combo box shows the expected value."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_storage_profile)
    test.compare(
        str(combo.currentText),
        storage_profile,
        f"Expect storage profile combo box to show '{storage_profile}'.",
    )


def set_submitter_farm(farm_name: str):
    """Select a farm by name in the farm combo box."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_farm)
    if not combo.enabled:
        test.log(f"Farm combo is disabled (single farm), skipping selection of '{farm_name}'.")
        return
    for i in range(combo.count):
        if str(combo.itemText(i)) == farm_name:
            combo.setCurrentIndex(i)
            return
    test.fail(f"Farm '{farm_name}' not found in combo box.")


def verify_submitter_farm(farm_name: str):
    """Verify the farm combo box shows the expected farm name."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_farm)
    test.compare(
        str(combo.currentText),
        farm_name,
        f"Expect farm combo box to show '{farm_name}'.",
    )


def verify_farm_readonly_with_tooltip():
    """Verify farm combo is disabled with correct tooltip when only one farm."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_farm)
    test.compare(combo.enabled, False, "Expect farm combo to be disabled with single farm.")
    test.compare(
        str(combo.toolTip),
        "You have access to one farm.",
        "Expect farm tooltip for single farm.",
    )


def verify_storage_profile_none_with_tooltip():
    """Verify storage profile shows 'None' and is disabled when no profiles available."""
    combo = _wait_for_combo_loaded(gui_submitter_locators.deadline_cloud_settings_storage_profile)
    test.compare(combo.enabled, False, "Expect storage profile combo to be disabled.")
    test.compare(str(combo.currentText), "None", "Expect storage profile to show 'None'.")
    test.compare(
        str(combo.toolTip),
        "No storage profiles available.",
        "Expect storage profile tooltip when none available.",
    )
