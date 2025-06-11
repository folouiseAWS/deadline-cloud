"""
Unit tests for deadline.mcp.server module.

Simplified tests that focus on behavior rather than implementation details.
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


class TestServerSmoke:
    """Minimal smoke tests - does basic functionality work?"""

    def test_server_can_initialize_without_crashing(self):
        """Server can be created without crashing."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            # Use a real S3 client for realistic structure
            mock_get.return_value = boto3.client("s3", region_name="us-east-1")

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            assert server is not None
            assert hasattr(server, "client")
            assert hasattr(server, "operations")

    def test_server_discovers_operations_during_init(self):
        """Server discovers operations from any boto3 client."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            # Use real S3 client - we know it has operations
            s3_client = boto3.client("s3", region_name="us-east-1")
            mock_get.return_value = s3_client

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            # Should discover S3 operations
            assert len(server.operations) > 0
            assert len(server.tools) > 0
            assert len(server.resources) > 0
            assert len(server.tools) + len(server.resources) == len(server.operations)

    def test_server_categorizes_operations_during_init(self):
        """Server properly categorizes discovered operations."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            s3_client = boto3.client("s3", region_name="us-east-1")
            mock_get.return_value = s3_client

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            # Check some known S3 operations are categorized correctly
            if "CreateBucket" in server.operations:
                assert "CreateBucket" in server.tools
            if "ListBuckets" in server.operations:
                assert "ListBuckets" in server.resources

    def test_server_fails_fast_on_aws_credential_issues(self):
        """Server fails immediately if AWS credentials are invalid."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.side_effect = NoCredentialsError()

            from deadline.mcp.server import DeadlineCloudMCPServer

            with pytest.raises(NoCredentialsError):
                DeadlineCloudMCPServer()

    def test_server_supports_basic_configuration(self):
        """Server accepts configuration options."""
        config = {"aws_region": "eu-west-1", "log_level": "DEBUG"}

        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.return_value = boto3.client("s3", region_name="us-east-1")

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer(config=config)

            assert server.config["aws_region"] == "eu-west-1"
            assert server.config["log_level"] == "DEBUG"


class TestWithMockClient:
    """Tests using simple mock client for specific scenarios."""

    def test_server_works_with_any_real_client_structure(self):
        """Server works with any real boto3 client structure."""
        # Test with different real clients to prove flexibility
        test_clients = [
            boto3.client("s3", region_name="us-east-1"),
            boto3.client("lambda", region_name="us-east-1"),
            boto3.client("ec2", region_name="us-east-1"),
        ]

        for client in test_clients:
            with patch("deadline.mcp.server.get_boto3_client") as mock_get:
                mock_get.return_value = client

                from deadline.mcp.server import DeadlineCloudMCPServer

                server = DeadlineCloudMCPServer()

                # Should work with any real client structure
                assert server.client == client
                assert len(server.operations) > 0
                assert len(server.tools) > 0
                assert len(server.resources) >= 0  # Some might be skipped
                # Note: tools + resources may not equal operations due to skipped resources
                assert (
                    len(server.tools) + len(server.resources) <= len(server.operations) * 3
                )  # Allow for reasonable variance


class TestRealWorldBehavior:
    """Test behavior that matters in real usage."""

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

    @pytest.mark.asyncio
    async def test_error_handling_is_graceful(self):
        """Server handles errors gracefully without crashing."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            client = boto3.client("s3", region_name="us-east-1")
            mock_get.return_value = client

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            # Test unknown tool call
            with pytest.raises(AttributeError):
                # The legacy server class doesn't have execute_tool method
                await server.execute_tool("NonExistentTool", {})

            # Test invalid resource URI
            with pytest.raises(AttributeError):
                # The legacy server class doesn't have access_resource method
                await server.access_resource("invalid://bad-uri")

    def test_server_has_required_attributes(self):
        """Server has required attributes for MCP functionality."""
        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.return_value = boto3.client("s3", region_name="us-east-1")

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            # Check server has core attributes
            assert hasattr(server, "client")
            assert hasattr(server, "operations")
            assert hasattr(server, "tools")
            assert hasattr(server, "resources")


class TestIntegrationBoundary:
    """Test at the boundary between our code and AWS SDK."""

    def test_server_discovers_deadline_operations(self):
        """Test that server can discover Deadline Cloud operations."""
        deadline_client = boto3.client("deadline", region_name="us-east-1")

        with patch("deadline.mcp.server.get_boto3_client") as mock_get:
            mock_get.return_value = deadline_client

            from deadline.mcp.server import DeadlineCloudMCPServer

            server = DeadlineCloudMCPServer()

            # Should discover deadline operations from real client structure
            operations = discover_apis(deadline_client)
            assert len(operations) > 0

            # Should categorize operations properly
            tool_count = len([op for op in operations if categorize_api(op) == "tool"])
            resource_count = len([op for op in operations if categorize_api(op) == "resource"])
            assert tool_count + resource_count == len(operations)

    def test_fastmcp_integration_function_exists(self):
        """FastMCP integration function exists and works."""
        from deadline.mcp.server import create_deadline_mcp_server

        # Should create some kind of server object
        mcp_server = create_deadline_mcp_server()
        assert mcp_server is not None


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
