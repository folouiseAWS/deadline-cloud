# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# -*- coding: utf-8 -*-
# mypy: disable-error-code="attr-defined"

import config
import choose_jobbundledir_helpers
import choose_jobbundledir_locators
import gui_submitter_helpers
import gui_submitter_locators
import workstation_config_helpers
import workstation_config_locators
import loginout_helpers
import squish
import test


def init():
    # First, launch Settings dialog to set the farm (farm is only in Settings now)
    workstation_config_helpers.detect_platform_and_launch_deadline_config()
    # set aws profile
    loginout_helpers.set_aws_profile_name_and_verify_auth(config.profile_name)
    # set farm name in Settings dialog
    workstation_config_helpers.set_farm_name(config.farm_name)
    # verify correct farm name is set
    test.compare(
        str(
            squish.waitForObjectExists(
                workstation_config_locators.profilesettings_defaultfarm_dropdown
            ).currentText
        ),
        config.farm_name,
        "Expect selected farm name to be set.",
    )
    # close Settings dialog
    workstation_config_helpers.close_deadline_config_gui()

    # Now launch Choose Job Bundle GUI Submitter
    choose_jobbundledir_helpers.detect_platform_and_launch_jobbundle_guisubmitter()
    # verify Choose job bundle directory is open
    test.compare(
        str(
            squish.waitForObjectExists(
                choose_jobbundledir_locators.choose_job_bundle_dir
            ).windowTitle
        ),
        "Choose job bundle directory",
        "Expect Choose job bundle directory window title to be present.",
    )
    test.compare(
        squish.waitForObjectExists(choose_jobbundledir_locators.choose_job_bundle_dir).visible,
        True,
        "Expect Choose job bundle directory to be open.",
    )


def main():
    # select Simple UI with Job Attachments (simple_ui_with_ja) job bundle
    choose_jobbundledir_helpers.select_jobbundle(config.simple_ui_with_ja)
    # verify GUI Submitter dialogue opens
    test.compare(
        str(squish.waitForObjectExists(gui_submitter_locators.aws_submitter_dialogue).windowTitle),
        "Deadline Cloud JobBundle Submitter",
        "Expect AWS Deadline Cloud Submitter window title to be present.",
    )
    test.compare(
        squish.waitForObjectExists(gui_submitter_locators.aws_submitter_dialogue).visible,
        True,
        "Expect AWS Deadline Cloud Submitter to be open.",
    )

    # verify combo boxes are present for queue and storage profile
    # (farm is now only in Settings dialog)
    test.log("Verify queue and storage profile combo boxes are present.")
    test.compare(
        squish.waitForObjectExists(
            gui_submitter_locators.deadline_cloud_settings_queue_name
        ).visible,
        True,
        "Expect queue combo box to be visible.",
    )
    test.compare(
        squish.waitForObjectExists(
            gui_submitter_locators.deadline_cloud_settings_storage_profile
        ).visible,
        True,
        "Expect storage profile combo box to be visible.",
    )

    # verify shared job settings tab for simple_ui_with_ja
    test.log(
        "Start verifying Shared Job Settings tab for Simple UI with Job Attachments (simple_ui_with_ja) job bundle"
    )
    gui_submitter_helpers.verify_shared_job_settings(
        config.simple_ui_with_ja_name,
        queue_name=config.queue_name,
    )

    # verify queue change refreshes storage profile
    test.log("Verify queue change triggers storage profile list refresh.")
    gui_submitter_helpers.set_submitter_queue(config.queue_name)
    gui_submitter_helpers.verify_submitter_queue(config.queue_name)

    # verify storage profile selection
    test.log("Verify storage profile can be selected.")
    gui_submitter_helpers.set_submitter_storage_profile(config.storage_profile_macos)
    gui_submitter_helpers.verify_submitter_storage_profile(config.storage_profile_macos)

    # verify load different job bundle flow
    test.log("Navigate to Job-Specific Settings tab and verify Load a different job bundle flow")
    choose_jobbundledir_helpers.load_different_job_bundle()
    # select Simple UI - No Job Attachments (simple_ui_no_ja) job bundle
    choose_jobbundledir_helpers.select_jobbundle(config.simple_ui_no_ja)
    # verify shared job settings tab for simple_ui_no_ja
    test.log(
        "Start verifying Shared Job Settings tab for Simple UI - No Job Attachments (simple_ui_no_ja) job bundle"
    )
    gui_submitter_helpers.verify_shared_job_settings(
        config.simple_ui_no_ja_name,
        queue_name=config.queue_name,
        storage_profile=config.storage_profile_macos,
    )


def cleanup():
    test.log("Closing AWS Submitter dialogue by sending QCloseEvent to 'x' button.")
    squish.sendEvent(
        "QCloseEvent", squish.waitForObject(gui_submitter_locators.aws_submitter_dialogue)
    )
