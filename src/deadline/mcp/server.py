"""Main MCP server implementation for AWS Deadline Cloud."""

from fastmcp import FastMCP
import logging

from deadline.mcp.boto3_adaptor import (
    discover_deadline_operations,
    generate_tool_function,
)
import boto3
from deadline.mcp.utils import (
    extract_operation_documentation,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mcp_app(name: str = "deadline-mcp") -> FastMCP:
    """
    Create FastMCP application instance.

    Args:
        name: Name of the MCP application

    Returns:
        FastMCP application instance
    """
    return FastMCP(name)


def register_tools(app: FastMCP) -> None:
    """
    Register all AWS Deadline Cloud tools with the MCP app.

    Args:
        app: FastMCP application instance
    """
    try:
        # Get boto3 client and service model for operation discovery
        client = boto3.client("deadline")
        service_model = client._service_model

        # Discover all operations
        operations = discover_deadline_operations(service_model)

        # For each operation, create a proper tool function
        for operation_name in operations:
            try:
                # Get the operation model
                operation_model = service_model.operation_model(operation_name)

                # Register the tool function using the existing generate_tool_function
                func_name = _register_tool(app, operation_name, operation_model)

                logger.info(f"Registered tool: {func_name}")

            except Exception as e:
                logger.warning(f"Failed to register tool for operation {operation_name}: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to create tool registry: {e}")


def _register_tool(app: FastMCP, operation_name: str, operation_model) -> str:
    """
    Register a single tool with the MCP app using the existing generate_tool_function.

    Args:
        app: FastMCP application instance
        operation_name: AWS operation name (CamelCase)
        operation_model: Boto3 operation model

    Returns:
        Function name that was registered
    """
    # Use the existing generate_tool_function to create the tool function
    func_name, tool_func = generate_tool_function(operation_name, operation_model)

    # Extract documentation from operation model
    description = extract_operation_documentation(operation_model)

    # Register with fastmcp using the tool decorator approach
    app.tool(name=func_name, description=description)(tool_func)

    return func_name


def main() -> None:
    """
    Main entry point for the MCP server.
    """
    try:
        # Create MCP application
        app = create_mcp_app()
        logger.info("Created MCP application")

        # Register all tools
        try:
            register_tools(app)
            logger.info("Registered all tools")
        except Exception as e:
            logger.error(f"Tool registration error: {e}")
            # Continue anyway - some tools may have been registered

        # Start stdio server
        logger.info("Starting MCP server...")
        app.run()

    except Exception as e:
        logger.error(f"Server error: {e}")
        # Don't re-raise - server should handle errors gracefully


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re

    # Insert underscore before uppercase letters (except the first one)
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    # Insert underscore before uppercase letters that follow lowercase letters
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


if __name__ == "__main__":
    main()
