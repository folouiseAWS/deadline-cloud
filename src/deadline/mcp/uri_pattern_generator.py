"""
Dynamic URI pattern generation for MCP resources.
Infers hierarchical patterns from operation parameters using actual AWS API parameter names.
"""

from typing import Dict, Any, List
import re


class DynamicURIPatternGenerator:
    """Generates URI patterns dynamically from operation schemas using actual parameter names."""

    def generate_pattern(self, operation_name: str, schema: Dict[str, Any]) -> str:
        """Generate URI pattern using actual parameter names from schema."""
        properties = schema.get("properties", {})

        # Tier 1: Check for special case operations first
        special_pattern = self._handle_special_case_operations(operation_name, properties)
        if special_pattern:
            return special_pattern

        # Tier 2: Standard hierarchical pattern generation
        hierarchy = self._infer_resource_hierarchy(properties)
        resource_type = self._extract_resource_type(operation_name)
        operation_type = self._get_operation_type(operation_name)

        return self._build_hierarchical_pattern(
            hierarchy, resource_type, operation_type, properties, operation_name
        )

    def _handle_special_case_operations(self, operation_name: str, properties: Dict) -> str:
        """Handle special case operations that don't follow standard hierarchy patterns."""

        # Association Operations - need both resource IDs in URI
        if operation_name == "ListQueueFleetAssociations":
            if "farmId" in properties and "queueId" in properties and "fleetId" in properties:
                return "deadline://farm/{farm_id}/queue/{queue_id}/fleet-associations/{fleet_id}"

        if operation_name == "ListQueueLimitAssociations":
            if "farmId" in properties and "queueId" in properties and "limitId" in properties:
                return "deadline://farm/{farm_id}/queue/{queue_id}/limit-associations/{limit_id}"

        # Session Operations - need full session context
        if operation_name == "ListSessionActions":
            required_params = {"farmId", "queueId", "jobId", "sessionId", "taskId"}
            if required_params.issubset(set(properties.keys())):
                return "deadline://farm/{farm_id}/queue/{queue_id}/job/{job_id}/session/{session_id}/task/{task_id}/actions"

        # Cross-hierarchy Search Operations - job-scoped, not queue-scoped
        if operation_name in ["SearchSteps", "SearchTasks"]:
            if "farmId" in properties and "jobId" in properties:
                resource_type = "steps" if "Steps" in operation_name else "tasks"
                return f"deadline://farm/{{farm_id}}/job/{{job_id}}/{resource_type}/search"

        return None  # Use standard hierarchy inference

    def _infer_resource_hierarchy(self, properties: Dict) -> List[str]:
        """Dynamically determine resource hierarchy from actual parameters."""
        hierarchy = []

        # Build hierarchy based on common AWS Deadline patterns using actual parameter names
        if "farmId" in properties:
            hierarchy.append("farm/{farm_id}")

            # Handle queue-based hierarchy
            if "queueId" in properties:
                hierarchy.append("queue/{queue_id}")

                if "jobId" in properties:
                    hierarchy.append("job/{job_id}")

                    if "stepId" in properties:
                        hierarchy.append("step/{step_id}")

                        if "taskId" in properties:
                            hierarchy.append("task/{task_id}")

                        if "sessionId" in properties:
                            hierarchy.append("session/{session_id}")

            # Handle job-based operations that don't have queueId but have jobId
            # (like SearchSteps, SearchTasks that search across queues but within a specific job context)
            elif "jobId" in properties and "queueIds" in properties:
                # For operations that have jobId + queueIds (plural), we still need queue in hierarchy
                # but we'll make it a placeholder since the actual queue comes from the job context
                hierarchy.append("queue/{queue_id}")
                hierarchy.append("job/{job_id}")

                if "stepId" in properties:
                    hierarchy.append("step/{step_id}")

                    if "taskId" in properties:
                        hierarchy.append("task/{task_id}")

            # Handle fleet-based hierarchy
            elif "fleetId" in properties:
                hierarchy.append("fleet/{fleet_id}")

                if "workerId" in properties:
                    hierarchy.append("worker/{worker_id}")

            # Handle other resource types
            elif "budgetId" in properties:
                hierarchy.append("budget/{budget_id}")

            elif "licenseEndpointId" in properties:
                hierarchy.append("license-endpoint/{license_endpoint_id}")

            # Handle limit operations
            elif "limitId" in properties:
                hierarchy.append("limit/{limit_id}")

        return hierarchy

    def _extract_resource_type(self, operation_name: str) -> str:
        """Extract resource type from operation name."""
        # Remove operation prefix
        match = re.search(r"(Get|List|Describe|Search|Create|Update|Delete)(.+)", operation_name)
        if match:
            resource_name = match.group(2)
            # Convert PascalCase to kebab-case
            return re.sub(r"(?<!^)(?=[A-Z])", "-", resource_name).lower()

        return "unknown"

    def _get_operation_type(self, operation_name: str) -> str:
        """Get operation type (list, get, search, etc.)."""
        if operation_name.startswith("List"):
            return "list"
        elif operation_name.startswith(("Get", "Describe")):
            return "get"
        elif operation_name.startswith("Search"):
            return "search"
        else:
            return "action"

    def _find_actual_id_parameter(
        self, properties: Dict, operation_name: str, resource_type: str
    ) -> str:
        """Find the actual ID parameter name from the schema for specific operations."""
        # Handle specific problematic operations with explicit mappings
        operation_id_mappings = {
            "GetQueueFleetAssociation": "fleetId",
            "GetQueueLimitAssociation": "limitId",
            "GetSessionsStatisticsAggregation": "aggregationId",
            "GetStorageProfileForQueue": "storageProfileId",
        }

        if operation_name in operation_id_mappings:
            api_param = operation_id_mappings[operation_name]
            if api_param in properties:
                # Convert camelCase to snake_case for URI
                snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", api_param).lower()
                return snake_case

        # For all other operations, use resource-based parameter names for consistency
        resource_snake = resource_type.replace("-", "_")
        return f"{resource_snake}_id"

    def _build_hierarchical_pattern(
        self,
        hierarchy: List[str],
        resource_type: str,
        op_type: str,
        properties: Dict,
        operation_name: str,
    ) -> str:
        """Build final URI pattern from inferred hierarchy using actual parameter names."""
        if hierarchy:
            base = "deadline://" + "/".join(hierarchy)
        else:
            base = "deadline://"

        if op_type == "list":
            # List operations - collection endpoint
            plural_resource = (
                resource_type + "s" if not resource_type.endswith("s") else resource_type
            )
            # Handle case where there's no hierarchy to avoid extra slash
            if hierarchy:
                return f"{base}/{plural_resource}"
            else:
                return f"{base}{plural_resource}"

        elif op_type in ["get", "describe"]:
            # Individual resource endpoint - use actual parameter name
            actual_id_param = self._find_actual_id_parameter(
                properties, operation_name, resource_type
            )
            resource_segment = f"{resource_type}/{{{actual_id_param}}}"

            # Check if the resource is already at the end of the hierarchy
            if hierarchy and any(f"/{{{actual_id_param}}}" in h for h in hierarchy):
                # Resource already in hierarchy, don't duplicate
                return base
            else:
                # Resource not in hierarchy, append it
                if hierarchy:
                    return f"{base}/{resource_segment}"
                else:
                    return f"{base}{resource_segment}"

        elif op_type == "search":
            # Search endpoint
            plural_resource = (
                resource_type + "s" if not resource_type.endswith("s") else resource_type
            )
            if hierarchy:
                return f"{base}/{plural_resource}/search"
            else:
                return f"{base}{plural_resource}/search"

        else:
            # Generic pattern for other operations
            return base if base.endswith("/") else f"{base}/"
