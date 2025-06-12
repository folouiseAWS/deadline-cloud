"""
Tests for Dynamic Parameter Extractor components.

Tests the unified parameter extraction, mapping, and validation system
that consolidates parameter logic from across the MCP server.
"""

import pytest
from unittest.mock import Mock, MagicMock
from deadline.mcp.parameter_extractor import (
    ParameterTypeConverter,
    ParameterSchemaExtractor,
    ParameterValidator,
    DynamicParameterExtractor,
)
from deadline.mcp.utils import NameConverter


class TestParameterTypeConverter:
    """Test the ParameterTypeConverter component."""

    def setup_method(self):
        self.converter = ParameterTypeConverter()

    def test_basic_type_mapping(self):
        """Test conversion of basic AWS types to JSON schema."""
        # Mock shapes for different types
        string_shape = Mock()
        string_shape.type_name = "string"
        string_shape.documentation = "A string parameter"

        integer_shape = Mock()
        integer_shape.type_name = "integer"
        del integer_shape.documentation  # Remove auto-created documentation

        boolean_shape = Mock()
        boolean_shape.type_name = "boolean"
        del boolean_shape.documentation  # Remove auto-created documentation

        # Test conversions
        assert self.converter.convert_shape_to_schema(string_shape) == {
            "type": "string",
            "description": "A string parameter",
        }
        assert self.converter.convert_shape_to_schema(integer_shape) == {"type": "integer"}
        assert self.converter.convert_shape_to_schema(boolean_shape) == {"type": "boolean"}

    def test_list_type_conversion(self):
        """Test conversion of list types."""
        list_shape = Mock(spec=[])
        list_shape.type_name = "list"

        member_shape = Mock(spec=[])
        member_shape.type_name = "string"
        list_shape.member = member_shape

        result = self.converter.convert_shape_to_schema(list_shape)
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_map_type_conversion(self):
        """Test conversion of map types."""
        map_shape = Mock(spec=[])
        map_shape.type_name = "map"

        value_shape = Mock(spec=[])
        value_shape.type_name = "string"
        map_shape.value = value_shape

        result = self.converter.convert_shape_to_schema(map_shape)
        assert result == {"type": "object", "additionalProperties": {"type": "string"}}

    def test_structure_type_conversion(self):
        """Test conversion of structure types."""
        struct_shape = Mock()
        struct_shape.type_name = "structure"

        # Mock members
        member1 = Mock(spec=[])
        member1.type_name = "string"
        member2 = Mock(spec=[])
        member2.type_name = "integer"

        struct_shape.members = {"name": member1, "count": member2}

        result = self.converter.convert_shape_to_schema(struct_shape)
        expected = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
        }
        assert result == expected

    def test_circular_reference_handling(self):
        """Test handling of circular references in shapes."""
        shape = Mock()
        shape.type_name = "structure"
        shape.name = "CircularShape"
        shape.members = {"self": shape}  # Self-reference

        result = self.converter.convert_shape_to_schema(shape)

        # Should handle circular reference gracefully
        assert result["type"] == "object"
        assert "Circular reference" in result["properties"]["self"]["description"]

    def test_unknown_type_fallback(self):
        """Test fallback for unknown types."""
        unknown_shape = Mock()
        unknown_shape.type_name = "unknown_type"

        result = self.converter.convert_shape_to_schema(unknown_shape)
        assert result == {"type": "string"}

    def test_no_type_name_fallback(self):
        """Test fallback when shape has no type_name."""
        shape = Mock(spec=[])  # No type_name attribute

        result = self.converter.convert_shape_to_schema(shape)
        assert result == {"type": "string"}


class TestNameConverter:
    """Test the NameConverter utility."""

    def test_to_snake_case(self):
        """Test PascalCase/camelCase to snake_case conversion."""
        assert NameConverter.to_snake_case("farmId") == "farm_id"
        assert NameConverter.to_snake_case("maxResults") == "max_results"
        assert NameConverter.to_snake_case("resourceArn") == "resource_arn"
        assert NameConverter.to_snake_case("queueEnvironmentId") == "queue_environment_id"
        assert NameConverter.to_snake_case("id") == "id"
        assert NameConverter.to_snake_case("HTTPSProxy") == "h_t_t_p_s_proxy"

    def test_to_kebab_case(self):
        """Test PascalCase to kebab-case conversion."""
        assert NameConverter.to_kebab_case("QueueFleetAssociations") == "queue-fleet-associations"
        assert NameConverter.to_kebab_case("StorageProfile") == "storage-profile"
        assert NameConverter.to_kebab_case("JobAttachmentSettings") == "job-attachment-settings"
        assert NameConverter.to_kebab_case("Farm") == "farm"

    def test_to_camel_case(self):
        """Test snake_case to camelCase conversion."""
        assert NameConverter.to_camel_case("farm_id") == "farmId"
        assert NameConverter.to_camel_case("max_results") == "maxResults"
        assert NameConverter.to_camel_case("queue_environment_id") == "queueEnvironmentId"
        assert NameConverter.to_camel_case("id") == "id"


class TestParameterSchemaExtractor:
    """Test the ParameterSchemaExtractor component."""

    def setup_method(self):
        self.extractor = ParameterSchemaExtractor()

    def test_extract_from_client(self):
        """Test schema extraction from a boto3 client."""
        # Mock client and service model
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        # Mock input shape
        mock_input_shape = Mock(spec=[])
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = ["farmId"]

        # Mock members
        farm_id_shape = Mock(spec=[])
        farm_id_shape.type_name = "string"
        queue_id_shape = Mock(spec=[])
        queue_id_shape.type_name = "string"

        mock_input_shape.members = {"farmId": farm_id_shape, "queueId": queue_id_shape}

        result = self.extractor.extract_from_operation(mock_client, "GetQueue")

        expected = {
            "type": "object",
            "properties": {"farmId": {"type": "string"}, "queueId": {"type": "string"}},
            "required": ["farmId"],
        }
        assert result == expected

    def test_extract_from_client_simple(self):
        """Test schema extraction with simple operation."""
        # Mock client and service model
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        # Mock input shape
        mock_input_shape = Mock(spec=[])
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = []

        # Mock members
        name_shape = Mock(spec=[])
        name_shape.type_name = "string"

        mock_input_shape.members = {"name": name_shape}

        result = self.extractor.extract_from_operation(mock_client, "TestOperation")

        expected = {"type": "object", "properties": {"name": {"type": "string"}}, "required": []}
        assert result == expected

    def test_extract_no_input_shape(self):
        """Test extraction when operation has no input shape."""
        # Mock client and service model
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        mock_operation_model.input_shape = None

        result = self.extractor.extract_from_operation(mock_client, "NoInputOperation")
        assert result == {"type": "object", "properties": {}}

    def test_extract_exception_handling(self):
        """Test graceful handling of exceptions during extraction."""
        mock_client = Mock()
        mock_client._service_model = Mock()
        mock_client._service_model.operation_model.side_effect = Exception("Test error")

        result = self.extractor.extract_from_operation(mock_client, "BadOperation")
        assert result == {"type": "object", "properties": {}}


class TestParameterValidator:
    """Test the ParameterValidator component."""

    def test_validate_required_parameters_success(self):
        """Test successful validation of required parameters."""
        parameters = {"farmId": "farm-123", "queueId": "queue-456"}
        required = {"farmId", "queueId"}

        is_valid, missing = ParameterValidator.validate_required_parameters(parameters, required)

        assert is_valid is True
        assert missing == []

    def test_validate_required_parameters_missing(self):
        """Test validation with missing required parameters."""
        parameters = {"farmId": "farm-123"}
        required = {"farmId", "queueId", "jobId"}

        is_valid, missing = ParameterValidator.validate_required_parameters(parameters, required)

        assert is_valid is False
        assert set(missing) == {"queueId", "jobId"}

    def test_validate_required_parameters_none_values(self):
        """Test validation treats None values as missing."""
        parameters = {"farmId": "farm-123", "queueId": None}
        required = {"farmId", "queueId"}

        is_valid, missing = ParameterValidator.validate_required_parameters(parameters, required)

        assert is_valid is False
        assert missing == ["queueId"]

    def test_normalize_parameter_values(self):
        """Test parameter value normalization."""
        parameters = {
            "farmId": "farm-123",
            "maxResults": 10,
            "enabled": True,
            "tags": ["tag1", "tag2"],
            "metadata": {"key": "value"},
            "empty": None,
        }

        normalized = ParameterValidator.normalize_parameter_values(parameters)

        expected = {
            "farmId": "farm-123",
            "maxResults": "10",
            "enabled": "True",
            "tags": ["tag1", "tag2"],  # Lists preserved
            "metadata": {"key": "value"},  # Dicts preserved
            # None values filtered out
        }
        assert normalized == expected


class TestDynamicParameterExtractor:
    """Test the main DynamicParameterExtractor orchestrator."""

    def setup_method(self):
        self.extractor = DynamicParameterExtractor()

    def test_extract_parameter_schema_delegation(self):
        """Test that parameter schema extraction delegates correctly."""
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        # Mock simple input shape
        mock_input_shape = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = []
        mock_input_shape.members = {}

        result = self.extractor.extract_parameter_schema(mock_client, "TestOp")

        assert result["type"] == "object"
        assert "properties" in result

    def test_create_parameter_mapping(self):
        """Test parameter mapping creation from schema."""
        schema = {
            "type": "object",
            "properties": {"farmId": {"type": "string"}, "maxResults": {"type": "integer"}},
        }

        mapping = self.extractor.create_parameter_mapping(schema)

        expected = {"farm_id": "farmId", "max_results": "maxResults"}
        assert mapping == expected

    def test_extract_parameter_info_integration(self):
        """Test complete parameter info extraction."""
        # Mock a complete operation
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        # Mock input shape with required parameters
        mock_input_shape = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = ["farmId"]

        farm_id_shape = Mock()
        farm_id_shape.type_name = "string"
        max_results_shape = Mock()
        max_results_shape.type_name = "integer"

        mock_input_shape.members = {"farmId": farm_id_shape, "maxResults": max_results_shape}

        properties, required, param_mapping = self.extractor.extract_parameter_info(
            mock_client, "ListQueues"
        )

        # Validate all components
        assert "farmId" in properties
        assert "maxResults" in properties
        assert required == {"farmId"}
        assert param_mapping["farm_id"] == "farmId"
        assert param_mapping["max_results"] == "maxResults"

    def test_validate_parameters(self):
        """Test parameter validation against schema."""
        schema = {
            "type": "object",
            "properties": {"farmId": {"type": "string"}, "queueId": {"type": "string"}},
            "required": ["farmId"],
        }

        # Valid parameters
        valid_params = {"farmId": "farm-123", "queueId": "queue-456"}
        is_valid, errors = self.extractor.validate_parameters(valid_params, schema)
        assert is_valid is True
        assert errors == []

        # Invalid parameters (missing required)
        invalid_params = {"queueId": "queue-456"}
        is_valid, errors = self.extractor.validate_parameters(invalid_params, schema)
        assert is_valid is False
        assert "farmId" in errors

    def test_normalize_parameters(self):
        """Test parameter normalization."""
        params = {"farmId": "farm-123", "maxResults": 10, "enabled": True}

        normalized = self.extractor.normalize_parameters(params)

        expected = {"farmId": "farm-123", "maxResults": "10", "enabled": "True"}
        assert normalized == expected

    def test_name_conversion_methods(self):
        """Test that name conversion uses NameConverter directly (delegation methods removed)."""
        from deadline.mcp.utils import NameConverter

        # Delegation methods were removed per simplification - use NameConverter directly
        assert NameConverter.to_snake_case("farmId") == "farm_id"
        assert NameConverter.to_kebab_case("QueueFleetAssociations") == "queue-fleet-associations"
        assert NameConverter.to_camel_case("farm_id") == "farmId"

        # Verify delegation methods no longer exist
        assert not hasattr(self.extractor, "to_snake_case")
        assert not hasattr(self.extractor, "to_kebab_case")
        assert not hasattr(self.extractor, "to_camel_case")

    def test_component_initialization(self):
        """Test that all components are properly initialized."""
        assert self.extractor.schema_extractor is not None
        assert self.extractor.validator is not None
        assert self.extractor.type_converter is not None


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def setup_method(self):
        self.extractor = DynamicParameterExtractor()

    def test_list_operation_scenario(self):
        """Test complete workflow for a List operation."""
        # Mock ListQueues operation
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        # Mock typical List operation parameters
        mock_input_shape = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = ["farmId"]

        # Create shapes for typical List parameters
        shapes = {}
        for param_name, type_name in [
            ("farmId", "string"),
            ("maxResults", "integer"),
            ("nextToken", "string"),
            ("filterExpressions", "list"),
        ]:
            shape = Mock()
            shape.type_name = type_name
            if type_name == "list":
                member_shape = Mock()
                member_shape.type_name = "string"
                shape.member = member_shape
            shapes[param_name] = shape

        mock_input_shape.members = shapes

        # Extract complete info
        properties, required, param_mapping = self.extractor.extract_parameter_info(
            mock_client, "ListQueues"
        )

        # Validate extraction results
        assert len(properties) == 4
        assert "farmId" in properties
        assert "filterExpressions" in properties
        assert required == {"farmId"}
        assert param_mapping["farm_id"] == "farmId"
        assert param_mapping["filter_expressions"] == "filterExpressions"

        # Test validation
        valid_params = {"farmId": "farm-123"}
        is_valid, errors = self.extractor.validate_parameters(
            valid_params, {"type": "object", "properties": properties, "required": list(required)}
        )
        assert is_valid is True

    def test_get_operation_scenario(self):
        """Test complete workflow for a Get operation."""
        # Mock GetQueue operation - typically has required ID parameters
        mock_client = Mock()
        mock_service_model = Mock()
        mock_operation_model = Mock()

        mock_client._service_model = mock_service_model
        mock_service_model.operation_model.return_value = mock_operation_model

        mock_input_shape = Mock()
        mock_operation_model.input_shape = mock_input_shape
        mock_input_shape.required_members = ["farmId", "queueId"]

        # Typical Get operation parameters
        farm_id_shape = Mock()
        farm_id_shape.type_name = "string"
        queue_id_shape = Mock()
        queue_id_shape.type_name = "string"

        mock_input_shape.members = {"farmId": farm_id_shape, "queueId": queue_id_shape}

        properties, required, param_mapping = self.extractor.extract_parameter_info(
            mock_client, "GetQueue"
        )

        assert len(properties) == 2
        assert required == {"farmId", "queueId"}
        assert param_mapping["farm_id"] == "farmId"
        assert param_mapping["queue_id"] == "queueId"

        # Test validation requires both IDs
        incomplete_params = {"farmId": "farm-123"}
        is_valid, errors = self.extractor.validate_parameters(
            incomplete_params,
            {"type": "object", "properties": properties, "required": list(required)},
        )
        assert is_valid is False
        assert "queueId" in errors
