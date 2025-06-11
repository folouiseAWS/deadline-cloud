"""
AWS Deadline Cloud MCP Server implementation.

FastMCP-based server that dynamically discovers and exposes Deadline Cloud APIs.
"""

from typing import Dict, Any, List, Optional, Tuple
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

    # Reset global state for fresh initialization (important for testing)
    # Comment out the early return to allow re-initialization

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


def auto_register_mcp_operations(mcp_server: "FastMCP", client) -> Tuple[int, int]:
    """
    Automatically register all AWS Deadline Cloud operations using decorator pattern.

    This function provides a clean, maintainable approach to registering all 113 operations
    by leveraging proper decorator application instead of manual loops. It preserves all
    existing functionality while dramatically improving code maintainability.

    Registration Process:
    1. Discover all available AWS operations through introspection
    2. Categorize each operation as tool (action) or resource (data access)
    3. Build type-safe functions using existing MCPFunctionBuilder logic
    4. Apply MCP decorators naturally for each operation type
    5. Handle edge cases and skip problematic operations gracefully

    Args:
        mcp_server: FastMCP server instance to register operations with
        client: boto3 Deadline Cloud client for operation discovery

    Returns:
        Tuple of (registered_tools_count, registered_resources_count)
    """
    operations = discover_apis(client)
    function_builder = MCPFunctionBuilder()

    registered_tools = 0
    registered_resources = 0

    for operation_name in operations:
        try:
            category = categorize_api(operation_name)
            schema = extract_parameter_schema(client, operation_name)

            # Build function using existing sophisticated logic
            func = function_builder.build_function(
                operation_name, schema, client, is_resource=(category == "resource")
            )

            if category == "tool":
                # Set proper function metadata
                func.__name__ = f"deadline_{_convert_to_snake_case(operation_name)}"
                func.__doc__ = f"Execute {operation_name} operation"

                # Apply tool decorator
                mcp_server.tool(description=f"Execute {operation_name}")(func)
                registered_tools += 1
                logger.debug(f"Registered tool: {operation_name}")

            elif category == "resource":
                # Generate URI pattern
                uri_pattern = ResourceURIMapper.get_uri_pattern_with_schema(operation_name, schema)

                # Check for problematic resource operations (preserve existing logic)
                import re

                uri_params = set(re.findall(r"\{(\w+)\}", uri_pattern))
                properties = schema.get("properties", {})

                if uri_params and not properties:
                    logger.warning(
                        f"Skipping resource registration for {operation_name} - "
                        f"has URI params {uri_params} but no properties"
                    )
                    continue

                # Set proper function metadata
                func.__name__ = f"deadline_resource_{_convert_to_snake_case(operation_name)}"
                func.__doc__ = f"Access {operation_name} data"

                # Apply resource decorator
                mcp_server.resource(uri_pattern, description=f"Access {operation_name} data")(func)
                registered_resources += 1
                logger.debug(f"Registered resource: {operation_name} -> {uri_pattern}")

        except Exception as e:
            logger.error(f"Failed to register operation {operation_name}: {str(e)}")
            continue

    logger.info(f"Auto-registered {registered_tools} tools and {registered_resources} resources")
    return registered_tools, registered_resources


def create_fastmcp_server() -> Optional["FastMCP"]:
    """
    Create and configure FastMCP server with dynamically registered APIs.

    This function is the primary MCP server factory that orchestrates the complete
    server setup process. It transforms boto3 operations into MCP-compliant tools
    and resources through a clean decorator-based registration system.

    MCP Registration Process:
    1. Initialize API discovery to get all 113 operations
    2. Create FastMCP server instance for protocol handling
    3. Auto-register all operations using decorator pattern
    4. Generate type-safe functions for each operation (prevents SSE errors)
    5. Register ~61 tools for action operations (Create, Update, Delete, etc.)
    6. Register ~52 resources for data operations (Get, List, Search, etc.)

    Critical Success Patterns:
    - Decorator-based registration for better maintainability
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

    # Initialize client for operation discovery
    global client
    client = get_boto3_client()
    logger.info("boto3 client created successfully")

    # Create FastMCP server
    mcp = FastMCP("Deadline Cloud")

    # Auto-register all operations using clean decorator pattern
    tools_count, resources_count = auto_register_mcp_operations(mcp, client)

    logger.info(f"FastMCP server created with {tools_count} tools and {resources_count} resources")
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
