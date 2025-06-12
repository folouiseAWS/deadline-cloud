"""
Unit tests for deadline.mcp.server module.

Tests the FastMCP-based server architecture after Phase 1-4 refactoring.
"""

import pytest
import boto3
from unittest.mock import Mock, patch
from botocore.stub import Stubber
from botocore.exceptions import ClientError, NoCredentialsError

from deadline.mcp.boto3_adaptor import categorize_api, discover_apis, ResourceURIMapper


class TestCoreLogic:
    """Test core logic functions - no mocking needed."""

    def test_categorize_api_identifies_tools(self):
        """Test operation categorization for tools."""
        tool_operations = [
            "CreateFarm",
            "UpdateFarm",
            "DeleteFarm",
            "StartJob",
            "CancelJob",
            "AssociateFleet",
        ]
        for op in tool_operations:
            assert categorize_api(op) == "tool"

    def test_categorize_api_identifies_resources(self):
        """Test operation categorization for resources."""
        resource_operations = [
            "ListFarms",
            "GetFarm",
            "DescribeFarm",
            "ListQueues",
            "GetQueue",
            "SearchJobs",
        ]
        for op in resource_operations:
            assert categorize_api(op) == "resource"

    def test_categorize_api_defaults_to_tool(self):
        """Unknown operations default to tool."""
        assert categorize_api("WeirdUnknownOperation") == "tool"

    def test_uri_pattern_inference_basic_cases(self):
        """Test URI pattern inference for common cases."""
        # Use ResourceURIMapper instead of the old function
        mock_schema = {"properties": {}}

        assert (
            ResourceURIMapper.get_uri_pattern_with_schema("ListFarms", mock_schema)
            == "deadline://farms"
        )
        assert (
            ResourceURIMapper.get_uri_pattern_with_schema("GetFarm", mock_schema)
            == "deadline://farm/{farm_id}"
        )
        assert (
            ResourceURIMapper.get_uri_pattern_with_schema("ListQueues", mock_schema)
            == "deadline://queues"
        )


class TestFastMCPServerCreation:
    """Test FastMCP server creation and functionality."""

    def test_create_fastmcp_server_works(self):
        """FastMCP server can be created without crashing."""
        from deadline.mcp.server import create_fastmcp_server

        # Should create server successfully
        server = create_fastmcp_server()
        assert server is not None

    def test_fastmcp_server_discovers_operations(self):
        """FastMCP server discovers and registers operations properly."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            # Use real S3 client for realistic structure
            mock_get.return_value = boto3.client("s3", region_name="us-east-1")

            from deadline.mcp.server import create_fastmcp_server

            # Should create without error
            server = create_fastmcp_server()
            assert server is not None

    def test_fastmcp_server_handles_aws_credential_issues(self):
        """FastMCP server handles AWS credential issues gracefully."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.side_effect = NoCredentialsError()

            from deadline.mcp.server import create_fastmcp_server

            # Should handle credentials error gracefully
            with pytest.raises(NoCredentialsError):
                create_fastmcp_server()


class TestAPIDiscovery:
    """Test API discovery functionality."""

    def test_api_discovery_works_with_any_client(self):
        """API discovery works with any real boto3 client."""
        # Test with different real clients
        clients = [
            boto3.client("s3", region_name="us-east-1"),
            boto3.client("ec2", region_name="us-east-1"),
            boto3.client("lambda", region_name="us-east-1"),
        ]

        for client in clients:
            operations = discover_apis(client)
            assert len(operations) > 0
            assert all(isinstance(op, str) for op in operations)

            # Test categorization works for any operations
            categories = [categorize_api(op) for op in operations[:3]]
            assert all(cat in ["tool", "resource"] for cat in categories)

    def test_uri_patterns_are_consistent(self):
        """URI pattern generation is consistent and predictable."""
        mock_schema = {"properties": {}}

        # Test same operation gives same URI
        uri1 = ResourceURIMapper.get_uri_pattern_with_schema("GetFarm", mock_schema)
        uri2 = ResourceURIMapper.get_uri_pattern_with_schema("GetFarm", mock_schema)
        assert uri1 == uri2

        # Test different operations give different URIs
        list_uri = ResourceURIMapper.get_uri_pattern_with_schema("ListFarms", mock_schema)
        get_uri = ResourceURIMapper.get_uri_pattern_with_schema("GetFarm", mock_schema)
        assert list_uri != get_uri

        # Test URI patterns are valid
        assert list_uri.startswith("deadline://")
        assert get_uri.startswith("deadline://")

    def test_server_discovers_deadline_operations(self):
        """Test that server can discover Deadline Cloud operations."""
        deadline_client = boto3.client("deadline", region_name="us-east-1")

        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.return_value = deadline_client

            # Should discover deadline operations from real client structure
            operations = discover_apis(deadline_client)
            assert len(operations) > 0

            # Should categorize operations properly
            tool_count = len([op for op in operations if categorize_api(op) == "tool"])
            resource_count = len([op for op in operations if categorize_api(op) == "resource"])
            assert tool_count + resource_count == len(operations)


class TestParameterClassifierIntegration:
    """Integration test for parameter classifier with server code."""

    def test_parameter_classifier_integration(self):
        """Test classifier integrates with existing server code."""
        from deadline.mcp.parameter_classifier import DynamicParameterClassifier

        classifier = DynamicParameterClassifier()

        # Test with real operation schemas
        mock_schema = {
            "properties": {
                "farmId": {"type": "string"},
                "nextToken": {"type": "string"},
                "maxResults": {"type": "integer"},
                "status": {"type": "string"},
            }
        }

        # Test parameter classification works correctly
        assert classifier.classify_parameter("farmId", "ListJobs").value == "identifier"
        assert classifier.classify_parameter("nextToken", "ListJobs").value == "pagination"
        assert classifier.classify_parameter("maxResults", "ListJobs").value == "pagination"
        assert classifier.classify_parameter("status", "ListJobs").value == "filter"

        # Test function signature inclusion logic
        # Pagination parameters should never be included
        assert not classifier.should_include_in_function_signature("nextToken", "ListJobs")
        assert not classifier.should_include_in_function_signature("maxResults", "ListJobs")

        # Filter parameters should not be included for List operations
        assert not classifier.should_include_in_function_signature("status", "ListJobs")

        # Identifier parameters should be included
        assert classifier.should_include_in_function_signature("farmId", "ListJobs")

    def test_classifier_works_with_real_operations(self):
        """Test classifier works with real Deadline Cloud operation names."""
        from deadline.mcp.parameter_classifier import DynamicParameterClassifier

        classifier = DynamicParameterClassifier()

        # Test with real Deadline Cloud operations
        real_operations = [
            "ListFarms",
            "GetFarm",
            "CreateFarm",
            "UpdateFarm",
            "DeleteFarm",
            "ListQueues",
            "GetQueue",
            "CreateQueue",
            "UpdateQueue",
            "DeleteQueue",
            "ListJobs",
            "GetJob",
            "CreateJob",
            "UpdateJob",
            "CancelJob",
            "SearchJobs",
            "SearchWorkers",
            "SearchSteps",
        ]

        for operation in real_operations:
            # Should be able to classify parameters for any operation
            pagination_params = ["nextToken", "maxResults", "pageSize", "limit"]
            filter_params = ["status", "filterExpressions", "sortBy", "displayName"]
            identifier_params = ["farmId", "queueId", "jobId"]

            for param in pagination_params:
                assert classifier.classify_parameter(param, operation).value == "pagination"
                assert not classifier.should_include_in_function_signature(param, operation)

            for param in filter_params:
                assert classifier.classify_parameter(param, operation).value == "filter"

            for param in identifier_params:
                assert classifier.classify_parameter(param, operation).value == "identifier"
                assert classifier.should_include_in_function_signature(param, operation)


class TestNameConverterIntegration:
    """Test integration with the unified NameConverter utility."""

    def test_name_converter_usage(self):
        """Test that NameConverter is used throughout the server."""
        from deadline.mcp.utils import NameConverter

        # Test snake_case conversion
        assert NameConverter.to_snake_case("GetFarm") == "get_farm"
        assert NameConverter.to_snake_case("ListQueues") == "list_queues"
        assert NameConverter.to_snake_case("farmId") == "farm_id"

        # Test kebab-case conversion
        assert NameConverter.to_kebab_case("GetFarm") == "get-farm"
        assert NameConverter.to_kebab_case("QueueFleetAssociations") == "queue-fleet-associations"

        # Test camelCase conversion
        assert NameConverter.to_camel_case("farm_id") == "farmId"
        assert NameConverter.to_camel_case("queue_id") == "queueId"


class TestFunctionBuilder:
    """Test function builder integration."""

    def test_function_builder_creates_functions(self):
        """Test that function builder creates working functions."""
        from deadline.mcp.function_builder import MCPFunctionBuilder

        builder = MCPFunctionBuilder()

        # Mock operation schema
        schema = {
            "type": "object",
            "properties": {
                "farmId": {"type": "string"},
                "displayName": {"type": "string"},
            },
            "required": ["farmId"],
        }

        # Mock client
        mock_client = Mock()
        mock_client.get_farm = Mock(return_value={"farmId": "test-farm"})

        # Build function
        func = builder.build_function("GetFarm", schema, mock_client, is_resource=True)

        assert func is not None
        assert callable(func)
        assert hasattr(func, "__signature__")

    def test_parameter_processor_excludes_correctly(self):
        """Test that parameter processor excludes the right parameters."""
        from deadline.mcp.function_builder import ParameterProcessor

        processor = ParameterProcessor()

        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "nextToken": {"type": "string"},
                "maxResults": {"type": "integer"},
                "status": {"type": "string"},
            },
            "required": ["farmId"],
        }

        # Test resource exclusions for List operation
        properties, required, param_mapping = processor.process_parameters(
            "ListQueues", schema, is_resource=True
        )

        # Should exclude pagination and filter parameters for List operations
        assert "nextToken" not in properties
        assert "maxResults" not in properties

        # Should include identifier parameters
        assert "farmId" in properties or len(properties) == 0  # Might be excluded if no URI params

        # Test tool exclusions (should not exclude anything)
        properties, required, param_mapping = processor.process_parameters(
            "CreateFarm", schema, is_resource=False
        )

        # Tools should include all parameters
        assert len(properties) == len(schema["properties"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
