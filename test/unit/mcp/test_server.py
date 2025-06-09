"""Tests for MCP server implementation."""

from unittest.mock import Mock, patch
from fastmcp import FastMCP

from deadline.mcp.server import (
    create_mcp_app,
    register_tools,
    main,
    _register_tool,
)


class TestCreateMcpApp:
    """Test MCP application creation."""

    def test_create_mcp_app_basic(self):
        """Test creating basic MCP application."""
        app = create_mcp_app()

        assert isinstance(app, FastMCP)
        assert app.name == "deadline-mcp"

    def test_create_mcp_app_with_custom_name(self):
        """Test creating MCP application with custom name."""
        app = create_mcp_app(name="custom-deadline-mcp")

        assert isinstance(app, FastMCP)
        assert app.name == "custom-deadline-mcp"


class TestRegisterAllTools:
    """Test tool registration functionality."""

    @patch("deadline.mcp.server.boto3.client")
    @patch("deadline.mcp.server._register_tool")
    def test_register_tools(self, mock_register_single, mock_boto3_client):
        """Test registering all tools with the MCP app."""
        # Setup mock app
        mock_app = Mock(spec=FastMCP)

        # Setup mock boto3 client and service model
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListFarms", "CreateFarm"]
        mock_client._service_model = mock_service_model
        mock_boto3_client.return_value = mock_client

        # Mock operation models
        list_farms_op = Mock()
        list_farms_op.name = "ListFarms"
        create_farm_op = Mock()
        create_farm_op.name = "CreateFarm"

        mock_service_model.operation_model.side_effect = [list_farms_op, create_farm_op]

        # Call function under test
        register_tools(mock_app)

        # Verify boto3 client was created
        mock_boto3_client.assert_called_once_with("deadline")

        # Verify _register_single_tool was called for each operation
        assert mock_register_single.call_count == 2

        # Verify the register calls contained the expected operation names
        register_calls = mock_register_single.call_args_list
        operation_names = [
            call[0][1] for call in register_calls
        ]  # Second argument is operation_name
        assert "ListFarms" in operation_names
        assert "CreateFarm" in operation_names

    @patch("deadline.mcp.server.boto3.client")
    def test_register_tools_empty_service_model(self, mock_boto3_client):
        """Test registering tools with empty service model."""
        mock_app = Mock(spec=FastMCP)

        # Setup mock with no operations
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = []
        mock_client._service_model = mock_service_model
        mock_boto3_client.return_value = mock_client

        register_tools(mock_app)

        mock_boto3_client.assert_called_once_with("deadline")
        # No tools should be registered

    @patch("deadline.mcp.server.boto3.client")
    @patch("deadline.mcp.server._register_tool")
    def test_register_tools_handles_register_error(self, mock_register_single, mock_boto3_client):
        """Test that tool registration handles registration errors gracefully."""
        mock_app = Mock(spec=FastMCP)

        # Setup mock with one operation
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListFarms"]
        mock_client._service_model = mock_service_model
        mock_boto3_client.return_value = mock_client

        # Mock operation model
        list_farms_op = Mock()
        mock_service_model.operation_model.return_value = list_farms_op

        # Make _register_single_tool raise an exception
        mock_register_single.side_effect = Exception("Registration failed")

        # Should not raise exception
        register_tools(mock_app)

        mock_register_single.assert_called_once()


class TestRegisterSingleTool:
    """Test single tool registration."""

    @patch("deadline.mcp.server.generate_tool_function")
    @patch("deadline.mcp.server.extract_operation_documentation")
    def test_register_single_tool_with_documentation(self, mock_extract_doc, mock_generate_tool):
        """Test registering a single tool with documentation."""
        mock_app = Mock(spec=FastMCP)
        mock_tool_decorator = Mock()
        mock_app.tool.return_value = mock_tool_decorator

        # Mock operation model
        mock_operation_model = Mock()

        # Mock generate_tool_function to return function name and callable
        mock_tool_func = Mock()
        mock_generate_tool.return_value = ("deadline_list_farms", mock_tool_func)

        # Mock extracted documentation
        mock_extract_doc.return_value = "Lists farms in your AWS account."

        result = _register_tool(mock_app, "ListFarms", mock_operation_model)

        # Verify generate_tool_function was called
        mock_generate_tool.assert_called_once_with("ListFarms", mock_operation_model)

        # Verify app.tool was called with correct parameters
        mock_app.tool.assert_called_once_with(
            name="deadline_list_farms", description="Lists farms in your AWS account."
        )

        # Verify the decorator was applied to the generated function
        mock_tool_decorator.assert_called_once_with(mock_tool_func)

        # Verify return value
        assert result == "deadline_list_farms"

    @patch("deadline.mcp.server.generate_tool_function")
    @patch("deadline.mcp.server.extract_operation_documentation")
    def test_register_single_tool_without_documentation(self, mock_extract_doc, mock_generate_tool):
        """Test registering a single tool without documentation."""
        mock_app = Mock(spec=FastMCP)
        mock_tool_decorator = Mock()
        mock_app.tool.return_value = mock_tool_decorator

        # Mock operation model
        mock_operation_model = Mock()

        # Mock generate_tool_function to return function name and callable
        mock_tool_func = Mock()
        mock_generate_tool.return_value = ("deadline_list_farms", mock_tool_func)

        # Mock extracted documentation (empty)
        mock_extract_doc.return_value = ""

        result = _register_tool(mock_app, "ListFarms", mock_operation_model)

        # Should use empty description
        mock_app.tool.assert_called_once_with(name="deadline_list_farms", description="")
        assert result == "deadline_list_farms"

    @patch("deadline.mcp.server.generate_tool_function")
    @patch("deadline.mcp.server.extract_operation_documentation")
    def test_register_single_tool_with_parameters(self, mock_extract_doc, mock_generate_tool):
        """Test registering a single tool with parameters."""
        mock_app = Mock(spec=FastMCP)
        mock_tool_decorator = Mock()
        mock_app.tool.return_value = mock_tool_decorator

        # Mock operation model
        mock_operation_model = Mock()

        # Mock generate_tool_function to return function name and callable
        mock_tool_func = Mock()
        mock_generate_tool.return_value = ("deadline_list_farms", mock_tool_func)

        # Mock extracted documentation
        mock_extract_doc.return_value = "Lists farms with parameters."

        result = _register_tool(mock_app, "ListFarms", mock_operation_model)

        # Verify app.tool was called with correct parameters
        mock_app.tool.assert_called_once_with(
            name="deadline_list_farms", description="Lists farms with parameters."
        )

        # Verify the decorator was applied to the generated function
        mock_tool_decorator.assert_called_once_with(mock_tool_func)
        assert result == "deadline_list_farms"


class TestMain:
    """Test main server entry point."""

    @patch("deadline.mcp.server.register_tools")
    @patch("deadline.mcp.server.create_mcp_app")
    def test_main_creates_app_and_registers_tools(self, mock_create_app, mock_register):
        """Test main function creates app and registers tools."""
        mock_app = Mock(spec=FastMCP)
        mock_create_app.return_value = mock_app

        main()

        # Verify app creation
        mock_create_app.assert_called_once_with()

        # Verify tool registration
        mock_register.assert_called_once_with(mock_app)

        # Verify app.run was called
        mock_app.run.assert_called_once()

    @patch("deadline.mcp.server.register_tools")
    @patch("deadline.mcp.server.create_mcp_app")
    def test_main_handles_registration_error(self, mock_create_app, mock_register):
        """Test main function handles tool registration errors."""
        mock_app = Mock(spec=FastMCP)
        mock_create_app.return_value = mock_app
        mock_register.side_effect = Exception("Registration failed")

        # Should not raise exception
        main()

        # Should still try to start server
        mock_app.run.assert_called_once()

    @patch("deadline.mcp.server.register_tools")
    @patch("deadline.mcp.server.create_mcp_app")
    def test_main_handles_server_error(self, mock_create_app, mock_register):
        """Test main function handles server startup errors."""
        mock_app = Mock(spec=FastMCP)
        mock_create_app.return_value = mock_app

        mock_app.run.side_effect = Exception("Server failed to start")

        # Should not raise exception
        main()


class TestIntegration:
    """Integration tests for the complete server."""

    @patch("deadline.mcp.boto3_adaptor.boto3.client")
    def test_full_server_integration(self, mock_boto3_client):
        """Test full server creation and tool registration integration."""
        # Mock boto3 client and service model
        mock_client = Mock()
        mock_service_model = Mock()
        mock_service_model.operation_names = ["ListFarms", "CreateFarm"]
        mock_client._service_model = mock_service_model
        mock_boto3_client.return_value = mock_client

        # Mock operation models
        list_farms_op = Mock()
        list_farms_op.name = "ListFarms"
        list_farms_op.documentation = "Lists farms"
        list_farms_op.input_shape = None

        create_farm_op = Mock()
        create_farm_op.name = "CreateFarm"
        create_farm_op.documentation = "Creates farm"
        create_farm_op.input_shape = None

        mock_service_model.operation_model.side_effect = [list_farms_op, create_farm_op]

        # Create app and register tools
        app = create_mcp_app()

        with patch("deadline.mcp.server._register_tool") as mock_register:
            register_tools(app)

            # Should have attempted to register tools
            assert mock_register.call_count >= 2

    def test_server_name_configuration(self):
        """Test server name can be configured."""
        app1 = create_mcp_app()
        app2 = create_mcp_app(name="custom-server")

        assert app1.name == "deadline-mcp"
        assert app2.name == "custom-server"
