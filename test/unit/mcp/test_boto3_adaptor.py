"""
Unit tests for deadline.mcp.boto3_adaptor module.

Tests for boto3 API discovery, categorization, and URI pattern inference.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from botocore.model import ServiceModel, OperationModel, StructureShape, Shape


class TestDiscoverApis:
    """Test boto3 API discovery functionality."""

    def test_discover_apis_finds_all_operations(self):
        """Test that discover_apis finds all operations in a boto3 client."""
        # Arrange
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_names = [
            "CreateFarm",
            "ListFarms",
            "GetFarm",
            "UpdateFarm",
            "DeleteFarm",
            "CreateQueue",
            "ListQueues",
            "GetQueue",
            "UpdateQueue",
            "DeleteQueue",
            "CreateJob",
            "ListJobs",
            "GetJob",
            "UpdateJob",
            "CancelJob",
        ]

        expected_operations = [
            "CreateFarm",
            "ListFarms",
            "GetFarm",
            "UpdateFarm",
            "DeleteFarm",
            "CreateQueue",
            "ListQueues",
            "GetQueue",
            "UpdateQueue",
            "DeleteQueue",
            "CreateJob",
            "ListJobs",
            "GetJob",
            "UpdateJob",
            "CancelJob",
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import discover_apis

        result = discover_apis(mock_client)
        assert result == expected_operations

    def test_discover_apis_handles_empty_client(self):
        """Test that discover_apis handles clients with no operations."""
        # Arrange
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_names = []

        # Act & Assert
        from deadline.mcp.boto3_adaptor import discover_apis

        result = discover_apis(mock_client)
        assert result == []

    def test_discover_apis_handles_missing_service_model(self):
        """Test that discover_apis handles clients without service model."""
        # Arrange
        mock_client = Mock()
        del mock_client._service_model

        # Act & Assert
        from deadline.mcp.boto3_adaptor import discover_apis

        result = discover_apis(mock_client)
        assert result == []


class TestCategorizeApi:
    """Test API categorization functionality."""

    def test_categorize_api_identifies_tools(self):
        """Test that categorize_api correctly identifies tool operations."""
        # Arrange
        tool_operations = [
            "CreateFarm",
            "UpdateFarm",
            "DeleteFarm",
            "CreateQueue",
            "UpdateQueue",
            "DeleteQueue",
            "CreateJob",
            "UpdateJob",
            "CancelJob",
            "StartWorker",
            "StopWorker",
            "AssociateFleet",
            "AssumeQueueRoleForUser",  # Deadline Cloud specific
            "AssumeQueueRoleForRead",  # Deadline Cloud specific
            "BatchGetJob",
            "CopyJob",
            "TagResource",
            "UntagResource",
            "MonitorJob",
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import categorize_api

        for operation in tool_operations:
            result = categorize_api(operation)
            assert result == "tool", f"Expected {operation} to be categorized as 'tool'"

    def test_categorize_api_identifies_resources(self):
        """Test that categorize_api correctly identifies resource operations."""
        # Arrange
        resource_operations = [
            "GetFarm",
            "ListFarms",
            "DescribeFarm",
            "GetQueue",
            "ListQueues",
            "DescribeQueue",
            "GetJob",
            "ListJobs",
            "DescribeJob",
            "GetWorker",
            "ListWorkers",
            "DescribeWorker",
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import categorize_api

        for operation in resource_operations:
            result = categorize_api(operation)
            assert result == "resource", f"Expected {operation} to be categorized as 'resource'"

    def test_categorize_api_handles_unknown_patterns(self):
        """Test that categorize_api handles unknown operation patterns."""
        # Arrange
        unknown_operations = ["SomeUnknownOperation", "WeirdApiCall", "CustomFunction"]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import categorize_api

        for operation in unknown_operations:
            result = categorize_api(operation)
            assert result == "tool", f"Expected unknown operation {operation} to default to 'tool'"


class TestInferResourceUriPattern:
    """Test URI pattern inference functionality."""

    def test_infer_resource_uri_pattern_farm_only(self):
        """Test URI pattern inference for farm-only resources."""
        # Arrange
        test_cases = [
            ("GetFarm", "deadline://farm/{farm_id}"),
            ("ListFarms", "deadline://farms"),
            ("DescribeFarm", "deadline://farm/{farm_id}"),
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import infer_resource_uri_pattern

        for operation, expected_pattern in test_cases:
            result = infer_resource_uri_pattern(operation)
            assert result == expected_pattern, (
                f"Expected {operation} to have pattern {expected_pattern}, got {result}"
            )

    def test_infer_resource_uri_pattern_job_hierarchy(self):
        """Test URI pattern inference for hierarchical job resources."""
        # Arrange
        test_cases = [
            ("GetJob", "deadline://farm/{farmId}/queue/{queueId}/job/{jobId}"),
            ("ListJobs", "deadline://farm/{farmId}/queue/{queueId}/jobs"),
            ("DescribeJob", "deadline://farm/{farmId}/queue/{queueId}/job/{jobId}"),
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import infer_resource_uri_pattern

        for operation, expected_pattern in test_cases:
            result = infer_resource_uri_pattern(operation)
            assert result == expected_pattern, (
                f"Expected {operation} to have pattern {expected_pattern}, got {result}"
            )

    def test_infer_resource_uri_pattern_queue_hierarchy(self):
        """Test URI pattern inference for queue resources."""
        # Arrange
        test_cases = [
            ("GetQueue", "deadline://farm/{farmId}/queue/{queueId}"),
            ("ListQueues", "deadline://farm/{farmId}/queues"),
            ("DescribeQueue", "deadline://farm/{farmId}/queue/{queueId}"),
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import infer_resource_uri_pattern

        for operation, expected_pattern in test_cases:
            result = infer_resource_uri_pattern(operation)
            assert result == expected_pattern, (
                f"Expected {operation} to have pattern {expected_pattern}, got {result}"
            )

    def test_infer_resource_uri_pattern_list_operations(self):
        """Test URI pattern inference for list operations."""
        # Arrange
        test_cases = [
            ("ListFarms", "deadline://farms"),
            ("ListFleets", "deadline://farm/{farmId}/fleets"),
            ("ListWorkers", "deadline://farm/{farmId}/fleet/{fleetId}/workers"),
            ("ListSessions", "deadline://farm/{farmId}/queue/{queueId}/sessions"),
        ]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import infer_resource_uri_pattern

        for operation, expected_pattern in test_cases:
            result = infer_resource_uri_pattern(operation)
            assert result == expected_pattern, (
                f"Expected {operation} to have pattern {expected_pattern}, got {result}"
            )

    def test_infer_resource_uri_pattern_handles_unknown_resources(self):
        """Test URI pattern inference for unknown resource types."""
        # Arrange
        unknown_operations = ["GetUnknownResource", "ListWeirdThings", "DescribeMystery"]

        # Act & Assert
        from deadline.mcp.boto3_adaptor import infer_resource_uri_pattern

        for operation in unknown_operations:
            result = infer_resource_uri_pattern(operation)
            # Should return a generic pattern or None
            assert result is not None, f"Expected {operation} to return a pattern, got None"
            assert "deadline://" in result, (
                f"Expected {operation} pattern to include deadline:// scheme"
            )


class TestExtractParameterSchema:
    """Test parameter schema extraction from boto3 operations."""

    def test_extract_parameter_schema_from_operation(self):
        """Test extracting parameter schema from a boto3 operation."""
        # Arrange
        mock_operation_model = Mock(spec=OperationModel)
        mock_operation_model.input_shape = Mock()
        mock_operation_model.input_shape.members = {
            "farmId": Mock(type_name="string", documentation="The farm ID"),
            "displayName": Mock(type_name="string", documentation="Display name"),
            "description": Mock(type_name="string", documentation="Optional description"),
        }

        expected_schema = {
            "type": "object",
            "properties": {
                "farmId": {"type": "string", "description": "The farm ID"},
                "displayName": {"type": "string", "description": "Display name"},
                "description": {"type": "string", "description": "Optional description"},
            },
            "required": ["farmId", "displayName"],
        }

        # Act & Assert
        from deadline.mcp.boto3_adaptor import extract_parameter_schema

        result = extract_parameter_schema(mock_operation_model)
        assert result["type"] == expected_schema["type"]
        assert "properties" in result
        assert "farmId" in result["properties"]
        assert "displayName" in result["properties"]

    def test_extract_parameter_schema_handles_no_input(self):
        """Test extracting schema when operation has no input parameters."""
        # Arrange
        mock_operation_model = Mock(spec=OperationModel)
        mock_operation_model.input_shape = None

        # Act & Assert
        from deadline.mcp.boto3_adaptor import extract_parameter_schema

        result = extract_parameter_schema(mock_operation_model)
        assert result == {"type": "object", "properties": {}}

    def test_extract_parameter_schema_handles_complex_types(self):
        """Test extracting schema with nested objects and arrays."""
        # Arrange
        mock_operation_model = Mock(spec=OperationModel)
        mock_operation_model.input_shape = Mock()

        # Mock nested structure
        mock_nested_shape = Mock()
        mock_nested_shape.type_name = "structure"
        mock_nested_shape.members = {
            "key": Mock(type_name="string"),
            "value": Mock(type_name="string"),
        }

        mock_operation_model.input_shape.members = {
            "farmId": Mock(type_name="string"),
            "tags": Mock(type_name="list", member=Mock(type_name="structure")),
            "configuration": mock_nested_shape,
        }

        # Act & Assert
        from deadline.mcp.boto3_adaptor import extract_parameter_schema

        result = extract_parameter_schema(mock_operation_model)
        assert result["type"] == "object"
        assert "properties" in result
        assert "farmId" in result["properties"]
        assert "tags" in result["properties"]
        assert "configuration" in result["properties"]


if __name__ == "__main__":
    pytest.main([__file__])
