"""
Tests for DynamicParameterClassifier.
Pure logic tests - no mocking required.
"""

import pytest
from deadline.mcp.parameter_classifier import DynamicParameterClassifier, ParameterType


class TestDynamicParameterClassifier:
    def setup_method(self):
        self.classifier = DynamicParameterClassifier()

    def test_pagination_parameter_classification(self):
        """Test pagination parameter detection."""
        pagination_params = [
            "nextToken",
            "continuationToken",
            "startToken",  # *Token patterns
            "maxResults",
            "maxItems",  # max* patterns
            "pageSize",
            "pageOffset",  # page* patterns
            "limit",
            "offset",
            "marker",  # exact matches
            "itemOffset",  # itemOffset pattern
        ]

        for param in pagination_params:
            result = self.classifier.classify_parameter(param, "ListJobs")
            assert result == ParameterType.PAGINATION, f"Failed for parameter: {param}"

    def test_filter_parameter_classification(self):
        """Test filter parameter detection."""
        filter_params = [
            "filterExpressions",
            "customFilter",  # *Filter* patterns
            "sortBy",
            "sortOrder",
            "sortExpressions",  # *Sort* patterns
            "searchTerm",
            "searchQuery",  # *Search* patterns
            "status",
            "state",
            "type",
            "category",  # exact matches
            "displayName",
            "name",  # exact matches
            "queueIds",
            "fleetIds",
            "resourceIds",  # *Ids patterns
        ]

        for param in filter_params:
            result = self.classifier.classify_parameter(param, "ListJobs")
            assert result == ParameterType.FILTER, f"Failed for parameter: {param}"

    def test_identifier_parameter_classification(self):
        """Test identifier parameter detection."""
        id_params = [
            "farmId",
            "queueId",
            "jobId",
            "fleetId",  # *Id patterns
            "resourceArn",
            "topicArn",
            "roleArn",  # *Arn patterns
        ]

        for param in id_params:
            result = self.classifier.classify_parameter(param, "GetJob")
            assert result == ParameterType.IDENTIFIER, f"Failed for parameter: {param}"

    def test_data_parameter_classification(self):
        """Test data parameter detection (fallback case)."""
        data_params = [
            "description",
            "configuration",
            "metadata",
            "tags",
            "content",
            "priority",
        ]

        for param in data_params:
            result = self.classifier.classify_parameter(param, "CreateFarm")
            assert result == ParameterType.DATA, f"Failed for parameter: {param}"

    def test_function_signature_inclusion_logic(self):
        """Test which parameters should be in function signatures."""
        classifier = self.classifier

        # Pagination should never be included
        assert not classifier.should_include_in_function_signature("nextToken", "ListJobs")
        assert not classifier.should_include_in_function_signature("maxResults", "GetFarm")

        # Filters should not be included for List operations
        assert not classifier.should_include_in_function_signature("status", "ListJobs")
        assert not classifier.should_include_in_function_signature(
            "filterExpressions", "SearchTasks"
        )

        # Filters are excluded from function signatures (they're query/filter params)
        assert not classifier.should_include_in_function_signature("status", "CreateFarm")

        # Identifiers should always be included
        assert classifier.should_include_in_function_signature("farmId", "GetFarm")
        assert classifier.should_include_in_function_signature("queueId", "ListJobs")

        # Data parameters should always be included
        assert classifier.should_include_in_function_signature("description", "CreateFarm")
        assert classifier.should_include_in_function_signature("configuration", "UpdateQueue")

    def test_pattern_matching_case_insensitive(self):
        """Test that pattern matching is case insensitive."""
        # Test different cases for token patterns
        assert (
            self.classifier.classify_parameter("nextToken", "ListJobs") == ParameterType.PAGINATION
        )
        assert (
            self.classifier.classify_parameter("NextToken", "ListJobs") == ParameterType.PAGINATION
        )
        assert (
            self.classifier.classify_parameter("NEXTTOKEN", "ListJobs") == ParameterType.PAGINATION
        )

        # Test different cases for filter patterns
        assert (
            self.classifier.classify_parameter("filterExpressions", "ListJobs")
            == ParameterType.FILTER
        )
        assert (
            self.classifier.classify_parameter("FilterExpressions", "ListJobs")
            == ParameterType.FILTER
        )
        assert (
            self.classifier.classify_parameter("FILTEREXPRESSIONS", "ListJobs")
            == ParameterType.FILTER
        )

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty string should default to DATA
        assert self.classifier.classify_parameter("", "GetFarm") == ParameterType.DATA

        # Parameters that could match multiple patterns
        # "sortId" ends with "Id" (identifier) but also contains "sort" (filter)
        # Filter pattern should match first
        assert self.classifier.classify_parameter("sortId", "ListJobs") == ParameterType.FILTER

        # "filterId" should be filter (filter pattern matches first)
        assert self.classifier.classify_parameter("filterId", "ListJobs") == ParameterType.FILTER

        # Parameters with mixed patterns - first match wins
        assert (
            self.classifier.classify_parameter("maxFilterId", "ListJobs")
            == ParameterType.PAGINATION
        )  # max* wins
