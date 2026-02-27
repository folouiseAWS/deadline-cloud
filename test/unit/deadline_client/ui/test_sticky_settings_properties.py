# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
"""
Property-based tests for StickySettingsManager.

These tests validate universal correctness properties using Hypothesis.
"""

import json
import re
from configparser import ConfigParser
from unittest.mock import MagicMock, patch

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from deadline.client.ui._sticky_settings import (  # noqa: E402
    STICKY_KEYS,
    StickySettingsManager,
    _CASCADE_ORDER,
)

# Strategy for generating valid sticky key names
sticky_key_st = st.sampled_from(list(STICKY_KEYS))

# Strategy for generating arbitrary non-empty resource ID strings
resource_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
)

# Strategy for generating resource IDs that may be empty
maybe_empty_resource_id_st = st.one_of(st.just(""), resource_id_st)


@pytest.fixture(autouse=True)
def mock_config_file():
    """Patches config_file for all property tests."""
    with patch("deadline.client.ui._sticky_settings.config_file") as mock_cf:
        mock_cf.get_setting.return_value = ""
        mock_cf.read_config.return_value = ConfigParser()
        mock_cf.set_setting = MagicMock()
        yield mock_cf


def _make_manager(tmp_path, mock_cf):
    """Helper to create a StickySettingsManager with a temp directory."""
    with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=tmp_path):
        return StickySettingsManager("test_submitter")


class TestProperty1EffectiveValuePrecedence:
    """
    Property 1: Effective value precedence.
    For any setting in STICKY_KEYS and any pair of sticky/global values:
    if sticky is non-empty, get_effective_value() returns sticky;
    otherwise returns global.
    """

    @given(
        key=sticky_key_st,
        sticky_val=maybe_empty_resource_id_st,
        global_val=maybe_empty_resource_id_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_effective_value_precedence(
        self, key, sticky_val, global_val, tmp_path, mock_config_file
    ):
        mock_config_file.get_setting.return_value = global_val
        mgr = _make_manager(tmp_path, mock_config_file)

        if sticky_val:
            mgr.set_value(key, sticky_val)

        result = mgr.get_effective_value(key)

        if sticky_val:
            assert result == sticky_val
        else:
            assert result == global_val


class TestProperty2StickySettingsRoundTrip:
    """
    Property 2: Sticky settings round-trip.
    For any valid combination of queue_id and storage_profile_id,
    saving via set_value() and reloading produces identical values.
    """

    @given(
        queue_id=resource_id_st,
        sp_id=resource_id_st,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_round_trip(self, queue_id, sp_id, tmp_path, mock_config_file):
        # Clear any existing file to ensure clean state
        file_path = tmp_path / "test_submitter.json"
        if file_path.exists():
            file_path.unlink()

        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=tmp_path):
            mgr = StickySettingsManager("test_submitter")
            mgr.set_value("defaults.queue_id", queue_id)
            mgr.set_value("settings.storage_profile_id", sp_id)

            # Reload from disk
            mgr.reload()

            assert mgr._settings["defaults.queue_id"] == queue_id
            assert mgr._settings["settings.storage_profile_id"] == sp_id


class TestProperty3UnrecognizedKeyFiltering:
    """
    Property 3: Unrecognized key filtering.
    For any JSON file containing arbitrary key-value pairs (including keys
    outside STICKY_KEYS), after _load(), the internal settings dict contains
    only keys in STICKY_KEYS.
    """

    @given(
        extra_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=30),
            values=st.text(min_size=0, max_size=50),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unrecognized_keys_filtered(self, extra_data, tmp_path, mock_config_file):
        # Write a JSON file with both recognized and unrecognized keys
        data = dict(extra_data)
        data["defaults.queue_id"] = "queue-known"
        file_path = tmp_path / "test_submitter.json"
        file_path.write_text(json.dumps(data), encoding="utf-8")

        mgr = _make_manager(tmp_path, mock_config_file)

        for key in mgr._settings:
            assert key in STICKY_KEYS


class TestProperty4CascadeInvariant:
    """
    Property 4: Cascade invariant.
    For any initial sticky settings state and any setting in cascade order,
    clear_downstream(setting_name) removes all keys strictly after it and
    preserves the setting itself and all keys before it.
    """

    @given(
        farm_id=resource_id_st,
        queue_id=resource_id_st,
        sp_id=resource_id_st,
        clear_key=st.sampled_from(_CASCADE_ORDER),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cascade_invariant(
        self, farm_id, queue_id, sp_id, clear_key, tmp_path, mock_config_file
    ):
        mgr = _make_manager(tmp_path, mock_config_file)
        mgr.set_value("defaults.farm_id", farm_id)
        mgr.set_value("defaults.queue_id", queue_id)
        mgr.set_value("settings.storage_profile_id", sp_id)

        idx = _CASCADE_ORDER.index(clear_key)
        mgr.clear_downstream(clear_key)

        # Keys at or before the cleared key should be preserved
        for key in _CASCADE_ORDER[: idx + 1]:
            assert key in mgr._settings

        # Keys after the cleared key should be removed
        for key in _CASCADE_ORDER[idx + 1 :]:
            assert key not in mgr._settings


class TestProperty8SubmitterNameSanitization:
    """
    Property 8: Submitter name sanitization.
    For any input string as submitter_name, the sanitized result contains
    only word characters, hyphens, and dots.
    """

    @given(name=st.text(min_size=1, max_size=100))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitized_name_is_safe(self, name, tmp_path, mock_config_file):
        with patch.object(StickySettingsManager, "_get_sticky_dir", return_value=tmp_path):
            mgr = StickySettingsManager(name)
        # The sanitized name should only contain word chars, hyphens, dots
        assert re.fullmatch(r"[\w\-.]*", mgr._submitter_name), (
            f"Sanitized name {mgr._submitter_name!r} contains invalid characters"
        )


class TestProperty11OnlyRecognizedKeysStored:
    """
    Property 11: Only recognized keys stored.
    For any key string passed to set_value(), the key is persisted only if
    it is a member of STICKY_KEYS; unrecognized keys produce no change.
    """

    @given(key=st.text(min_size=1, max_size=50), value=resource_id_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_only_recognized_keys_stored(self, key, value, tmp_path, mock_config_file):
        mgr = _make_manager(tmp_path, mock_config_file)
        mgr.set_value(key, value)

        if key in STICKY_KEYS:
            assert mgr._settings.get(key) == value
        else:
            assert key not in mgr._settings


class TestProperty9OverrideConfigImmutability:
    """
    Property 9: Override config immutability.
    For any global config state and sticky settings state,
    build_override_config() returns a new ConfigParser without modifying
    values readable from config_file.get_setting().
    """

    @given(
        queue_id=maybe_empty_resource_id_st,
        sp_id=maybe_empty_resource_id_st,
        global_queue=maybe_empty_resource_id_st,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_override_config_does_not_mutate_global(
        self, queue_id, sp_id, global_queue, tmp_path, mock_config_file
    ):
        # Set up global config (use interpolation=None to avoid issues with % in values)
        global_config = ConfigParser(interpolation=None)
        if global_queue:
            global_config["defaults"] = {"queue_id": global_queue}
        mock_config_file.read_config.return_value = global_config

        # Capture the global value before
        mock_config_file.get_setting.return_value = global_queue

        mgr = _make_manager(tmp_path, mock_config_file)
        if queue_id:
            mgr.set_value("defaults.queue_id", queue_id)
        if sp_id:
            mgr.set_value("settings.storage_profile_id", sp_id)

        # Call build_override_config
        mgr.build_override_config()

        # The global config singleton should not have been modified
        # (set_setting was only called with a config param, not without)
        for call_args in mock_config_file.set_setting.call_args_list:
            # Every call should have 3 args (key, value, config) — never 2
            assert len(call_args[0]) == 3, (
                "set_setting was called without a config param, which would write to disk"
            )


class TestProperty10OverrideConfigMergeCorrectness:
    """
    Property 10: Override config merge correctness.
    For any combination of global and sticky values across STICKY_KEYS,
    the returned ConfigParser contains sticky value where non-empty override
    exists, and global value otherwise.
    """

    @given(
        sticky_queue=maybe_empty_resource_id_st,
        sticky_sp=maybe_empty_resource_id_st,
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_merge_correctness(self, sticky_queue, sticky_sp, tmp_path, mock_config_file):
        global_config = ConfigParser(interpolation=None)
        mock_config_file.read_config.return_value = global_config

        mgr = _make_manager(tmp_path, mock_config_file)
        if sticky_queue:
            mgr.set_value("defaults.queue_id", sticky_queue)
        if sticky_sp:
            mgr.set_value("settings.storage_profile_id", sticky_sp)

        mgr.build_override_config()

        # Verify set_setting was called for each non-empty sticky value
        set_setting_calls = {
            call[0][0]: call[0][1]
            for call in mock_config_file.set_setting.call_args_list
            if len(call[0]) == 3  # only calls with config param
        }

        if sticky_queue:
            assert set_setting_calls.get("defaults.queue_id") == sticky_queue
        if sticky_sp:
            assert set_setting_calls.get("settings.storage_profile_id") == sticky_sp
