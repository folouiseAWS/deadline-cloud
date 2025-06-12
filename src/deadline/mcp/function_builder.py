"""
MCP Function Builder for Deadline Cloud MCP Server.

Provides modular, testable components for building MCP tool and resource functions.
Replaces the monolithic function creation logic with composable components.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
import logging
import inspect
import re
from deadline.mcp.boto3_adaptor import ResourceURIMapper
from deadline.mcp.parameter_classifier import DynamicParameterClassifier
from deadline.mcp.utils import NameConverter

logger = logging.getLogger(__name__)


class ParameterProcessor:
    """Handles parameter filtering, exclusion, and mapping logic."""

    def __init__(self):
        self.classifier = DynamicParameterClassifier()

    def process_parameters(
        self, operation_name: str, schema: Dict[str, Any], is_resource: bool = False
    ) -> Tuple[Dict[str, Any], Set[str], Dict[str, str]]:
        """
        Process operation parameters for MCP function creation.

        Args:
            operation_name: Name of the AWS operation
            schema: Parameter schema from extract_parameter_schema
            is_resource: Whether this is a resource (vs tool) function

        Returns:
            Tuple of (filtered_properties, required_params, param_mapping)
        """
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if is_resource:
            excluded_params = self._get_resource_exclusions(operation_name, schema)
        else:
            excluded_params = self._get_tool_exclusions(operation_name)

        # Filter out excluded parameters
        filtered_properties = {k: v for k, v in properties.items() if k not in excluded_params}
        filtered_required = {r for r in required if r not in excluded_params}

        # Create parameter mapping (snake_case -> camelCase)
        param_mapping = {}
        for param_name in filtered_properties.keys():
            snake_name = NameConverter.to_snake_case(param_name)
            param_mapping[snake_name] = param_name

        return filtered_properties, filtered_required, param_mapping

    def _get_resource_exclusions(self, operation_name: str, schema: Dict[str, Any]) -> Set[str]:
        """Get parameter exclusions for resource functions."""
        properties = schema.get("properties", {})

        # Get URI parameters that must be preserved
        uri_pattern = ResourceURIMapper.get_uri_pattern_with_schema(operation_name, schema)
        uri_params = set(re.findall(r"\{(\w+)\}", uri_pattern))

        # Convert snake_case URI params back to camelCase API params
        uri_api_params = set()
        for uri_param in uri_params:
            # Convert snake_case to camelCase
            words = uri_param.split("_")
            if len(words) == 1:
                camel_param = words[0]
            else:
                camel_param = words[0] + "".join(word.capitalize() for word in words[1:])

            # Special handling for common parameter mappings
            if camel_param == "id":
                potential_params = ["id", "resourceArn", "resourceId", "entityId"]
                for potential in potential_params:
                    if potential in properties:
                        camel_param = potential
                        break

            uri_api_params.add(camel_param)

        # Log debug info
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Operation: {operation_name}")
            logger.debug(f"URI pattern: {uri_pattern}")
            logger.debug(f"URI params: {uri_params}")
            logger.debug(f"API params: {uri_api_params}")
            logger.debug(f"Available properties: {set(properties.keys())}")

        # Handle edge case: no properties available
        if not properties and uri_api_params:
            logger.warning(
                f"Operation {operation_name} has URI params {uri_api_params} but no properties"
            )
            return set()  # Don't exclude anything if there's nothing to exclude

        # Always exclude principalId from resource functions - it's handled automatically
        base_exclusions = {"principalId"}

        # Determine exclusions based on operation type
        if operation_name.startswith(("List", "Search", "Query")):
            if not uri_api_params:
                # No URI parameters = exclude everything for MCP resources
                return set(properties.keys())
            else:
                # Use pattern-based classification but preserve URI parameters
                excluded_params = set()
                for param_name in properties.keys():
                    if not self.classifier.should_include_in_function_signature(
                        param_name, operation_name, has_uri_params=True
                    ):
                        excluded_params.add(param_name)
                return excluded_params.union(base_exclusions) - uri_api_params
        else:
            # Get/Describe operations: exclude only pagination parameters and principalId
            return base_exclusions.union(
                {
                    "nextToken",
                    "maxResults",
                    "maxItems",
                    "pageSize",
                    "limit",
                    "offset",
                    "marker",
                    "continuationToken",
                    "startToken",
                }
            )

    def _get_tool_exclusions(self, operation_name: str) -> Set[str]:
        """Get parameter exclusions for tool functions."""
        # Tools don't exclude parameters - they need all parameters for actions
        return set()


class FunctionSignatureBuilder:
    """Builds function signatures with proper typing and parameter ordering."""

    def build_signature(
        self, param_mapping: Dict[str, str], required_params: Set[str]
    ) -> inspect.Signature:
        """
        Build a function signature from parameter mapping.

        Args:
            param_mapping: Mapping from snake_case to camelCase parameter names
            required_params: Set of required parameter names (camelCase)

        Returns:
            inspect.Signature object
        """
        required_snake_params = []
        optional_snake_params = []

        for snake_name, camel_name in param_mapping.items():
            is_required = camel_name in required_params
            default_value = inspect.Parameter.empty if is_required else None

            param = inspect.Parameter(
                snake_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=str,  # All AWS API parameters are strings for simplicity
                default=default_value,
            )

            if is_required:
                required_snake_params.append(param)
            else:
                optional_snake_params.append(param)

        # Combine parameters - required first, then optional
        all_params = required_snake_params + optional_snake_params
        return inspect.Signature(all_params)


class FunctionWrapperBuilder:
    """Creates function wrappers with proper error handling and execution logic."""

    def build_wrapper(
        self,
        operation_name: str,
        signature: inspect.Signature,
        param_mapping: Dict[str, str],
        client: Any,
        is_resource: bool = False,
    ) -> Any:
        """
        Build a function wrapper for the given operation.

        Args:
            operation_name: Name of the AWS operation
            signature: Function signature to use
            param_mapping: Parameter mapping (snake_case -> camelCase)
            client: boto3 client instance
            is_resource: Whether this is a resource function

        Returns:
            Async function wrapper
        """

        async def wrapper(*args, **kwargs) -> Dict[str, Any]:
            """Safe wrapper that always returns valid JSON-serializable data."""
            try:
                # Bind arguments to signature
                try:
                    bound_args = signature.bind(*args, **kwargs)
                    bound_args.apply_defaults()
                except TypeError as e:
                    logger.warning(f"Parameter binding failed for {operation_name}: {str(e)}")
                    return {
                        "error": "Parameter binding failed",
                        "operation": operation_name,
                        "message": str(e),
                    }

                # Convert to API kwargs
                api_kwargs = {}
                for param_name, value in bound_args.arguments.items():
                    if value is not None and param_name in param_mapping:
                        original_name = param_mapping[param_name]
                        api_kwargs[original_name] = value

                # Auto-inject principalId for List operations (like client API does)
                if (
                    operation_name.startswith(("List", "Search", "Query"))
                    and "principalId" not in api_kwargs
                ):
                    try:
                        # Import here to avoid circular dependencies
                        from deadline.client.api._session import get_user_and_identity_store_id

                        user_id, _ = get_user_and_identity_store_id()
                        if user_id:
                            api_kwargs["principalId"] = user_id
                    except (ImportError, Exception):
                        # If we can't get user ID, continue without it
                        # The API call may still work depending on permissions
                        pass

                # Execute the operation
                method_name = NameConverter.to_snake_case(operation_name)
                try:
                    method = getattr(client, method_name)
                except AttributeError as e:
                    logger.error(f"Method {method_name} not found for {operation_name}: {str(e)}")
                    return {
                        "error": "Method not found",
                        "operation": operation_name,
                        "method": method_name,
                    }

                try:
                    result = method(**api_kwargs)
                    # Ensure result is JSON-serializable
                    if result is None:
                        return {"result": None, "operation": operation_name}
                    elif isinstance(result, dict):
                        return result
                    else:
                        # Convert non-dict results to dict format
                        return {"data": str(result), "operation": operation_name}
                except Exception as e:
                    logger.warning(f"API error in {operation_name}: {str(e)}")
                    return {
                        "error": "API call failed",
                        "operation": operation_name,
                        "message": str(e),
                    }

            except Exception as e:
                logger.error(f"Unexpected error executing {operation_name}: {str(e)}")
                return {"error": "Unexpected error", "operation": operation_name, "message": str(e)}

        # Set function metadata
        func_type = "resource" if is_resource else "tool"
        wrapper.__name__ = f"{NameConverter.to_snake_case(operation_name)}_function"
        wrapper.__doc__ = f"Dynamically created {func_type} function for {operation_name}"
        wrapper.__signature__ = signature
        wrapper.__annotations__ = {"return": Dict[str, Any]}

        # Set parameter annotations
        for param in signature.parameters.values():
            wrapper.__annotations__[param.name] = param.annotation

        return wrapper


class MCPFunctionBuilder:
    """
    Main builder class that orchestrates MCP function creation.

    Replaces the monolithic _create_function_with_typed_params() function
    with modular, testable components.
    """

    def __init__(self):
        self.parameter_processor = ParameterProcessor()
        self.signature_builder = FunctionSignatureBuilder()
        self.wrapper_builder = FunctionWrapperBuilder()

    def build_function(
        self, operation_name: str, schema: Dict[str, Any], client: Any, is_resource: bool = False
    ) -> Any:
        """
        Build a complete MCP function for the given operation.

        Args:
            operation_name: Name of the AWS operation
            schema: Parameter schema from extract_parameter_schema
            client: boto3 client instance
            is_resource: Whether this is a resource (vs tool) function

        Returns:
            Configured async function ready for MCP registration
        """
        # Step 1: Process parameters
        properties, required, param_mapping = self.parameter_processor.process_parameters(
            operation_name, schema, is_resource
        )

        # Step 2: Handle edge cases
        if not properties and is_resource:
            # Check if this operation has URI parameters but no available properties
            uri_pattern = ResourceURIMapper.get_uri_pattern_with_schema(operation_name, schema)
            uri_params = set(re.findall(r"\{(\w+)\}", uri_pattern))

            if uri_params:
                logger.warning(
                    f"Creating safe function for {operation_name} - "
                    f"has URI params {uri_params} but no properties"
                )

                async def safe_function(**kwargs) -> Dict[str, Any]:
                    """Safe function that returns empty result for operations with no parameters."""
                    logger.info(
                        f"Operation {operation_name} called but has no available parameters"
                    )
                    return {"result": "No data available", "operation": operation_name}

                safe_function.__name__ = f"{NameConverter.to_snake_case(operation_name)}_safe"
                safe_function.__doc__ = (
                    f"Safe function for {operation_name} (no parameters available)"
                )
                return safe_function

        # Step 3: Build function signature
        signature = self.signature_builder.build_signature(param_mapping, required)

        # Step 4: Build function wrapper
        wrapper = self.wrapper_builder.build_wrapper(
            operation_name, signature, param_mapping, client, is_resource
        )

        return wrapper
