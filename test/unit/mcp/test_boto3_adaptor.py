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


class TestResourceURIMapper:
    """Test ResourceURIMapper functionality with no-fallback policy."""

    def test_get_uri_pattern_without_schema_raises_error(self):
        """Test that get_uri_pattern raises error without schema (no fallbacks allowed)."""
        from deadline.mcp.boto3_adaptor import ResourceURIMapper

        with pytest.raises(ValueError, match="requires schema"):
            ResourceURIMapper.get_uri_pattern("GetFarm")

    def test_parse_uri_not_implemented(self):
        """Test that parse_uri raises NotImplementedError (no fallbacks allowed)."""
        from deadline.mcp.boto3_adaptor import ResourceURIMapper

        with pytest.raises(NotImplementedError, match="URI parsing not implemented"):
            ResourceURIMapper.parse_uri("deadline://farm/test-farm")

    def test_proper_schema_based_pattern_generation(self):
        """Test that proper schema-based pattern generation works."""
        from deadline.mcp.boto3_adaptor import ResourceURIMapper

        schema = {"properties": {"farmId": {"type": "string"}}, "required": ["farmId"]}
        pattern = ResourceURIMapper.get_uri_pattern_with_schema("GetFarm", schema)
        assert pattern.startswith("deadline://")
        assert "{farm_id}" in pattern

    def test_schema_based_pattern_generation_list_operations(self):
        """Test schema-based pattern generation for list operations."""
        from deadline.mcp.boto3_adaptor import ResourceURIMapper

        schema = {"properties": {"farmId": {"type": "string"}}, "required": ["farmId"]}
        pattern = ResourceURIMapper.get_uri_pattern_with_schema("ListQueues", schema)
        assert pattern.startswith("deadline://")
        assert "farm/{farm_id}" in pattern
        assert "queues" in pattern

    def test_schema_based_pattern_generation_complex_hierarchy(self):
        """Test schema-based pattern generation for complex hierarchies."""
        from deadline.mcp.boto3_adaptor import ResourceURIMapper

        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "jobId": {"type": "string"},
            },
            "required": ["farmId", "queueId", "jobId"],
        }
        pattern = ResourceURIMapper.get_uri_pattern_with_schema("GetJob", schema)
        assert pattern.startswith("deadline://")
        assert "farm/{farm_id}" in pattern
        assert "queue/{queue_id}" in pattern
        assert "job/{job_id}" in pattern


class TestDynamicParameterExtractor:
    """Test parameter schema extraction using DynamicParameterExtractor."""

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
        mock_operation_model.input_shape.required_members = ["farmId", "displayName"]

        # Create mock client that returns our mock operation model
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_model.return_value = mock_operation_model

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
        from deadline.mcp.parameter_extractor import DynamicParameterExtractor

        extractor = DynamicParameterExtractor()
        result = extractor.extract_parameter_schema(mock_client, "TestOperation")
        assert result["type"] == expected_schema["type"]
        assert "properties" in result
        assert "farmId" in result["properties"]
        assert "displayName" in result["properties"]

    def test_extract_parameter_schema_handles_no_input(self):
        """Test extracting schema when operation has no input parameters."""
        # Arrange
        mock_operation_model = Mock(spec=OperationModel)
        mock_operation_model.input_shape = None

        # Create mock client that returns our mock operation model
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_model.return_value = mock_operation_model

        # Act & Assert
        from deadline.mcp.parameter_extractor import DynamicParameterExtractor

        extractor = DynamicParameterExtractor()
        result = extractor.extract_parameter_schema(mock_client, "TestOperation")
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
        mock_operation_model.input_shape.required_members = []

        # Create mock client that returns our mock operation model
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_model.return_value = mock_operation_model

        # Act & Assert
        from deadline.mcp.parameter_extractor import DynamicParameterExtractor

        extractor = DynamicParameterExtractor()
        result = extractor.extract_parameter_schema(mock_client, "TestOperation")
        assert result["type"] == "object"
        assert "properties" in result
        assert "farmId" in result["properties"]
        assert "tags" in result["properties"]
        assert "configuration" in result["properties"]


if __name__ == "__main__":
    pytest.main([__file__])
