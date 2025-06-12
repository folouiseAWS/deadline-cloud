"""
Tests for DynamicURIPatternGenerator.
Pure logic tests - no mocking required.
"""

import pytest
from deadline.mcp.uri_pattern_generator import DynamicURIPatternGenerator


class TestDynamicURIPatternGenerator:
    def setup_method(self):
        self.generator = DynamicURIPatternGenerator()

    def test_simple_farm_hierarchy(self):
        """Test basic farm resource pattern generation."""
        schema = {"properties": {"farmId": {"type": "string"}}}

        # List operation
        pattern = self.generator.generate_pattern("ListQueues", schema)
        assert pattern == "deadline://farm/{farm_id}/queues"

        # Get operation
        schema_with_queue = {
            "properties": {"farmId": {"type": "string"}, "queueId": {"type": "string"}}
        }
        pattern = self.generator.generate_pattern("GetQueue", schema_with_queue)
        assert pattern == "deadline://farm/{farm_id}/queue/{queue_id}"

    def test_complex_hierarchy(self):
        """Test complex farm -> queue -> job hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "jobId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetJob", schema)
        assert pattern == "deadline://farm/{farm_id}/queue/{queue_id}/job/{job_id}"

    def test_search_operations(self):
        """Test search operation pattern generation."""
        schema = {"properties": {"farmId": {"type": "string"}}}

        pattern = self.generator.generate_pattern("SearchJobs", schema)
        assert pattern == "deadline://farm/{farm_id}/jobs/search"

    def test_fleet_hierarchy(self):
        """Test farm -> fleet -> worker hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "fleetId": {"type": "string"},
                "workerId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetWorker", schema)
        assert pattern == "deadline://farm/{farm_id}/fleet/{fleet_id}/worker/{worker_id}"

    def test_list_operations(self):
        """Test list operation patterns with different hierarchies."""
        # Simple list
        schema = {"properties": {"farmId": {"type": "string"}}}
        pattern = self.generator.generate_pattern("ListFleets", schema)
        assert pattern == "deadline://farm/{farm_id}/fleets"

        # Nested list
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
            }
        }
        pattern = self.generator.generate_pattern("ListJobs", schema)
        assert pattern == "deadline://farm/{farm_id}/queue/{queue_id}/jobs"

    def test_resource_type_extraction(self):
        """Test resource type extraction from operation names."""
        # Test PascalCase to kebab-case conversion
        assert self.generator._extract_resource_type("GetFarm") == "farm"
        assert self.generator._extract_resource_type("ListQueues") == "queues"
        assert self.generator._extract_resource_type("GetLicenseEndpoint") == "license-endpoint"
        assert self.generator._extract_resource_type("SearchJobParameters") == "job-parameters"
        assert (
            self.generator._extract_resource_type("CreateQueueFleetAssociation")
            == "queue-fleet-association"
        )

    def test_operation_type_classification(self):
        """Test operation type classification."""
        assert self.generator._get_operation_type("ListFarms") == "list"
        assert self.generator._get_operation_type("GetFarm") == "get"
        assert self.generator._get_operation_type("DescribeFarm") == "get"
        assert self.generator._get_operation_type("SearchJobs") == "search"
        assert self.generator._get_operation_type("CreateFarm") == "action"
        assert self.generator._get_operation_type("UpdateQueue") == "action"
        assert self.generator._get_operation_type("DeleteJob") == "action"

    def test_hierarchy_inference(self):
        """Test resource hierarchy inference from parameters."""
        # Farm only
        properties = {"farmId": {"type": "string"}}
        hierarchy = self.generator._infer_resource_hierarchy(properties)
        assert hierarchy == ["farm/{farm_id}"]

        # Farm + Queue
        properties = {"farmId": {"type": "string"}, "queueId": {"type": "string"}}
        hierarchy = self.generator._infer_resource_hierarchy(properties)
        assert hierarchy == ["farm/{farm_id}", "queue/{queue_id}"]

        # Farm + Fleet + Worker
        properties = {
            "farmId": {"type": "string"},
            "fleetId": {"type": "string"},
            "workerId": {"type": "string"},
        }
        hierarchy = self.generator._infer_resource_hierarchy(properties)
        assert hierarchy == ["farm/{farm_id}", "fleet/{fleet_id}", "worker/{worker_id}"]

        # Farm + Queue + Job + Step + Task
        properties = {
            "farmId": {"type": "string"},
            "queueId": {"type": "string"},
            "jobId": {"type": "string"},
            "stepId": {"type": "string"},
            "taskId": {"type": "string"},
        }
        hierarchy = self.generator._infer_resource_hierarchy(properties)
        expected = [
            "farm/{farm_id}",
            "queue/{queue_id}",
            "job/{job_id}",
            "step/{step_id}",
            "task/{task_id}",
        ]
        assert hierarchy == expected

    def test_budget_hierarchy(self):
        """Test farm -> budget hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "budgetId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetBudget", schema)
        assert pattern == "deadline://farm/{farm_id}/budget/{budget_id}"

    def test_license_endpoint_hierarchy(self):
        """Test farm -> license-endpoint hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "licenseEndpointId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetLicenseEndpoint", schema)
        assert pattern == "deadline://farm/{farm_id}/license-endpoint/{license_endpoint_id}"

    def test_session_hierarchy(self):
        """Test farm -> queue -> job -> session hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "jobId": {"type": "string"},
                "sessionId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetSession", schema)
        # Actual output doesn't duplicate the resource type
        expected = "deadline://farm/{farm_id}/queue/{queue_id}/job/{job_id}/session/{session_id}"
        assert pattern == expected

    def test_plural_resource_handling(self):
        """Test handling of resource names that already end in 's'."""
        # Resource already plural
        schema = {"properties": {"farmId": {"type": "string"}}}
        pattern = self.generator.generate_pattern("ListQueues", schema)
        assert pattern == "deadline://farm/{farm_id}/queues"  # Should not double-pluralize

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty properties - no hierarchy means direct path
        schema = {"properties": {}}
        pattern = self.generator.generate_pattern("GetUnknown", schema)
        # When no hierarchy, we get deadline:// + unknown/{unknown_id} (no extra slash)
        assert pattern == "deadline://unknown/{unknown_id}"

        # No farm hierarchy - should still work
        schema = {"properties": {"customId": {"type": "string"}}}
        pattern = self.generator.generate_pattern("GetCustomResource", schema)
        assert pattern == "deadline://custom-resource/{custom_resource_id}"

    def test_action_operations(self):
        """Test non-CRUD operations that become actions."""
        schema = {"properties": {"farmId": {"type": "string"}}}

        # Create, Update, Delete operations
        pattern = self.generator.generate_pattern("CreateFarm", schema)
        assert pattern == "deadline://farm/{farm_id}/"

        pattern = self.generator.generate_pattern("UpdateQueue", schema)
        assert pattern == "deadline://farm/{farm_id}/"

        pattern = self.generator.generate_pattern("DeleteJob", schema)
        assert pattern == "deadline://farm/{farm_id}/"

    def test_complex_step_task_hierarchy(self):
        """Test the full step -> task hierarchy."""
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "jobId": {"type": "string"},
                "stepId": {"type": "string"},
                "taskId": {"type": "string"},
            }
        }

        pattern = self.generator.generate_pattern("GetTask", schema)
        expected = (
            "deadline://farm/{farm_id}/queue/{queue_id}/job/{job_id}/step/{step_id}/task/{task_id}"
        )
        assert pattern == expected

    def test_no_farm_id_fallback(self):
        """Test behavior when farmId is not present."""
        schema = {"properties": {"customParam": {"type": "string"}}}

        pattern = self.generator.generate_pattern("ListCustom", schema)
        # No hierarchy means deadline:// + customs (no extra slash)
        assert pattern == "deadline://customs"

        pattern = self.generator.generate_pattern("GetCustom", schema)
        assert pattern == "deadline://custom/{custom_id}"

    def test_global_operations_no_hierarchy(self):
        """Test global operations that don't have farm hierarchy."""
        schema = {"properties": {}}

        # Test list operations without hierarchy
        pattern = self.generator.generate_pattern("ListFarms", schema)
        assert pattern == "deadline://farms"

        pattern = self.generator.generate_pattern("ListMonitors", schema)
        assert pattern == "deadline://monitors"

        pattern = self.generator.generate_pattern("ListLicenseEndpoints", schema)
        assert pattern == "deadline://license-endpoints"

        # Test get operations without hierarchy
        pattern = self.generator.generate_pattern("GetFarm", schema)
        assert pattern == "deadline://farm/{farm_id}"

        pattern = self.generator.generate_pattern("GetMonitor", schema)
        assert pattern == "deadline://monitor/{monitor_id}"

        pattern = self.generator.generate_pattern("GetLicenseEndpoint", schema)
        assert pattern == "deadline://license-endpoint/{license_endpoint_id}"

    def test_special_case_association_operations(self):
        """Test special case association operations that need both resource IDs."""
        # ListQueueFleetAssociations - needs all three IDs
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "fleetId": {"type": "string"},
            }
        }
        result = self.generator.generate_pattern("ListQueueFleetAssociations", schema)
        assert result == "deadline://farm/{farm_id}/queue/{queue_id}/fleet-associations/{fleet_id}"

        # ListQueueLimitAssociations - needs all three IDs
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "limitId": {"type": "string"},
            }
        }
        result = self.generator.generate_pattern("ListQueueLimitAssociations", schema)
        assert result == "deadline://farm/{farm_id}/queue/{queue_id}/limit-associations/{limit_id}"

    def test_special_case_session_operations(self):
        """Test special case session operations that need full session context."""
        # ListSessionActions - needs full session context
        schema = {
            "properties": {
                "farmId": {"type": "string"},
                "queueId": {"type": "string"},
                "jobId": {"type": "string"},
                "sessionId": {"type": "string"},
                "taskId": {"type": "string"},
            }
        }
        result = self.generator.generate_pattern("ListSessionActions", schema)
        assert (
            result
            == "deadline://farm/{farm_id}/queue/{queue_id}/job/{job_id}/session/{session_id}/task/{task_id}/actions"
        )

    def test_special_case_cross_hierarchy_search(self):
        """Test special case cross-hierarchy search operations."""
        # SearchSteps - job-scoped, not queue-scoped
        schema = {"properties": {"farmId": {"type": "string"}, "jobId": {"type": "string"}}}
        result = self.generator.generate_pattern("SearchSteps", schema)
        assert result == "deadline://farm/{farm_id}/job/{job_id}/steps/search"

        # SearchTasks - job-scoped, not queue-scoped
        schema = {"properties": {"farmId": {"type": "string"}, "jobId": {"type": "string"}}}
        result = self.generator.generate_pattern("SearchTasks", schema)
        assert result == "deadline://farm/{farm_id}/job/{job_id}/tasks/search"
