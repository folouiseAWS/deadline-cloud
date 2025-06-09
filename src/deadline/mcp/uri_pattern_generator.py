"""
Dynamic URI pattern generation for MCP resources.
Infers hierarchical patterns from operation parameters.
"""

from typing import Dict, Any, List
import re


class DynamicURIPatternGenerator:
    """Generates URI patterns dynamically from operation schemas."""

    def generate_pattern(self, operation_name: str, schema: Dict[str, Any]) -> str:
        """Generate URI pattern using intelligent analysis of parameters."""
        properties = schema.get("properties", {})

        # Analyze parameter relationships dynamically
        hierarchy = self._infer_resource_hierarchy(properties)
        resource_type = self._extract_resource_type(operation_name)
        operation_type = self._get_operation_type(operation_name)

        return self._build_hierarchical_pattern(hierarchy, resource_type, operation_type)

    def _infer_resource_hierarchy(self, properties: Dict) -> List[str]:
        """Dynamically determine resource hierarchy from parameters."""
        hierarchy = []

        # Build hierarchy based on common AWS Deadline patterns
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

    def _build_hierarchical_pattern(
        self, hierarchy: List[str], resource_type: str, op_type: str
    ) -> str:
        """Build final URI pattern from inferred hierarchy."""
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
            # Individual resource endpoint - check if already in hierarchy to avoid duplication
            id_param = f"{resource_type.replace('-', '_')}_id"
            resource_segment = f"{resource_type}/{{{id_param}}}"

            # Check if the resource is already at the end of the hierarchy
            if hierarchy and hierarchy[-1].startswith(f"{resource_type}/{{"):
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
