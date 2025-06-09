"""Tests for MCP server utility functions."""

from unittest.mock import Mock
from typing import Dict, Any

from deadline.mcp.utils import (
    extract_service_model_parameters,
    generate_typed_signature,
    map_aws_type_to_python,
    extract_operation_documentation,
    strip_html_tags,
)


class TestExtractServiceModelParameters:
    """Test parameter extraction from boto3 service models."""

    def test_extract_optional_parameters(self, real_list_farms_operation):
        """Test extracting optional parameters from real service model."""
        params = extract_service_model_parameters(real_list_farms_operation)

        # Real ListFarms has: nextToken, principalId, maxResults
        assert "maxResults" in params
        assert "nextToken" in params
        assert "principalId" in params

        # Check parameter details
        max_results = params["maxResults"]
        assert max_results["type"] == "integer"
        assert max_results["required"] is False
        # Real AWS docs will have HTML tags
        assert "result" in max_results["documentation"].lower()

        next_token = params["nextToken"]
        assert next_token["type"] == "string"
        assert next_token["required"] is False
        assert "token" in next_token["documentation"].lower()

        principal_id = params["principalId"]
        assert principal_id["type"] == "string"
        assert principal_id["required"] is False

    def test_extract_required_parameters(self, real_create_farm_operation):
        """Test extracting required parameters from service model."""
        params = extract_service_model_parameters(real_create_farm_operation)

        # Real CreateFarm has: clientToken, displayName, description, kmsKeyArn, tags
        assert "displayName" in params
        assert "description" in params
        assert "kmsKeyArn" in params
        assert "clientToken" in params
        assert "tags" in params

        # Check required parameter
        display_name = params["displayName"]
        assert display_name["type"] == "string"
        assert display_name["required"] is True
        # Real AWS docs have HTML tags
        assert "display name" in display_name["documentation"].lower()

        # Check optional parameter
        description = params["description"]
        assert description["type"] == "string"
        assert description["required"] is False
        assert "description" in description["documentation"].lower()

    def test_extract_no_parameters(self):
        """Test operation with no input parameters."""
        operation = Mock()
        operation.input_shape = None

        params = extract_service_model_parameters(operation)
        assert params == {}


class TestMapAwsTypeToPython:
    """Test AWS type to Python type mapping."""

    def test_string_mapping(self):
        """Test string type mapping."""
        result = map_aws_type_to_python("string")
        assert result is str

    def test_integer_mapping(self):
        """Test integer type mapping."""
        result = map_aws_type_to_python("integer")
        assert result is int

    def test_boolean_mapping(self):
        """Test boolean type mapping."""
        result = map_aws_type_to_python("boolean")
        assert result is bool

    def test_long_mapping(self):
        """Test long type mapping."""
        result = map_aws_type_to_python("long")
        assert result is int

    def test_float_mapping(self):
        """Test float type mapping."""
        result = map_aws_type_to_python("float")
        assert result is float

    def test_double_mapping(self):
        """Test double type mapping."""
        result = map_aws_type_to_python("double")
        assert result is float

    def test_timestamp_mapping(self):
        """Test timestamp type mapping."""
        from datetime import datetime

        result = map_aws_type_to_python("timestamp")
        assert result == datetime

    def test_blob_mapping(self):
        """Test blob type mapping."""
        result = map_aws_type_to_python("blob")
        assert result is bytes

    def test_structure_mapping(self):
        """Test structure type mapping."""

        result = map_aws_type_to_python("structure")
        assert result == Dict[str, Any]

    def test_list_mapping_with_string_items(self):
        """Test list type mapping with string items."""
        from typing import List

        mock_shape = Mock()
        mock_shape.member = Mock()
        mock_shape.member.type_name = "string"

        result = map_aws_type_to_python("list", mock_shape)
        assert result == List[str]

    def test_list_mapping_with_complex_items(self):
        """Test list type mapping with structure items."""
        from typing import List

        mock_shape = Mock()
        mock_shape.member = Mock()
        mock_shape.member.type_name = "structure"

        result = map_aws_type_to_python("list", mock_shape)
        assert result == List[Dict[str, Any]]

    def test_map_mapping_with_string_values(self):
        """Test map type mapping with string values."""

        mock_shape = Mock()
        mock_shape.value = Mock()
        mock_shape.value.type_name = "string"

        result = map_aws_type_to_python("map", mock_shape)
        assert result == Dict[str, str]

    def test_map_mapping_with_complex_values(self):
        """Test map type mapping with structure values."""

        mock_shape = Mock()
        mock_shape.value = Mock()
        mock_shape.value.type_name = "structure"

        result = map_aws_type_to_python("map", mock_shape)
        assert result == Dict[str, Dict[str, Any]]

    def test_circular_reference_detection(self):
        """Test circular reference detection prevents infinite recursion."""
        from typing import List

        mock_shape = Mock()
        mock_shape.member = mock_shape  # Circular reference
        mock_shape.type_name = "list"

        result = map_aws_type_to_python("list", mock_shape)
        assert result == List[Any]  # Should fall back to Any due to circular reference

    def test_nested_list_of_maps(self):
        """Test nested complex types: List[Dict[str, str]]."""
        from typing import List

        # Create List[Map[string, string]]
        mock_list_shape = Mock()
        mock_map_shape = Mock()
        mock_string_shape = Mock()

        mock_string_shape.type_name = "string"
        mock_map_shape.type_name = "map"
        mock_map_shape.value = mock_string_shape
        mock_list_shape.type_name = "list"
        mock_list_shape.member = mock_map_shape

        result = map_aws_type_to_python("list", mock_list_shape)
        assert result == List[Dict[str, str]]

    def test_list_without_member_shape(self):
        """Test list type without member shape falls back to List[Any]."""
        from typing import List

        mock_shape = Mock()
        # No member attribute
        result = map_aws_type_to_python("list", mock_shape)
        assert result == List[Any]

    def test_map_without_value_shape(self):
        """Test map type without value shape falls back to Dict[str, Any]."""

        mock_shape = Mock()
        # No value attribute
        result = map_aws_type_to_python("map", mock_shape)
        assert result == Dict[str, Any]

    def test_unknown_type_defaults_to_any(self):
        """Test unknown type defaults to Any."""
        result = map_aws_type_to_python("unknown_type")
        assert result == Any


class TestGenerateTypedSignature:
    """Test generation of typed function signatures."""

    def test_generate_optional_parameters_signature(self):
        """Test generating signature for optional parameters."""
        params = {
            "maxResults": {"type": "integer", "required": False, "documentation": "Max results"},
            "nextToken": {"type": "string", "required": False, "documentation": "Token"},
        }

        signature_parts = generate_typed_signature(params)

        expected = ["maxResults: Optional[int] = None", "nextToken: Optional[str] = None"]

        assert signature_parts == expected

    def test_generate_mixed_parameters_signature(self):
        """Test generating signature for required and optional parameters."""
        params = {
            "displayName": {"type": "string", "required": True, "documentation": "Display name"},
            "description": {"type": "string", "required": False, "documentation": "Description"},
            "maxRetries": {"type": "integer", "required": True, "documentation": "Max retries"},
        }

        signature_parts = generate_typed_signature(params)

        # Required parameters should come first
        expected = ["displayName: str", "maxRetries: int", "description: Optional[str] = None"]

        assert signature_parts == expected

    def test_generate_no_parameters_signature(self):
        """Test generating signature for no parameters."""
        params: dict[str, dict[str, Any]] = {}

        signature_parts = generate_typed_signature(params)

        assert signature_parts == []


class TestStripHtmlTags:
    """Test HTML tag stripping functionality."""

    def test_strip_simple_html_tags(self):
        """Test stripping simple HTML tags."""
        text = "<p>Assigns a farm membership level to a member.</p>"
        result = strip_html_tags(text)
        assert result == "Assigns a farm membership level to a member."

    def test_strip_multiple_html_tags(self):
        """Test stripping multiple HTML tags."""
        text = "<p>Creates a new <code>farm</code> with the specified <em>name</em>.</p>"
        result = strip_html_tags(text)
        assert result == "Creates a new farm with the specified name."

    def test_strip_nested_html_tags(self):
        """Test stripping nested HTML tags."""
        text = "<div><p>This is <strong>important</strong> information.</p></div>"
        result = strip_html_tags(text)
        assert result == "This is important information."

    def test_strip_html_with_extra_whitespace(self):
        """Test stripping HTML tags and normalizing whitespace."""
        text = "<p>   This   has   extra   spaces.   </p>"
        result = strip_html_tags(text)
        assert result == "This has extra spaces."

    def test_strip_html_empty_text(self):
        """Test stripping HTML from empty text."""
        result = strip_html_tags("")
        assert result == ""

    def test_strip_html_none_text(self):
        """Test stripping HTML from None text."""
        result = strip_html_tags(None)
        assert result is None

    def test_strip_html_no_tags(self):
        """Test stripping HTML when no tags are present."""
        text = "This is plain text with no HTML tags."
        result = strip_html_tags(text)
        assert result == "This is plain text with no HTML tags."

    def test_strip_html_self_closing_tags(self):
        """Test stripping self-closing HTML tags."""
        text = "<p>Line one.<br/>Line two.</p>"
        result = strip_html_tags(text)
        assert result == "Line one.Line two."


class TestExtractOperationDocumentation:
    """Test extraction of operation documentation."""

    def test_extract_documentation_with_description(self, real_list_farms_operation):
        """Test extracting documentation when description exists."""
        doc = extract_operation_documentation(real_list_farms_operation)

        # Real AWS doc will be "Lists farms." after HTML stripping
        assert "farms" in doc.lower()
        assert len(doc) > 5

    def test_extract_documentation_no_description(self):
        """Test extracting documentation when no description exists."""
        operation = Mock()
        operation.name = "TestOperation"
        operation.documentation = None

        doc = extract_operation_documentation(operation)

        assert doc == "Execute TestOperation operation"

    def test_extract_documentation_empty_description(self):
        """Test extracting documentation when description is empty."""
        operation = Mock()
        operation.name = "TestOperation"
        operation.documentation = ""

        doc = extract_operation_documentation(operation)

        assert doc == "Execute TestOperation operation"

    def test_extract_documentation_with_html_tags(self):
        """Test extracting documentation with HTML tags gets cleaned."""
        operation = Mock()
        operation.documentation = "<p>Assigns a farm membership level to a member.</p>"

        doc = extract_operation_documentation(operation)

        assert doc == "Assigns a farm membership level to a member."
