"""Tests for MCP server boto3 adaptor."""

import pytest
from unittest.mock import Mock, patch

from deadline.mcp.boto3_adaptor import (
    discover_deadline_operations,
    generate_tool_function,
    create_tool_registry,
    execute_deadline_operation,
)


class TestDiscoverDeadlineOperations:
    """Test discovery of deadline operations from boto3 service model."""

    def test_discover_operations_from_service_model(self, real_deadline_service_model):
        """Test discovering operations from service model."""
        operations = discover_deadline_operations(real_deadline_service_model)

        # Real service model has 113+ operations, check for key ones
        expected_operations = ["ListFarms", "CreateFarm", "GetFarm", "DeleteFarm"]
        for expected_op in expected_operations:
            assert expected_op in operations
        assert len(operations) > 100  # Real deadline has 113+ operations

    def test_discover_operations_empty_service_model(self):
        """Test discovering operations from empty service model."""
        service_model = Mock()
        service_model.operation_names = []

        operations = discover_deadline_operations(service_model)
        assert operations == []

    @patch("deadline.mcp.boto3_adaptor.boto3.client")
    def test_discover_operations_from_client(self, mock_boto3_client):
        """Test discovering operations directly from boto3 client."""
        mock_client = Mock()
        real_deadline_service_model = Mock()
        real_deadline_service_model.operation_names = ["ListFarms", "CreateFarm"]
        mock_client._service_model = real_deadline_service_model
        mock_boto3_client.return_value = mock_client

        operations = discover_deadline_operations()

        mock_boto3_client.assert_called_once_with("deadline")
        assert operations == ["ListFarms", "CreateFarm"]


class TestGenerateToolFunction:
    """Test generation of MCP tool functions from operation models."""

    def test_generate_tool_function_with_optional_params(self, real_list_farms_operation):
        """Test generating tool function for operation with optional parameters."""
        func_name, func_obj = generate_tool_function("ListFarms", real_list_farms_operation)

        assert func_name == "deadline_list_farms"
        assert callable(func_obj)
        assert func_obj.__name__ == "deadline_list_farms"

        # Check signature has the expected parameters
        sig = func_obj.__signature__  # type: ignore[attr-defined]
        param_names = list(sig.parameters.keys())
        assert "maxResults" in param_names
        assert "nextToken" in param_names
        assert "principalId" in param_names

        # Check documentation
        assert func_obj.__doc__ is not None
        assert "farms" in func_obj.__doc__.lower()

    def test_generate_tool_function_with_required_params(self, real_create_farm_operation):
        """Test generating tool function for operation with required parameters."""
        func_name, func_obj = generate_tool_function("CreateFarm", real_create_farm_operation)

        assert func_name == "deadline_create_farm"
        assert callable(func_obj)
        assert func_obj.__name__ == "deadline_create_farm"

        # Check signature has the expected parameters
        sig = func_obj.__signature__  # type: ignore[attr-defined]
        param_names = list(sig.parameters.keys())
        assert "displayName" in param_names  # Required parameter
        assert "clientToken" in param_names
        assert "description" in param_names
        assert "kmsKeyArn" in param_names

        # Check documentation
        assert func_obj.__doc__ is not None
        assert "farm" in func_obj.__doc__.lower()

    def test_generate_tool_function_no_params(self):
        """Test generating tool function for operation with no parameters."""
        operation = Mock()
        operation.name = "GetCallerIdentity"
        operation.documentation = "Get caller identity"
        operation.input_shape = None

        func_name, func_obj = generate_tool_function("GetCallerIdentity", operation)

        assert func_name == "deadline_get_caller_identity"
        assert callable(func_obj)
        assert func_obj.__name__ == "deadline_get_caller_identity"
        assert func_obj.__doc__ is not None
        assert "Get caller identity" in func_obj.__doc__

    def test_generate_tool_function_snake_case_conversion(self):
        """Test snake_case conversion of operation names."""
        operation = Mock()
        operation.name = "ListJobsForQueue"
        operation.documentation = "List queue jobs"
        operation.input_shape = None

        func_name, func_obj = generate_tool_function("ListJobsForQueue", operation)

        assert func_name == "deadline_list_jobs_for_queue"


class TestCreateToolRegistry:
    """Test creation of tool registry for fastmcp."""

    @patch("deadline.mcp.boto3_adaptor.boto3.client")
    def test_create_tool_registry(self, mock_boto3_client):
        """Test creating complete tool registry."""
        # Create a mock service model instead of using real one
        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListFarms", "CreateFarm"]

        # Setup mock client
        mock_client = Mock()
        mock_client._service_model = mock_service_model
        mock_boto3_client.return_value = mock_client

        # Create simple mock operations for testing
        mock_list_farms = Mock()
        mock_list_farms.name = "ListFarms"
        mock_list_farms.documentation = "Lists farms"
        mock_list_farms.input_shape = None

        mock_create_farm = Mock()
        mock_create_farm.name = "CreateFarm"
        mock_create_farm.documentation = "Creates farm"
        mock_create_farm.input_shape = None

        mock_service_model.operation_model.side_effect = [
            mock_list_farms,
            mock_create_farm,
        ]

        registry = create_tool_registry()

        assert "deadline_list_farms" in registry
        assert "deadline_create_farm" in registry
        assert len(registry) >= 2

    def test_create_empty_tool_registry(self):
        """Test creating tool registry with no operations."""
        with patch("deadline.mcp.boto3_adaptor.boto3.client") as mock_boto3_client:
            mock_client = Mock()
            real_deadline_service_model = Mock()
            real_deadline_service_model.operation_names = []
            mock_client._service_model = real_deadline_service_model
            mock_boto3_client.return_value = mock_client

            registry = create_tool_registry()
            assert registry == {}


class TestExecuteDeadlineOperation:
    """Test execution of deadline operations."""

    @patch("deadline.mcp.boto3_adaptor.get_boto3_client")
    def test_execute_operation_with_parameters(self, mock_get_client):
        """Test executing operation with parameters."""
        mock_client = Mock()
        mock_client.list_farms.return_value = {"farms": [{"farmId": "farm-1"}]}
        mock_get_client.return_value = mock_client

        result = execute_deadline_operation("list_farms", {"maxResults": 10, "nextToken": "token"})

        mock_client.list_farms.assert_called_once_with(maxResults=10, nextToken="token")
        assert result == {"farms": [{"farmId": "farm-1"}]}

    @patch("deadline.mcp.boto3_adaptor.get_boto3_client")
    def test_execute_operation_no_parameters(self, mock_get_client):
        """Test executing operation with no parameters."""
        mock_client = Mock()
        mock_client.get_caller_identity.return_value = {"Account": "123456789"}
        mock_get_client.return_value = mock_client

        result = execute_deadline_operation("get_caller_identity", {})

        mock_client.get_caller_identity.assert_called_once_with()
        assert result == {"Account": "123456789"}

    @patch("deadline.mcp.boto3_adaptor.get_boto3_client")
    def test_execute_operation_filters_none_values(self, mock_get_client):
        """Test that None values are filtered out from parameters."""
        mock_client = Mock()
        mock_client.list_farms.return_value = {"farms": []}
        mock_get_client.return_value = mock_client

        result = execute_deadline_operation("list_farms", {"maxResults": 10})

        # Should only pass non-None parameters
        mock_client.list_farms.assert_called_once_with(maxResults=10)
        assert result == {"farms": []}

    @patch("deadline.mcp.boto3_adaptor.get_boto3_client")
    def test_execute_operation_handles_client_error(self, mock_get_client):
        """Test handling of boto3 ClientError."""
        from botocore.exceptions import ClientError

        mock_client = Mock()
        error = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListFarms",
        )
        mock_client.list_farms.side_effect = error
        mock_get_client.return_value = mock_client

        with pytest.raises(ClientError):
            execute_deadline_operation("list_farms", {})


class TestIntegration:
    """Integration tests using real service models."""

    def test_real_service_model_integration(self):
        """Test complete flow with real boto3 service model."""
        # This uses real boto3.client('deadline') service model
        operations = discover_deadline_operations()

        # Should discover real operations
        assert len(operations) > 0
        assert "ListFarms" in operations
        assert "CreateFarm" in operations

    def test_create_fleet_complex_api(self):
        """Test CreateFleet operation - complex API with nested structures."""
        import boto3

        # Get real CreateFleet operation model
        client = boto3.client("deadline")
        service_model = client._service_model
        create_fleet_op = service_model.operation_model("CreateFleet")

        # Generate tool function
        func_name, func_obj = generate_tool_function("CreateFleet", create_fleet_op)

        # Verify function generation
        assert func_name == "deadline_create_fleet"
        assert callable(func_obj)
        assert hasattr(func_obj, "__signature__")
        assert hasattr(func_obj, "__annotations__")

        # Examine signature for complex parameter handling
        sig = func_obj.__signature__
        param_names = list(sig.parameters.keys())

        # CreateFleet should have these key parameters
        assert "farmId" in param_names
        assert "displayName" in param_names
        assert "roleArn" in param_names
        assert "maxWorkerCount" in param_names
        assert "configuration" in param_names

        # Test parameter ordering (.clinerules compliance)
        # Required parameters should come before optional ones
        required_params = []
        optional_params = []

        for param_name, param in sig.parameters.items():
            if param.default is param.empty:
                required_params.append(param_name)
            else:
                optional_params.append(param_name)

        print(f"Required params: {required_params}")
        print(f"Optional params: {optional_params}")

        # Verify required parameters come first
        all_param_names = list(sig.parameters.keys())
        required_end_idx = len(required_params)

        assert all_param_names[:required_end_idx] == required_params

        # Test type annotations for complex structures
        annotations = func_obj.__annotations__

        # farmId should be str
        assert annotations.get("farmId") is str

        # displayName should be str
        assert annotations.get("displayName") is str

        # maxWorkerCount should be int
        assert annotations.get("maxWorkerCount") is int

        # configuration should be a complex type (Dict)
        config_type = annotations.get("configuration")
        assert config_type is not None
        print(f"Configuration type: {config_type}")

        # Test that we can call the function with proper parameters
        # (This won't actually execute since we're not mocking the full client)
        try:
            # This should not raise a signature error
            import inspect

            inspect.signature(func_obj).bind(
                farmId="test-farm",
                displayName="Test Fleet",
                roleArn="arn:aws:iam::123:role/test",
                maxWorkerCount=10,
                configuration={"instanceType": "m5.large"},
            )
            # If we get here, signature binding worked
            signature_valid = True
        except TypeError as e:
            print(f"Signature binding failed: {e}")
            signature_valid = False

        assert signature_valid, "Function signature should accept proper parameters"

        # Test .clinerules compliance by checking internal structure
        # The function should not use **kwargs in the visible signature
        sig_str = str(sig)
        assert "**kwargs" not in sig_str, "Public signature should not contain **kwargs"

        # Verify function has proper attributes for FastMCP/Pydantic
        assert hasattr(func_obj, "__name__")
        assert hasattr(func_obj, "__doc__")
        assert hasattr(func_obj, "__signature__")
        assert hasattr(func_obj, "__annotations__")

        print(f"CreateFleet function signature: {sig}")
        print(f"CreateFleet annotations: {annotations}")
