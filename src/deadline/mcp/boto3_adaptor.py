"""
boto3 adaptor for the Deadline Cloud MCP Server.

Provides API discovery, categorization, and parameter schema extraction
from boto3 clients for automatic MCP tool and resource generation.
"""

import re
from typing import List, Dict, Any, Optional, Union
from botocore.model import OperationModel
from deadline.mcp.uri_pattern_generator import DynamicURIPatternGenerator


def _convert_to_kebab_case(name: str) -> str:
    """Convert PascalCase to kebab-case.

    Args:
        name: PascalCase string (e.g., 'QueueFleetAssociations')

    Returns:
        str: kebab-case string (e.g., 'queue-fleet-associations')
    """
    # Insert hyphens before capital letters (except the first one)
    result = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    return result.lower()


class ResourceURIMapper:
    """
    Unified mapper for MCP resource URIs.

    Handles both creating URI patterns from operations and parsing URIs back to operations.
    This eliminates duplication between pattern creation and parsing logic.
    """

    # NOTE: All explicit mappings removed - now using dynamic URI pattern generation
    # The DynamicURIPatternGenerator handles all operations automatically

    @classmethod
    def get_uri_pattern(cls, operation_name: str) -> str:
        """
        Get the URI pattern for a given operation.

        Args:
            operation_name: The name of the boto3 operation

        Returns:
            str: The URI pattern for the resource
        """
        # All operations must use proper schema-based generation
        # No fallbacks allowed per .clinerules
        raise ValueError(
            f"get_uri_pattern() requires schema - use get_uri_pattern_with_schema() for {operation_name}"
        )

    @classmethod
    def parse_uri(cls, uri: str) -> tuple[str, Dict[str, Any]]:
        """
        Parse a resource URI back to operation name and parameters.

        Args:
            uri: The resource URI to parse

        Returns:
            tuple[str, Dict[str, Any]]: (operation_name, parameters)
        """
        if not uri.startswith("deadline://"):
            raise ValueError(f"Invalid resource URI: {uri}")

        path = uri[11:]  # Remove "deadline://"

        # No fallbacks allowed per .clinerules - parsing not supported yet
        # URI parsing should be implemented properly with schema-based matching
        raise NotImplementedError(f"URI parsing not implemented - received path: {path}")

    @classmethod
    def _match_pattern(cls, path: str, pattern: str) -> Optional[Dict[str, str]]:
        """
        Match a path against a pattern with {param} placeholders.

        Args:
            path: The actual path to match
            pattern: The pattern with {param} placeholders

        Returns:
            Optional[Dict[str, str]]: Parameters if match, None otherwise
        """
        # Convert pattern to regex
        regex_pattern = re.escape(pattern)
        regex_pattern = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", regex_pattern)
        regex_pattern = f"^{regex_pattern}$"

        match = re.match(regex_pattern, path)
        if match:
            return match.groupdict()
        return None

    @classmethod
    def get_uri_pattern_with_schema(cls, operation_name: str, schema: Dict[str, Any]) -> str:
        """
        Get URI pattern for operation using parameter schema to ensure parameter matching.

        Args:
            operation_name: The operation name
            schema: Parameter schema from extract_parameter_schema

        Returns:
            str: URI pattern with parameters matching the schema
        """
        # All operations now use dynamic URI pattern generator
        # Use dynamic URI pattern generator for all operations
        generator = DynamicURIPatternGenerator()
        return generator.generate_pattern(operation_name, schema)


def discover_apis(client) -> List[str]:
    """
    Discover all available API operations from a boto3 client for MCP exposure.

    This function is the foundation of the MCP server's dynamic API discovery system.
    It introspects the boto3 Deadline Cloud client to automatically find all available
    operations, enabling the MCP server to expose AWS APIs without manual configuration.

    MCP Discovery Process:
    1. Access the client's service model through boto3 introspection
    2. Extract all operation names from the service model
    3. Return the complete list for MCP categorization and registration

    This approach enables:
    - Automatic exposure of new AWS APIs as they're added to boto3
    - No manual maintenance of operation lists
    - Consistent discovery across different AWS service versions
    - Dynamic MCP server configuration based on available APIs

    MCP Protocol Impact:
    - Discovered operations become MCP tools (actions) or resources (data access)
    - Each operation gets its own MCP function with proper parameter schemas
    - Operation names are used for MCP function naming and URI pattern generation
    - The complete list enables comprehensive AWS Deadline Cloud coverage

    Args:
        client: The boto3 Deadline Cloud client to introspect

    Returns:
        List[str]: List of operation names available in the client (typically 113 operations)

    Example:
        >>> client = boto3.client('deadline')
        >>> ops = discover_apis(client)
        >>> len(ops)  # Returns 113 for current Deadline Cloud API
        113
        >>> 'GetFarm' in ops
        True
    """
    try:
        if not hasattr(client, "_service_model"):
            return []

        service_model = client._service_model
        if not hasattr(service_model, "operation_names"):
            return []

        return list(service_model.operation_names)
    except (AttributeError, TypeError):
        return []


def categorize_api(operation_name: str) -> str:
    """
    Categorize a boto3 operation as either a 'tool' or 'resource'.

    Tools are operations that perform actions (Create, Update, Delete, etc.)
    Resources are operations that retrieve data (Get, List, Describe, etc.)

    Args:
        operation_name: The name of the boto3 operation

    Returns:
        str: Either 'tool' or 'resource'
    """
    # Resource operations (read-only)
    resource_prefixes = ["Get", "List", "Describe", "Search", "Query", "Scan"]

    # Tool operations (actions)
    tool_prefixes = [
        "Create",
        "Update",
        "Delete",
        "Put",
        "Post",
        "Patch",
        "Start",
        "Stop",
        "Cancel",
        "Pause",
        "Resume",
        "Restart",
        "Associate",
        "Disassociate",
        "Attach",
        "Detach",
        "Enable",
        "Disable",
        "Activate",
        "Deactivate",
        "Add",
        "Remove",
        "Set",
        "Reset",
        "Clear",
        "Send",
        "Publish",
        "Subscribe",
        "Unsubscribe",
        "Assume",  # For assume_queue_role_for_user, assume_queue_role_for_read
        "Batch",  # For batch operations
        "Copy",  # For copy operations
        "Tag",  # For tagging resources
        "Untag",  # For removing tags
        "Monitor",  # For monitoring operations
    ]

    # Check for resource patterns first
    for prefix in resource_prefixes:
        if operation_name.startswith(prefix):
            return "resource"

    # Check for tool patterns
    for prefix in tool_prefixes:
        if operation_name.startswith(prefix):
            return "tool"

    # Default to tool for unknown patterns
    return "tool"
