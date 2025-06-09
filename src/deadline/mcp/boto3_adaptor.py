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
        # All operations now use dynamic pattern generation
        # Fallback to original logic for unknown operations
        return cls._infer_pattern_fallback(operation_name)

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

        # All explicit mappings removed - use fallback parsing only
        # Fallback for simple patterns
        return cls._parse_fallback(path)

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
    def _infer_pattern_fallback(cls, operation_name: str) -> str:
        """
        Fallback logic for operations not in explicit mappings.

        Note: This creates generic patterns. For proper parameter matching,
        use get_uri_pattern_with_schema() instead.

        Args:
            operation_name: The operation name

        Returns:
            str: Inferred URI pattern
        """
        # Extract potential resource name from operation
        resource_match = re.search(r"(Get|List|Describe)(.+)", operation_name)
        if resource_match:
            resource_name = resource_match.group(2)
            # Convert PascalCase to kebab-case for better URI readability
            kebab_name = _convert_to_kebab_case(resource_name)
            if operation_name.startswith("List"):
                # Avoid double 's' if resource name already ends with 's'
                if kebab_name.endswith("s"):
                    return f"deadline://{kebab_name}"
                else:
                    return f"deadline://{kebab_name}s"
            else:
                return f"deadline://{kebab_name}/{{id}}"

        # Final fallback
        return "deadline://unknown/{id}"

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

    @classmethod
    def _parse_fallback(cls, path: str) -> tuple[str, Dict[str, Any]]:
        """
        Fallback parsing for simple patterns.

        Args:
            path: The URI path to parse

        Returns:
            tuple[str, Dict[str, Any]]: (operation_name, parameters)
        """
        parts = path.split("/")

        if len(parts) == 1:
            # List operation, e.g., "farms" -> "ListFarms"
            resource_type = parts[0]
            if resource_type == "farms":
                return ("ListFarms", {})
            elif resource_type == "queues":
                return ("ListQueues", {})
            elif resource_type == "jobs":
                return ("ListJobs", {})
        elif len(parts) == 2:
            # Get operation, e.g., "farm/farm-123" -> "GetFarm"
            resource_type, resource_id = parts
            if resource_type == "farm":
                return ("GetFarm", {"farmId": resource_id})
            elif resource_type == "queue":
                return ("GetQueue", {"queueId": resource_id})
            elif resource_type == "job":
                return ("GetJob", {"jobId": resource_id})

        raise ValueError(f"Cannot parse URI path: {path}")


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


def extract_parameter_schema(
    operation_model_or_client, operation_name: str = None
) -> Dict[str, Any]:
    """
    Extract JSON schema for parameters from a boto3 operation.

    Args:
        operation_model_or_client: Either a boto3 client or an operation model
        operation_name: The name of the operation (required if first arg is client)

    Returns:
        Dict[str, Any]: JSON schema describing the operation parameters
    """
    try:
        # Handle both signatures for backward compatibility with tests
        if hasattr(operation_model_or_client, "_service_model"):
            # This is a client, get the operation model
            client = operation_model_or_client
            if not operation_name:
                return {"type": "object", "properties": {}}

            service_model = client._service_model
            if not hasattr(service_model, "operation_model"):
                return {"type": "object", "properties": {}}

            operation_model = service_model.operation_model(operation_name)
        else:
            # This is already an operation model (test usage)
            operation_model = operation_model_or_client

        if (
            not operation_model
            or not hasattr(operation_model, "input_shape")
            or not operation_model.input_shape
        ):
            return {"type": "object", "properties": {}}

        input_shape = operation_model.input_shape
        if not hasattr(input_shape, "members") or not input_shape.members:
            return {"type": "object", "properties": {}}

        schema = {"type": "object", "properties": {}, "required": []}

        # Get required members from the input shape
        required_members = getattr(input_shape, "required_members", [])

        for param_name, param_shape in input_shape.members.items():
            param_schema = _convert_shape_to_schema(param_shape, visited_shapes=set())
            schema["properties"][param_name] = param_schema

            # Add to required if the parameter is in the required_members list
            if param_name in required_members:
                schema["required"].append(param_name)

        return schema
    except Exception:
        return {"type": "object", "properties": {}}


def _convert_shape_to_schema(shape, visited_shapes=None) -> Dict[str, Any]:
    """
    Convert a boto3 shape to JSON schema format.

    Args:
        shape: The boto3 shape to convert
        visited_shapes: Set to track visited shapes to avoid infinite recursion

    Returns:
        Dict[str, Any]: JSON schema representation of the shape
    """
    # Initialize visited shapes tracking set
    if visited_shapes is None:
        visited_shapes = set()

    # Check for circular references
    shape_name = getattr(shape, "name", None)
    if shape_name is not None and shape_name in visited_shapes:
        # Return a simplified schema to break the recursion
        return {"type": "object", "description": f"Circular reference to {shape_name}"}

    # Add current shape to visited set if it has a name
    if shape_name is not None:
        visited_shapes.add(shape_name)
    if not hasattr(shape, "type_name"):
        return {"type": "string"}

    type_name = shape.type_name

    # Basic type mappings
    type_mapping = {
        "string": "string",
        "integer": "integer",
        "long": "integer",
        "float": "number",
        "double": "number",
        "boolean": "boolean",
        "timestamp": "string",
        "blob": "string",
    }

    if type_name in type_mapping:
        schema = {"type": type_mapping[type_name]}

        # Add description if available
        if hasattr(shape, "documentation") and shape.documentation:
            schema["description"] = shape.documentation

        return schema

    elif type_name == "list":
        schema = {"type": "array"}
        if hasattr(shape, "member"):
            schema["items"] = _convert_shape_to_schema(shape.member, visited_shapes)
        return schema

    elif type_name == "map":
        schema = {"type": "object"}
        if hasattr(shape, "value"):
            schema["additionalProperties"] = _convert_shape_to_schema(shape.value, visited_shapes)
        return schema

    elif type_name == "structure":
        schema = {"type": "object", "properties": {}}
        if hasattr(shape, "members") and shape.members:
            try:
                for member_name, member_shape in shape.members.items():
                    schema["properties"][member_name] = _convert_shape_to_schema(
                        member_shape, visited_shapes
                    )
            except (TypeError, AttributeError):
                # Handle case where members is not iterable (e.g., in tests with mocks)
                pass
        return schema

    else:
        # Unknown type, default to string
        return {"type": "string"}
