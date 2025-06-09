"""Utility functions for MCP server implementation."""

import re
from datetime import datetime
from typing import Dict, Any, List, Type, Optional, Set


def extract_service_model_parameters(operation_model) -> Dict[str, Dict[str, Any]]:
    """
    Extract parameters from boto3 service model operation.

    Args:
        operation_model: Boto3 operation model

    Returns:
        Dictionary of parameter information
    """
    if not hasattr(operation_model, "input_shape") or operation_model.input_shape is None:
        return {}

    input_shape = operation_model.input_shape
    if not hasattr(input_shape, "members"):
        return {}

    params = {}
    required_members = getattr(input_shape, "required_members", [])

    for param_name, param_shape in input_shape.members.items():
        params[param_name] = {
            "type": param_shape.type_name,
            "shape": param_shape,  # Pass shape for recursive type resolution
            "required": param_name in required_members,
            "documentation": getattr(param_shape, "documentation", f"Parameter {param_name}"),
        }

    return params


def map_aws_type_to_python(aws_type: str, shape=None, visited: Optional[Set[int]] = None) -> Type:
    """
    Map AWS service model types to Python types with recursive support.

    Args:
        aws_type: AWS type name
        shape: Optional boto3 shape object for complex types
        visited: Set of visited shape IDs to prevent circular references

    Returns:
        Python type
    """
    if visited is None:
        visited = set()

    # Circular reference detection
    if shape and id(shape) in visited:
        return Any
    if shape:
        visited.add(id(shape))

    # Basic type mapping
    basic_mapping = {
        "string": str,
        "integer": int,
        "long": int,
        "boolean": bool,
        "float": float,
        "double": float,
        "timestamp": datetime,
        "blob": bytes,
    }

    if aws_type in basic_mapping:
        return basic_mapping[aws_type]

    # Complex recursive types
    if aws_type == "structure":
        # For structures, return Dict[str, Any] (we could create TypedDict classes but that's complex)
        return Dict[str, Any]

    elif aws_type == "list":
        if shape and hasattr(shape, "member"):
            # Get the item type recursively
            item_type = map_aws_type_to_python(shape.member.type_name, shape.member, visited.copy())
            return List[item_type]  # type: ignore[valid-type]
        else:
            # No member information, fall back to Any
            return List[Any]

    elif aws_type == "map":
        if shape and hasattr(shape, "value"):
            # Get the value type recursively (key is always string for AWS maps)
            value_type = map_aws_type_to_python(shape.value.type_name, shape.value, visited.copy())
            return Dict[str, value_type]  # type: ignore[valid-type]
        else:
            # No value information, fall back to Any
            return Dict[str, Any]

    # Default fallback
    return Any


def generate_typed_signature(params: Dict[str, Dict[str, Any]]) -> List[str]:
    """
    Generate typed function signature parts from parameters.

    Args:
        params: Parameter dictionary from extract_service_model_parameters

    Returns:
        List of signature parts
    """
    if not params:
        return []

    required_params = []
    optional_params = []

    for param_name, param_info in params.items():
        # Use shape for recursive type resolution
        python_type = map_aws_type_to_python(param_info["type"], param_info.get("shape"))
        type_name = python_type.__name__ if python_type != Any else "Any"

        if param_info["required"]:
            required_params.append(f"{param_name}: {type_name}")
        else:
            optional_params.append(f"{param_name}: Optional[{type_name}] = None")

    # Required parameters come first, then optional
    return required_params + optional_params


def strip_html_tags(text: Optional[str]) -> Optional[str]:
    """
    Remove HTML tags from text while preserving content.

    Args:
        text: Text potentially containing HTML tags

    Returns:
        Clean text with HTML tags removed
    """
    if not text:
        return text

    # Remove HTML tags but keep the content
    clean_text = re.sub(r"<[^>]+>", "", text)
    # Clean up extra whitespace and normalize
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text


def extract_operation_documentation(operation_model) -> str:
    """
    Extract and clean documentation from operation model.

    Args:
        operation_model: Boto3 operation model

    Returns:
        Clean documentation string with HTML tags removed
    """
    if hasattr(operation_model, "documentation") and operation_model.documentation:
        raw_doc = operation_model.documentation
        cleaned_doc = strip_html_tags(raw_doc)
        return cleaned_doc or "No documentation available"

    # Fallback to generic documentation
    operation_name = getattr(operation_model, "name", "Unknown")
    return f"Execute {operation_name} operation"
