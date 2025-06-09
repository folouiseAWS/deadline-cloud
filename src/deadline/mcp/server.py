"""
AWS Deadline Cloud MCP Server implementation.

FastMCP-based server that dynamically discovers and exposes Deadline Cloud APIs.
"""

from typing import Dict, Any, List, Optional
import logging
import sys
import boto3
from deadline.mcp.boto3_adaptor import (
    discover_apis,
    categorize_api,
    extract_parameter_schema,
    ResourceURIMapper,
)
from deadline.mcp.function_builder import MCPFunctionBuilder

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

# Global logger
logger = logging.getLogger(__name__)

# Global client and operations (will be set during initialization)
client = None
operations = []
tools = {}
resources = {}


def get_boto3_client():
    """
    Create and return a boto3 client for AWS Deadline Cloud.

    Returns:
        boto3.client: Configured Deadline Cloud client
    """
    return boto3.client("deadline")


def _convert_to_snake_case(name: str) -> str:
    """
    Convert PascalCase to snake_case for MCP function naming.

    This conversion is critical for MCP protocol compliance as:
    - AWS APIs use PascalCase (e.g., 'GetFarm', 'ListQueues')
    - MCP functions should use snake_case (e.g., 'get_farm', 'list_queues')
    - FastMCP expects consistent naming for tool/resource registration

    Args:
        name: PascalCase string from AWS operation name

    Returns:
        snake_case string suitable for MCP function names

    Examples:
        GetFarm -> get_farm
        ListQueues -> list_queues
        GetQueueEnvironment -> get_queue_environment
    """
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


# Global function builder instance
_function_builder = None


def _create_function_with_typed_params(
    operation_name: str, schema: Dict[str, Any], is_resource: bool = False
) -> Any:
    """Create a function with properly typed parameters based on schema.

    Now uses the modular MCPFunctionBuilder instead of monolithic logic.
    """
    global _function_builder

    # Initialize function builder on first use
    if _function_builder is None:
        _function_builder = MCPFunctionBuilder()

    # Use the new modular function builder
    return _function_builder.build_function(operation_name, schema, client, is_resource)


def _initialize_client_and_apis():
    """
    Initialize the boto3 client and discover all AWS Deadline Cloud APIs for MCP exposure.

    This function is the core of the MCP server's API discovery system. It:
    1. Creates a boto3 Deadline Cloud client for AWS API access
    2. Discovers all 113 available operations through introspection
    3. Categorizes operations as MCP tools (actions) or resources (data access)
    4. Extracts parameter schemas for MCP protocol compliance
    5. Generates URI patterns for MCP resource identification

    The discovery process enables dynamic MCP server configuration:
    - New AWS APIs are automatically exposed as MCP operations
    - No manual registration required for standard operations
    - Consistent categorization based on operation naming patterns

    MCP Protocol Impact:
    - Tools enable AI assistants to perform actions (Create, Update, Delete)
    - Resources provide structured data access (Get, List, Search)
    - Parameter schemas ensure proper MCP message validation
    - URI patterns enable MCP resource template functionality

    Global State Modified:
    - client: boto3 Deadline Cloud client instance
    - operations: List of all discovered operation names (113 total)
    - tools: Dict of tool definitions with schemas (61 operations)
    - resources: Dict of resource definitions with URI patterns (52 operations)
    """
    global client, operations, tools, resources

    if client is not None:
        return  # Already initialized

    logger.info("Initializing Deadline Cloud MCP Server...")

    # Create boto3 client
    client = get_boto3_client()
    logger.info("boto3 client created successfully")

    # Discover APIs
    operations = discover_apis(client)
    logger.info(f"Discovered {len(operations)} operations")

    # Categorize operations
    for operation in operations:
        category = categorize_api(operation)
        if category == "tool":
            tools[operation] = {
                "name": operation,
                "description": f"Execute {operation} operation",
                "schema": extract_parameter_schema(client, operation),
            }
        elif category == "resource":
            schema = extract_parameter_schema(client, operation)
            uri_pattern = ResourceURIMapper.get_uri_pattern_with_schema(operation, schema)

            # Check if this operation has URI parameters but no available properties
            # Skip registration for such operations to avoid parameter mismatches
            import re

            uri_params = set(re.findall(r"\{(\w+)\}", uri_pattern))
            properties = schema.get("properties", {})

            if uri_params and not properties:
                logger.warning(
                    f"Skipping resource registration for {operation} - has URI params {uri_params} but no properties"
                )
                continue

            resources[operation] = {
                "name": operation,
                "uri": uri_pattern,
                "description": f"Access {operation} data",
            }

    logger.info(f"Categorized APIs: {len(tools)} tools, {len(resources)} resources")


def create_fastmcp_server() -> Optional["FastMCP"]:
    """
    Create and configure FastMCP server with dynamically registered APIs.

    This function is the primary MCP server factory that orchestrates the complete
    server setup process. It transforms boto3 operations into MCP-compliant tools
    and resources through a sophisticated registration pipeline.

    MCP Registration Process:
    1. Initialize API discovery to get all 113 operations
    2. Create FastMCP server instance for protocol handling
    3. Generate type-safe functions for each operation (prevents SSE errors)
    4. Register 61 tools for action operations (Create, Update, Delete, etc.)
    5. Register 52 resources for data operations (Get, List, Search, etc.)

    Critical Success Patterns:
    - Type-safe function generation prevents parameter mismatch errors
    - Proper snake_case naming ensures FastMCP compatibility
    - URI pattern matching enables MCP resource templates
    - Comprehensive error handling prevents SSE connection failures

    MCP Protocol Compliance:
    - Tools: Enable AI assistants to perform AWS Deadline Cloud actions
    - Resources: Provide structured access to AWS Deadline Cloud data
    - Parameter schemas: Ensure proper MCP message validation
    - Error handling: Return JSON-serializable responses for all operations

    Returns:
        FastMCP server instance ready for stdio transport, or None if FastMCP unavailable

    Raises:
        ImportError: If FastMCP is not installed (requires 'deadline[mcp]' extras)
    """
    if FastMCP is None:
        raise ImportError(
            "FastMCP is required for MCP server functionality. "
            "Install with: pip install 'deadline[mcp]'"
        )

    # Initialize client and APIs
    _initialize_client_and_apis()

    # Create FastMCP server
    mcp = FastMCP("Deadline Cloud")

    # Dynamically create and register tool functions
    for tool_name, tool_def in tools.items():
        # Create a function for this specific tool
        # Create function with proper typed parameters
        tool_func = _create_function_with_typed_params(
            tool_name, tool_def["schema"], is_resource=False
        )

        # Set proper function name and docstring
        tool_func.__name__ = f"deadline_{_convert_to_snake_case(tool_name)}"
        tool_func.__doc__ = tool_def["description"]
        decorated_func = mcp.tool(description=tool_def["description"])(tool_func)

        logger.debug(f"Registered tool: {tool_name}")

    # Dynamically create and register resource functions
    for resource_name, resource_def in resources.items():
        # Search operations are now properly handled with explicit URI mappings in ResourceURIMapper

        # Create function with proper typed parameters
        resource_func = _create_function_with_typed_params(
            resource_name, extract_parameter_schema(client, resource_name), is_resource=True
        )

        # Set proper function name and docstring
        resource_func.__name__ = f"deadline_resource_{_convert_to_snake_case(resource_name)}"
        resource_func.__doc__ = resource_def["description"]

        try:
            # Apply decorator
            decorated_func = mcp.resource(
                resource_def["uri"], description=resource_def["description"]
            )(resource_func)
            logger.debug(f"Registered resource: {resource_name} -> {resource_def['uri']}")
        except Exception as e:
            logger.error(f"Failed to register resource {resource_name}: {str(e)}")

    logger.info(f"FastMCP server created with {len(tools)} tools and {len(resources)} resources")
    return mcp


class DeadlineCloudMCPServer:
    """
    Legacy class maintained for backward compatibility.

    The actual MCP server functionality is now handled by FastMCP.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the server with immediate client creation and API discovery."""
        self.config = config or {}
        _initialize_client_and_apis()

        # Store references for compatibility
        self.client = client
        self.operations = operations
        self.tools = tools
        self.resources = resources


def create_deadline_mcp_server(config: Optional[Dict[str, Any]] = None) -> DeadlineCloudMCPServer:
    """Create and return a Deadline Cloud MCP server instance."""
    return DeadlineCloudMCPServer(config)


def main():
    """Main entry point for the deadline-mcp console script."""
    import argparse
    import asyncio

    # Parse arguments
    parser = argparse.ArgumentParser(description="Deadline Cloud MCP Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--transport", choices=["stdio"], default="stdio", help="Transport type")
    args = parser.parse_args()

    # Set up logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        if args.transport == "stdio":
            # Create and run FastMCP server
            mcp_server = create_fastmcp_server()
            logger.info("Starting Deadline Cloud MCP Server with stdio transport")
            # FastMCP run method may not return a coroutine, call it directly
            mcp_server.run("stdio")
        else:
            # Fallback: print info and exit (for manual testing)
            _initialize_client_and_apis()
            print(f"Deadline Cloud MCP Server initialized successfully!")
            print(f"Discovered {len(operations)} operations:")
            print(f"  - Tools: {len(tools)}")
            print(f"  - Resources: {len(resources)}")
            print("\nServer is ready for MCP Inspector testing.")
            print("Use: npx @modelcontextprotocol/inspector deadline-mcp")

    except ImportError as e:
        logger.error(f"Import error: {e}")
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error starting Deadline Cloud MCP Server: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
