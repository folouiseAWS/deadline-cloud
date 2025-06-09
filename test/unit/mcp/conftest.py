"""Test fixtures for MCP server tests."""

import pytest
from unittest.mock import Mock, patch
import boto3


@pytest.fixture
def real_deadline_service_model():
    """Real boto3 deadline service model."""
    client = boto3.client("deadline", region_name="us-east-1")
    return client._service_model


@pytest.fixture
def real_list_farms_operation(real_deadline_service_model):
    """Real ListFarms operation model from boto3."""
    return real_deadline_service_model.operation_model("ListFarms")


@pytest.fixture
def real_create_farm_operation(real_deadline_service_model):
    """Real CreateFarm operation model from boto3."""
    return real_deadline_service_model.operation_model("CreateFarm")


@pytest.fixture
def real_get_farm_operation(real_deadline_service_model):
    """Real GetFarm operation model from boto3."""
    return real_deadline_service_model.operation_model("GetFarm")


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 deadline client for network call isolation."""
    with patch("boto3.client") as mock_client_constructor:
        mock_client = Mock()
        mock_client_constructor.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_deadline_client_methods():
    """Mock deadline client with typical methods."""
    methods = [
        "list_farms",
        "create_farm",
        "get_farm",
        "delete_farm",
        "list_queues",
        "create_queue",
        "get_queue",
        "delete_queue",
        "list_jobs",
        "create_job",
        "get_job",
        "update_job",
    ]
    return methods
