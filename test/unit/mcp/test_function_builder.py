"""
Tests for MCP Function Builder components.

Tests the modular function building system that replaces the monolithic
_create_function_with_typed_params() function.
"""

import pytest
import inspect
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch
from deadline.mcp.function_builder import (
    ParameterProcessor,
    FunctionSignatureBuilder,
    FunctionWrapperBuilder,
    MCPFunctionBuilder,
)


class TestParameterProcessor:
    """Test the ParameterProcessor component."""

    def setup_method(self):
        self.processor = ParameterProcessor()

    def test_tool_parameter_processing(self):
        """Test parameter processing for tool functions."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "maxResults": {"type": "integer"},
                "nextToken": {"type": "string"},
            },
            "required": ["farmId"],
        }

        properties, required, param_mapping = self.processor.process_parameters(
            "CreateQueue", schema, is_resource=False
        )

        # Tools should keep all parameters
        assert len(properties) == 4
        assert "farmId" in properties
        assert "maxResults" in properties
        assert required == {"farmId"}
        assert param_mapping["farm_id"] == "farmId"
        assert param_mapping["queue_id"] == "queueId"

    def test_list_resource_parameter_processing(self):
        """Test parameter processing for List resource functions."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "maxResults": {"type": "integer"},
                "nextToken": {"type": "string"},
                "filterExpressions": {"type": "array"},
            },
            "required": ["farmId"],
        }

        properties, required, param_mapping = self.processor.process_parameters(
            "ListQueues", schema, is_resource=True
        )

        # List resources should exclude pagination/filter params but keep URI params
        assert "farmId" in param_mapping.values()  # URI parameter preserved
        assert "maxResults" not in param_mapping.values()  # Pagination excluded
        assert "nextToken" not in param_mapping.values()  # Pagination excluded
        assert "filterExpressions" not in param_mapping.values()  # Filter excluded

    def test_get_resource_parameter_processing(self):
        """Test parameter processing for Get resource functions."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "maxResults": {"type": "integer"},  # Should be excluded
                "nextToken": {"type": "string"},  # Should be excluded
            },
            "required": ["farmId", "queueId"],
        }

        properties, required, param_mapping = self.processor.process_parameters(
            "GetQueue", schema, is_resource=True
        )

        # Get resources should keep ID parameters but exclude pagination
        assert "farmId" in param_mapping.values()
        assert "queueId" in param_mapping.values()
        assert "maxResults" not in param_mapping.values()
        assert "nextToken" not in param_mapping.values()
        assert param_mapping["farm_id"] == "farmId"
        assert param_mapping["queue_id"] == "queueId"

    def test_snake_case_conversion(self):
        """Test PascalCase to snake_case conversion."""
        from deadline.mcp.utils import NameConverter

        assert NameConverter.to_snake_case("farmId") == "farm_id"
        assert NameConverter.to_snake_case("maxResults") == "max_results"
        assert NameConverter.to_snake_case("resourceArn") == "resource_arn"
        assert NameConverter.to_snake_case("id") == "id"


class TestFunctionSignatureBuilder:
    """Test the FunctionSignatureBuilder component."""

    def setup_method(self):
        self.builder = FunctionSignatureBuilder()

    def test_signature_with_required_and_optional_params(self):
        """Test building signatures with mixed parameter types."""
        param_mapping = {
            "farm_id": "farmId",
            "queue_id": "queueId",
            "max_results": "maxResults",
        }
        required_params = {"farmId", "queueId"}

        signature = self.builder.build_signature(param_mapping, required_params)

        # Check parameter count
        assert len(signature.parameters) == 3

        # Check parameter order (required first)
        param_names = list(signature.parameters.keys())
        required_indices = [
            i
            for i, name in enumerate(param_names)
            if signature.parameters[name].default is inspect.Parameter.empty
        ]
        optional_indices = [
            i
            for i, name in enumerate(param_names)
            if signature.parameters[name].default is not inspect.Parameter.empty
        ]

        # Required parameters should come before optional ones
        assert all(
            req_idx < opt_idx for req_idx in required_indices for opt_idx in optional_indices
        )

    def test_signature_parameter_types(self):
        """Test that all parameters have string annotations."""
        param_mapping = {"farm_id": "farmId", "queue_id": "queueId"}
        required_params = {"farmId"}

        signature = self.builder.build_signature(param_mapping, required_params)

        for param in signature.parameters.values():
            assert param.annotation == str

    def test_empty_signature(self):
        """Test building signature with no parameters."""
        signature = self.builder.build_signature({}, set())
        assert len(signature.parameters) == 0


class TestFunctionWrapperBuilder:
    """Test the FunctionWrapperBuilder component."""

    def setup_method(self):
        self.builder = FunctionWrapperBuilder()

    @pytest.mark.asyncio
    async def test_successful_api_call(self):
        """Test wrapper with successful API call."""
        # Mock client
        mock_client = Mock()
        mock_method = Mock(return_value={"result": "success"})
        mock_client.get_farm = mock_method

        # Create signature
        param_mapping = {"farm_id": "farmId"}
        signature = inspect.Signature(
            [inspect.Parameter("farm_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
        )

        # Build wrapper
        wrapper = self.builder.build_wrapper("GetFarm", signature, param_mapping, mock_client)

        # Test execution
        result = await wrapper(farm_id="test-farm")
        assert result == {"result": "success"}
        mock_method.assert_called_once_with(farmId="test-farm")

    @pytest.mark.asyncio
    async def test_parameter_binding_failure(self):
        """Test wrapper with parameter binding failure."""
        mock_client = Mock()
        param_mapping = {"farm_id": "farmId"}
        signature = inspect.Signature(
            [
                inspect.Parameter(
                    "farm_id",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=str,
                    default=inspect.Parameter.empty,
                )
            ]
        )

        wrapper = self.builder.build_wrapper("GetFarm", signature, param_mapping, mock_client)

        # Call without required parameter should return error dict
        result = await wrapper()
        assert "error" in result
        assert result["error"] == "Parameter binding failed"
        assert result["operation"] == "GetFarm"

    @pytest.mark.asyncio
    async def test_api_exception_handling(self):
        """Test wrapper with API exception."""
        mock_client = Mock()
        mock_method = Mock(side_effect=Exception("API Error"))
        mock_client.get_farm = mock_method

        param_mapping = {"farm_id": "farmId"}
        signature = inspect.Signature(
            [inspect.Parameter("farm_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
        )

        wrapper = self.builder.build_wrapper("GetFarm", signature, param_mapping, mock_client)

        # API exception should return error dict
        result = await wrapper(farm_id="test-farm")
        assert "error" in result
        assert result["error"] == "API call failed"
        assert result["operation"] == "GetFarm"
        assert "API Error" in result["message"]

    def test_wrapper_metadata(self):
        """Test that wrapper has correct metadata."""
        mock_client = Mock()
        param_mapping = {"farm_id": "farmId"}
        signature = inspect.Signature(
            [inspect.Parameter("farm_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
        )

        wrapper = self.builder.build_wrapper(
            "GetFarm", signature, param_mapping, mock_client, is_resource=True
        )

        assert wrapper.__name__ == "get_farm_function"
        assert "resource function for GetFarm" in wrapper.__doc__
        assert wrapper.__signature__ == signature
        assert wrapper.__annotations__["return"] == Dict[str, Any]


class TestMCPFunctionBuilder:
    """Test the main MCPFunctionBuilder orchestrator."""

    def setup_method(self):
        self.builder = MCPFunctionBuilder()

    @pytest.mark.asyncio
    async def test_tool_function_creation(self):
        """Test creating a complete tool function."""
        mock_client = Mock()
        mock_method = Mock(return_value={"result": "success"})
        mock_client.create_queue = mock_method

        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "displayName": {"type": "string"},
            },
            "required": ["farmId", "displayName"],
        }

        func = self.builder.build_function("CreateQueue", schema, mock_client, is_resource=False)

        # Test function execution
        result = await func(farm_id="test-farm", display_name="test-queue")
        assert result == {"result": "success"}
        mock_method.assert_called_once_with(farmId="test-farm", displayName="test-queue")

    def test_function_signature_correctness(self):
        """Test that generated functions have correct signatures."""
        mock_client = Mock()
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "maxResults": {"type": "integer"},
            },
            "required": ["farmId"],
        }

        func = self.builder.build_function("GetQueue", schema, mock_client, is_resource=True)

        # Check signature
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # Should have snake_case parameters
        assert "farm_id" in param_names
        assert "queue_id" in param_names
        assert "maxResults" not in param_names  # Should be excluded for resources

    def test_edge_case_no_properties_with_uri_params(self):
        """Test handling of operations with URI params but no properties - should raise error."""
        mock_client = Mock()
        schema = {"properties": {}, "required": []}

        # Mock ResourceURIMapper to return a pattern with URI params
        with patch(
            "deadline.mcp.function_builder.ResourceURIMapper.get_uri_pattern_with_schema"
        ) as mock_uri:
            mock_uri.return_value = "deadline://farm/{farm_id}/resource/{resource_id}"

            # Should raise error for operations with URI params but no properties
            with pytest.raises(
                ValueError,
                match="Resource operation GetWeirdResource has URI params.*but no properties",
            ):
                self.builder.build_function(
                    "GetWeirdResource", schema, mock_client, is_resource=True
                )

    def test_edge_case_global_resource_no_properties(self):
        """Test handling of global operations with no properties - should be allowed."""
        mock_client = Mock()
        schema = {"properties": {}, "required": []}

        # Mock ResourceURIMapper to return a pattern with no URI params (global resource)
        with patch(
            "deadline.mcp.function_builder.ResourceURIMapper.get_uri_pattern_with_schema"
        ) as mock_uri:
            mock_uri.return_value = "deadline://farms"  # No {param} placeholders

            # Should NOT raise error for global operations with no properties
            func = self.builder.build_function("ListFarms", schema, mock_client, is_resource=True)
            assert callable(func)

    @pytest.mark.asyncio
    async def test_parameter_filtering_integration(self):
        """Test integration between parameter processing and function creation."""
        mock_client = Mock()
        mock_method = Mock(return_value={"queues": []})
        mock_client.list_queues = mock_method

        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "maxResults": {"type": "integer"},
                "nextToken": {"type": "string"},
                "filterExpressions": {"type": "array"},
            },
            "required": ["farmId"],
        }

        func = self.builder.build_function("ListQueues", schema, mock_client, is_resource=True)

        # Should only accept farmId (other params filtered out for resources)
        result = await func(farm_id="test-farm")
        assert result == {"queues": []}
        mock_method.assert_called_once_with(farmId="test-farm")

    def test_snake_case_parameter_conversion(self):
        """Test that camelCase parameters are converted to snake_case in signatures."""
        mock_client = Mock()
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueEnvironmentId": {"type": "string"},
                "storageProfileId": {"type": "string"},
            },
            "required": [],
        }

        func = self.builder.build_function(
            "GetQueueEnvironment", schema, mock_client, is_resource=True
        )

        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        assert "farm_id" in param_names
        assert "queue_environment_id" in param_names
        assert "storage_profile_id" in param_names
        assert "farmId" not in param_names  # Original camelCase should not be present


class TestIntegrationWithExistingComponents:
    """Test integration with existing MCP components."""

    def test_parameter_classifier_integration(self):
        """Test that ParameterProcessor correctly uses DynamicParameterClassifier."""
        processor = ParameterProcessor()

        # The classifier should be properly initialized
        assert processor.classifier is not None
        assert hasattr(processor.classifier, "should_include_in_function_signature")
        assert hasattr(processor.classifier, "classify_parameter")

    def test_resource_uri_mapper_integration(self):
        """Test that ParameterProcessor correctly uses ResourceURIMapper."""
        processor = ParameterProcessor()

        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
            },
            "required": ["farmId", "queueId"],
        }

        # Should not raise an exception when calling ResourceURIMapper
        try:
            properties, required, param_mapping = processor.process_parameters(
                "GetQueue", schema, is_resource=True
            )
            # If we get here without exception, integration is working
            assert isinstance(properties, dict)
            assert isinstance(required, set)
            assert isinstance(param_mapping, dict)
        except Exception as e:
            pytest.fail(f"ResourceURIMapper integration failed: {e}")
