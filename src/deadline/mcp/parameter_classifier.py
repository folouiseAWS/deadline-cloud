"""
Dynamic parameter classification for MCP server.
Replaces hardcoded exclusion lists with pattern-based rules.
"""

import re
from typing import Set, List
from enum import Enum


class ParameterType(Enum):
    PAGINATION = "pagination"
    FILTER = "filter"
    IDENTIFIER = "identifier"
    DATA = "data"


class DynamicParameterClassifier:
    """Classifies parameters dynamically using pattern recognition."""

    # Pattern-based rules instead of hardcoded lists
    PAGINATION_PATTERNS = [
        r".*[Tt]oken$",  # nextToken, continuationToken, startToken
        r"^max.*$",  # maxResults, maxItems
        r"^page.*$",  # pageSize, pageOffset
        r"^limit$",  # limit
        r"^offset$",  # offset
        r"^marker$",  # marker
        r"^item[Oo]ffset$",  # itemOffset
    ]

    FILTER_PATTERNS = [
        r"^.*[Ff]ilter.*$",  # filterExpressions, any*Filter*
        r"^.*[Ss]ort.*$",  # sortBy, sortOrder, sortExpressions
        r"^.*[Ss]earch.*$",  # searchTerm, any*Search*
        r"^status$",  # status
        r"^state$",  # state
        r"^type$",  # type (when used as filter)
        r"^category$",  # category
        r"^displayName$",  # displayName (often a filter)
        r"^name$",  # name (often a filter)
        r"^.*[Ii]ds$",  # queueIds, fleetIds (array filters)
    ]

    def classify_parameter(self, param_name: str, operation_name: str) -> ParameterType:
        """Dynamically classify parameter type."""
        if self._matches_patterns(param_name, self.PAGINATION_PATTERNS):
            return ParameterType.PAGINATION
        if self._matches_patterns(param_name, self.FILTER_PATTERNS):
            return ParameterType.FILTER
        if param_name.lower().endswith("id") or param_name.lower().endswith("arn"):
            return ParameterType.IDENTIFIER
        return ParameterType.DATA

    def should_include_in_function_signature(
        self, param_name: str, operation_name: str, has_uri_params: bool = True
    ) -> bool:
        """Dynamic decision for parameter inclusion in function signature."""
        param_type = self.classify_parameter(param_name, operation_name)

        # Always exclude pagination parameters from function signatures
        if param_type == ParameterType.PAGINATION:
            return False

        # For List/Search operations, exclude filter parameters
        # (they're not in URI patterns for MCP resources)
        if operation_name.startswith(("List", "Search")) and param_type == ParameterType.FILTER:
            return False

        # Include identifiers and data parameters
        return param_type in [ParameterType.IDENTIFIER, ParameterType.DATA]

    def get_excluded_parameters(self, operation_name: str) -> Set[str]:
        """Get parameters that should be excluded (for backward compatibility)."""
        # This will be used to gradually replace hardcoded exclusion lists
        excluded = set()

        # Always exclude pagination
        excluded.update(self._get_pagination_exclusions())

        # For List/Search operations, also exclude filters
        if operation_name.startswith(("List", "Search", "Query")):
            excluded.update(self._get_filter_exclusions())

        return excluded

    def _matches_patterns(self, param_name: str, patterns: List[str]) -> bool:
        """Check if parameter matches any pattern."""
        return any(re.match(pattern, param_name, re.IGNORECASE) for pattern in patterns)

    def _get_pagination_exclusions(self) -> Set[str]:
        """Get common pagination parameter names for backward compatibility."""
        return {
            "nextToken",
            "maxResults",
            "maxItems",
            "pageSize",
            "limit",
            "offset",
            "marker",
            "continuationToken",
            "startToken",
            "itemOffset",
        }

    def _get_filter_exclusions(self) -> Set[str]:
        """Get common filter parameter names for backward compatibility."""
        return {
            "filterExpressions",
            "sortExpressions",
            "queueIds",
            "fleetIds",
            "status",
            "state",
            "type",
            "category",
            "filter",
            "search",
            "sortBy",
            "sortOrder",
            "orderBy",
            "direction",
            "displayName",
            "name",
        }
