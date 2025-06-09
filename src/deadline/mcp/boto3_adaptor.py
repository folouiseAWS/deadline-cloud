"""Boto3 adaptor for AWS Deadline Cloud MCP server."""

import boto3
import re
from inspect import Parameter, Signature
from typing import List, Dict, Any, Tuple, Optional, Callable
from deadline.client.api import get_boto3_client
from deadline.mcp.utils import (
    extract_service_model_parameters,
    map_aws_type_to_python,
    extract_operation_documentation,
)


def discover_deadline_operations(service_model=None) -> List[str]:
    """
    Discover all available deadline operations from boto3 service model.

    Args:
        service_model: Optional service model, if None will create deadline client

    Returns:
        List of operation names
    """
    if service_model is None:
        client = boto3.client("deadline")
        service_model = client._service_model

    return list(service_model.operation_names)


def generate_tool_function(operation_name: str, operation_model) -> Tuple[str, Callable]:
    """
    Generate tool function for a given operation using inspect.Signature.

    Args:
        operation_name: Name of the operation
        operation_model: Boto3 operation model

    Returns:
        Tuple of (function_name, function_object)
    """
    # Convert to snake_case and add deadline prefix
    func_name = f"deadline_{camel_to_snake(operation_name)}"

    # Extract parameters and create signature
    params = extract_service_model_parameters(operation_model)
    parameters = []

    # Create Parameter objects for required parameters first
    for param_name, param_info in params.items():
        if param_info["required"]:
            # Use shape for recursive type resolution
            param_type = map_aws_type_to_python(param_info["type"], param_info.get("shape"))
            parameters.append(
                Parameter(param_name, Parameter.POSITIONAL_OR_KEYWORD, annotation=param_type)
            )

    # Then optional parameters
    for param_name, param_info in params.items():
        if not param_info["required"]:
            # Use shape for recursive type resolution
            param_type = map_aws_type_to_python(param_info["type"], param_info.get("shape"))
            parameters.append(
                Parameter(
                    param_name,
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=Optional[param_type],
                    default=None,
                )
            )

    # Create signature
    sig = Signature(parameters)

    # Extract documentation
    doc = extract_operation_documentation(operation_model)

    # Create function with closure (no exec/eval needed)
    def create_tool_function():
        snake_operation = camel_to_snake(operation_name)

        def tool_func(**kwargs):
            # Filter None values explicitly without using **kwargs in signature
            filtered_params = {k: v for k, v in kwargs.items() if v is not None}
            return execute_deadline_operation(snake_operation, filtered_params)

        # Set proper signature and annotations for FastMCP/Pydantic
        tool_func.__signature__ = sig  # type: ignore[attr-defined]
        tool_func.__annotations__ = {p.name: p.annotation for p in sig.parameters.values()}
        tool_func.__doc__ = doc
        tool_func.__name__ = func_name

        return tool_func

    return func_name, create_tool_function()


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    # Insert underscore before uppercase letters (except the first one)
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    # Insert underscore before uppercase letters that follow lowercase letters
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def create_tool_registry() -> Dict[str, Callable]:
    """
    Create complete tool registry for fastmcp.

    Returns:
        Dictionary of tool functions
    """
    client = boto3.client("deadline")
    service_model = client._service_model

    registry = {}

    for operation_name in service_model.operation_names:
        try:
            operation_model = service_model.operation_model(operation_name)
            func_name, func_obj = generate_tool_function(operation_name, operation_model)
            registry[func_name] = func_obj
        except Exception:
            # Skip operations that fail to process
            continue

    return registry


def execute_deadline_operation(operation_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a deadline operation with the given parameters.

    Args:
        operation_name: Name of the operation in snake_case
        params: Operation parameters (already filtered)

    Returns:
        Operation response
    """
    # Get authenticated client
    client = get_boto3_client("deadline")

    # Get the method from client
    method = getattr(client, operation_name)

    # Execute the operation with explicit parameters
    return method(**params)
