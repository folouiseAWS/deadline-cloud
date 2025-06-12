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
    ResourceURIMapper,
)
from deadline.mcp.parameter_extractor import DynamicParameterExtractor
from deadline.mcp.function_builder import MCPFunctionBuilder
from deadline.mcp.utils import NameConverter

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

# Global logger
logger = logging.getLogger(__name__)

# Global parameter extractor
parameter_extractor = DynamicParameterExtractor()


def get_boto3_client():
    """
    Create and return a boto3 client for AWS Deadline Cloud.

    Returns:
        boto3.client: Configured Deadline Cloud client
    """
    return boto3.client("deadline")


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
            schema = parameter_extractor.extract_parameter_schema(client, operation_name)

            # Build function using existing sophisticated logic
            func = function_builder.build_function(
                operation_name, schema, client, is_resource=(category == "resource")
            )

            if category == "tool":
                # Set proper function metadata
                func.__name__ = f"deadline_{NameConverter.to_snake_case(operation_name)}"
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
                func.__name__ = f"deadline_resource_{NameConverter.to_snake_case(operation_name)}"
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
            print("Only stdio transport is supported.")
            sys.exit(1)

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
