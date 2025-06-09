"""
Dynamic Parameter Extractor for Deadline Cloud MCP Server.

Consolidates all parameter extraction, mapping, and validation logic
into a unified, testable component. Handles boto3 shape conversion,
parameter type mapping, and name normalization.
"""

import re
from typing import Dict, Any, Set, List, Optional, Union, Tuple
from botocore.model import OperationModel


class ParameterTypeConverter:
    """Converts boto3 shapes to JSON schema format with intelligent type mapping."""

    def __init__(self):
        self.basic_type_mapping = {
            "string": "string",
            "integer": "integer",
            "long": "integer",
            "float": "number",
            "double": "number",
            "boolean": "boolean",
            "timestamp": "string",
            "blob": "string",
        }

    def convert_shape_to_schema(
        self, shape, visited_shapes: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
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

        # Handle basic types
        if type_name in self.basic_type_mapping:
            schema = {"type": self.basic_type_mapping[type_name]}

            # Add description if available
            if hasattr(shape, "documentation") and shape.documentation:
                schema["description"] = shape.documentation

            return schema

        # Handle complex types
        elif type_name == "list":
            schema = {"type": "array"}
            if hasattr(shape, "member"):
                schema["items"] = self.convert_shape_to_schema(shape.member, visited_shapes)
            return schema

        elif type_name == "map":
            schema = {"type": "object"}
            if hasattr(shape, "value"):
                schema["additionalProperties"] = self.convert_shape_to_schema(
                    shape.value, visited_shapes
                )
            return schema

        elif type_name == "structure":
            schema = {"type": "object", "properties": {}}
            if hasattr(shape, "members") and shape.members:
                try:
                    for member_name, member_shape in shape.members.items():
                        schema["properties"][member_name] = self.convert_shape_to_schema(
                            member_shape, visited_shapes
                        )
                except (TypeError, AttributeError):
                    # Handle case where members is not iterable (e.g., in tests with mocks)
                    pass
            return schema

        else:
            # Unknown type, default to string
            return {"type": "string"}


class ParameterNameMapper:
    """Handles parameter name conversions between different naming conventions."""

    @staticmethod
    def to_snake_case(name: str) -> str:
        """Convert PascalCase/camelCase to snake_case.

        Args:
            name: PascalCase or camelCase string

        Returns:
            str: snake_case string
        """
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    @staticmethod
    def to_kebab_case(name: str) -> str:
        """Convert PascalCase to kebab-case.

        Args:
            name: PascalCase string (e.g., 'QueueFleetAssociations')

        Returns:
            str: kebab-case string (e.g., 'queue-fleet-associations')
        """
        # Insert hyphens before capital letters (except the first one)
        result = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
        return result.lower()

    @staticmethod
    def to_camel_case(snake_name: str) -> str:
        """Convert snake_case to camelCase.

        Args:
            snake_name: snake_case string

        Returns:
            str: camelCase string
        """
        words = snake_name.split("_")
        if len(words) == 1:
            return words[0]
        else:
            return words[0] + "".join(word.capitalize() for word in words[1:])

    def create_parameter_mapping(self, properties: Dict[str, Any]) -> Dict[str, str]:
        """Create a mapping from snake_case to original parameter names.

        Args:
            properties: Dictionary of parameter properties

        Returns:
            Dict[str, str]: Mapping from snake_case names to original names
        """
        param_mapping = {}
        for param_name in properties.keys():
            snake_name = self.to_snake_case(param_name)
            param_mapping[snake_name] = param_name
        return param_mapping


class ParameterSchemaExtractor:
    """Extracts parameter schemas from boto3 operations."""

    def __init__(self):
        self.type_converter = ParameterTypeConverter()

    def extract_from_operation(
        self, operation_model_or_client, operation_name: Optional[str] = None
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
                param_schema = self.type_converter.convert_shape_to_schema(param_shape)
                schema["properties"][param_name] = param_schema

                # Add to required if the parameter is in the required_members list
                if param_name in required_members:
                    schema["required"].append(param_name)

            return schema
        except Exception:
            return {"type": "object", "properties": {}}


class ParameterValidator:
    """Validates and normalizes parameters for MCP operations."""

    @staticmethod
    def validate_required_parameters(
        parameters: Dict[str, Any], required: Set[str]
    ) -> Tuple[bool, List[str]]:
        """
        Validate that all required parameters are present.

        Args:
            parameters: Dictionary of provided parameters
            required: Set of required parameter names

        Returns:
            Tuple[bool, List[str]]: (is_valid, missing_parameters)
        """
        missing = []
        for param in required:
            if param not in parameters or parameters[param] is None:
                missing.append(param)

        return len(missing) == 0, missing

    @staticmethod
    def normalize_parameter_values(parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize parameter values for consistent processing.

        Args:
            parameters: Dictionary of parameters to normalize

        Returns:
            Dict[str, Any]: Normalized parameters
        """
        normalized = {}
        for key, value in parameters.items():
            if value is not None:
                # Convert all values to strings for simplicity in MCP context
                if isinstance(value, (list, dict)):
                    normalized[key] = value  # Keep complex types as-is
                else:
                    normalized[key] = str(value)
        return normalized


class DynamicParameterExtractor:
    """
    Unified parameter extraction and management system.

    Consolidates all parameter-related operations into a single,
    testable component with consistent behavior across the MCP server.
    """

    def __init__(self):
        self.schema_extractor = ParameterSchemaExtractor()
        self.name_mapper = ParameterNameMapper()
        self.validator = ParameterValidator()
        self.type_converter = ParameterTypeConverter()

    def extract_parameter_schema(
        self, operation_model_or_client, operation_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract JSON schema for parameters from a boto3 operation.

        This is the main entry point for parameter schema extraction,
        replacing the original extract_parameter_schema function.

        Args:
            operation_model_or_client: Either a boto3 client or an operation model
            operation_name: The name of the operation (required if first arg is client)

        Returns:
            Dict[str, Any]: JSON schema describing the operation parameters
        """
        return self.schema_extractor.extract_from_operation(
            operation_model_or_client, operation_name
        )

    def create_parameter_mapping(self, schema: Dict[str, Any]) -> Dict[str, str]:
        """
        Create parameter name mapping from schema.

        Args:
            schema: Parameter schema from extract_parameter_schema

        Returns:
            Dict[str, str]: Mapping from snake_case to original parameter names
        """
        properties = schema.get("properties", {})
        return self.name_mapper.create_parameter_mapping(properties)

    def extract_parameter_info(
        self, operation_model_or_client, operation_name: Optional[str] = None
    ) -> Tuple[Dict[str, Any], Set[str], Dict[str, str]]:
        """
        Extract complete parameter information for an operation.

        Args:
            operation_model_or_client: Either a boto3 client or an operation model
            operation_name: The name of the operation (required if first arg is client)

        Returns:
            Tuple containing:
            - properties: Dict of parameter properties
            - required: Set of required parameter names
            - param_mapping: Dict mapping snake_case to original names
        """
        schema = self.extract_parameter_schema(operation_model_or_client, operation_name)
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        param_mapping = self.create_parameter_mapping(schema)

        return properties, required, param_mapping

    def validate_parameters(
        self, parameters: Dict[str, Any], schema: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate parameters against schema.

        Args:
            parameters: Dictionary of provided parameters
            schema: Parameter schema to validate against

        Returns:
            Tuple[bool, List[str]]: (is_valid, validation_errors)
        """
        required = set(schema.get("required", []))
        return self.validator.validate_required_parameters(parameters, required)

    def normalize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize parameter values for consistent processing.

        Args:
            parameters: Dictionary of parameters to normalize

        Returns:
            Dict[str, Any]: Normalized parameters
        """
        return self.validator.normalize_parameter_values(parameters)

    # Convenience methods for name conversion
    def to_snake_case(self, name: str) -> str:
        """Convert PascalCase/camelCase to snake_case."""
        return self.name_mapper.to_snake_case(name)

    def to_kebab_case(self, name: str) -> str:
        """Convert PascalCase to kebab-case."""
        return self.name_mapper.to_kebab_case(name)

    def to_camel_case(self, snake_name: str) -> str:
        """Convert snake_case to camelCase."""
        return self.name_mapper.to_camel_case(snake_name)
