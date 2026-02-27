# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# -*- coding: utf-8 -*-
# mypy: disable-error-code="attr-defined"
"""
Tests for sticky settings behavior in the Job Settings dialog.

Sticky settings allow each DCC submitter to remember its own farm, queue,
and storage profile selections independently of the global defaults.
"""

import os
import shutil

import config
import choose_jobbundledir_helpers
import gui_submitter_helpers
import gui_submitter_locators
import workstation_config_helpers
import loginout_helpers
import squish
import test


def init():
    # Clear sticky settings to start fresh
    sticky_dir = os.path.expanduser("~/.deadline/sticky_settings")
    if os.path.exists(sticky_dir):
        shutil.rmtree(sticky_dir)
        test.log(f"Cleared sticky settings directory: {sticky_dir}")

    # Clear global defaults (farm, queue, storage profile) from config
    config_path = os.path.expanduser("~/.deadline/config")
    if os.path.exists(config_path):
        import configparser

        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        changed = False
        for section, key in [
            ("defaults", "farm_id"),
            ("defaults", "queue_id"),
            ("settings", "storage_profile_id"),
        ]:
            if cfg.has_option(section, key):
                cfg.remove_option(section, key)
                changed = True
        if changed:
            with open(config_path, "w") as f:
                cfg.write(f)
            test.log("Cleared global defaults from config file.")

    # Launch Settings dialog to set initial farm
    workstation_config_helpers.detect_platform_and_launch_deadline_config()
    loginout_helpers.set_aws_profile_name_and_verify_auth(config.profile_name)
    workstation_config_helpers.set_farm_name(config.farm_name)
    workstation_config_helpers.close_deadline_config_gui()


def main():
    # Test 1: Set global defaults in Settings dialog and verify they persist
    test.log("Test 1: Set global defaults in Settings and verify persistence.")
    workstation_config_helpers.detect_platform_and_launch_deadline_config()
    workstation_config_helpers.set_farm_name(config.farm_name)
    workstation_config_helpers.set_queue_name(config.queue_name)
    workstation_config_helpers.close_deadline_config_gui()

    # Reopen Settings and verify global defaults persisted
    workstation_config_helpers.detect_platform_and_launch_deadline_config()
    squish.snooze(2)  # Wait for lists to load
    workstation_config_helpers.verify_farm_name(config.farm_name)
    workstation_config_helpers.verify_queue_name(config.queue_name)
    test.log("Global defaults persisted in Settings dialog.")
    workstation_config_helpers.close_deadline_config_gui()

    # Test 2: Verify farm combo box is visible in Job Settings
    test.log("Test 2: Verify farm combo box is present in Job Settings dialog.")
    choose_jobbundledir_helpers.detect_platform_and_launch_jobbundle_guisubmitter()
    choose_jobbundledir_helpers.select_jobbundle(config.simple_ui_with_ja)

    test.compare(
        squish.waitForObjectExists(gui_submitter_locators.deadline_cloud_settings_farm).visible,
        True,
        "Expect farm combo box to be visible in Job Settings.",
    )
    gui_submitter_helpers.verify_submitter_farm(config.farm_name)

    # Test 3: Set sticky queue and storage profile
    test.log("Test 3: Set sticky queue and storage profile.")
    gui_submitter_helpers.set_submitter_queue(config.queue_name)
    gui_submitter_helpers.verify_submitter_queue(config.queue_name)
    gui_submitter_helpers.set_submitter_storage_profile(config.storage_profile_macos)
    gui_submitter_helpers.verify_submitter_storage_profile(config.storage_profile_macos)

    # Test 4: Verify sticky settings persist after dialog reopen
    test.log("Test 4: Verify sticky settings persist after dialog reopen.")
    squish.sendEvent(
        "QCloseEvent", squish.waitForObject(gui_submitter_locators.aws_submitter_dialogue)
    )

    # Reopen submitter
    choose_jobbundledir_helpers.detect_platform_and_launch_jobbundle_guisubmitter()
    choose_jobbundledir_helpers.select_jobbundle(config.simple_ui_with_ja)
    squish.snooze(2)  # Wait for lists to load

    # Verify sticky values persisted
    gui_submitter_helpers.verify_submitter_farm(config.farm_name)
    gui_submitter_helpers.verify_submitter_queue(config.queue_name)
    gui_submitter_helpers.verify_submitter_storage_profile(config.storage_profile_macos)
    test.log("Sticky settings persisted correctly after dialog reopen.")

    # Test 5: Verify global settings are independent of sticky settings
    test.log("Test 5: Verify global settings are independent of sticky settings.")
    squish.sendEvent(
        "QCloseEvent", squish.waitForObject(gui_submitter_locators.aws_submitter_dialogue)
    )

    # Reopen Settings and verify global defaults still correct
    workstation_config_helpers.detect_platform_and_launch_deadline_config()
    squish.snooze(2)  # Wait for lists to load
    workstation_config_helpers.verify_farm_name(config.farm_name)
    workstation_config_helpers.verify_queue_name(config.queue_name)
    test.log("Global defaults unchanged after sticky settings were set.")
    workstation_config_helpers.close_deadline_config_gui()

    # Reopen submitter and verify sticky still correct
    choose_jobbundledir_helpers.detect_platform_and_launch_jobbundle_guisubmitter()
    choose_jobbundledir_helpers.select_jobbundle(config.simple_ui_with_ja)
    squish.snooze(2)  # Wait for lists to load
    gui_submitter_helpers.verify_submitter_queue(config.queue_name)
    test.log("Sticky settings unchanged after reopening Settings dialog.")


def cleanup():
    test.log("Closing AWS Submitter dialogue.")
    squish.sendEvent(
        "QCloseEvent", squish.waitForObject(gui_submitter_locators.aws_submitter_dialogue)
    )
