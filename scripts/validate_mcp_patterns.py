#!/usr/bin/env python3
"""
Comprehensive validation script for MCP server URI patterns.
Tests all operations to detect regex issues and pattern problems.
"""

import re
import sys
import boto3
from typing import Dict, Any, List, Tuple
import logging

# Add src to path for imports
sys.path.insert(0, "src")

from deadline.mcp.uri_pattern_generator import DynamicURIPatternGenerator
from deadline.mcp.boto3_adaptor import (
    discover_apis,
    categorize_api,
    extract_parameter_schema,
    ResourceURIMapper,
)
from deadline.mcp.server import create_fastmcp_server

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MCPValidationError(Exception):
    """Custom exception for MCP validation errors."""

    pass


class MCPPatternValidator:
    """Validates MCP URI patterns for all operations."""

    def __init__(self):
        self.generator = DynamicURIPatternGenerator()
        self.errors = []
        self.warnings = []

    def validate_regex_pattern(self, pattern: str, operation_name: str) -> bool:
        """Validate that a URI pattern can be compiled as regex without duplicate groups."""
        try:
            # Convert URI pattern to regex for testing
            regex_pattern = pattern.replace("deadline://", "")

            # Find all named groups
            named_groups = re.findall(r"\{(\w+)\}", regex_pattern)

            # Check for duplicates
            if len(named_groups) != len(set(named_groups)):
                duplicates = [g for g in set(named_groups) if named_groups.count(g) > 1]
                self.errors.append(
                    f"{operation_name}: Duplicate named groups {duplicates} in pattern '{pattern}'"
                )
                return False

            # Try to compile as regex (convert {param} to (?P<param>[^/]+))
            test_regex = re.escape(regex_pattern)
            test_regex = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>[^/]+)", test_regex)

            try:
                re.compile(test_regex)
                return True
            except re.error as e:
                self.errors.append(
                    f"{operation_name}: Regex compilation failed for pattern '{pattern}': {str(e)}"
                )
                return False

        except Exception as e:
            self.errors.append(
                f"{operation_name}: Unexpected error validating pattern '{pattern}': {str(e)}"
            )
            return False

    def validate_operation(self, operation_name: str, schema: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a single operation's URI pattern."""
        try:
            # Generate pattern
            pattern = self.generator.generate_pattern(operation_name, schema)

            # Validate regex compilation
            is_valid = self.validate_regex_pattern(pattern, operation_name)

            return is_valid, pattern

        except Exception as e:
            self.errors.append(f"{operation_name}: Pattern generation failed: {str(e)}")
            return False, ""

    def validate_all_operations(self, operations: List[str], client) -> Dict[str, Any]:
        """Validate URI patterns for all operations."""
        results = {
            "total": len(operations),
            "passed": 0,
            "failed": 0,
            "patterns": {},
            "failures": [],
        }

        for operation in operations:
            try:
                schema = extract_parameter_schema(client, operation)
                is_valid, pattern = self.validate_operation(operation, schema)

                results["patterns"][operation] = {
                    "pattern": pattern,
                    "valid": is_valid,
                    "category": categorize_api(operation),
                }

                if is_valid:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["failures"].append(operation)

            except Exception as e:
                self.errors.append(f"{operation}: Validation error: {str(e)}")
                results["failed"] += 1
                results["failures"].append(operation)

        return results

    def test_server_creation(self) -> bool:
        """Test that the MCP server can be created without errors."""
        try:
            logger.info("Testing MCP server creation...")

            # This should not raise any regex compilation errors
            server = create_fastmcp_server()

            if server is None:
                self.errors.append("Server creation returned None")
                return False

            logger.info("✓ MCP server created successfully")
            return True

        except Exception as e:
            self.errors.append(f"Server creation failed: {str(e)}")
            return False

    def run_comprehensive_validation(self) -> bool:
        """Run all validation tests."""
        logger.info("Starting comprehensive MCP validation...")

        try:
            # Create boto3 client
            client = boto3.client("deadline", region_name="us-east-1")

            # Discover operations
            operations = discover_apis(client)
            logger.info(f"Discovered {len(operations)} operations")

            # Validate all patterns
            results = self.validate_all_operations(operations, client)

            # Print results
            logger.info(f"\n=== VALIDATION RESULTS ===")
            logger.info(f"Total operations: {results['total']}")
            logger.info(f"Passed: {results['passed']}")
            logger.info(f"Failed: {results['failed']}")

            if results["failed"] > 0:
                logger.error(f"\nFailed operations: {results['failures']}")

            # Test server creation
            server_ok = self.test_server_creation()

            # Print all errors
            if self.errors:
                logger.error(f"\n=== ERRORS ({len(self.errors)}) ===")
                for error in self.errors:
                    logger.error(f"  • {error}")

            if self.warnings:
                logger.warning(f"\n=== WARNINGS ({len(self.warnings)}) ===")
                for warning in self.warnings:
                    logger.warning(f"  • {warning}")

            # Summary
            total_errors = len(self.errors)
            validation_passed = results["failed"] == 0 and total_errors == 0 and server_ok

            logger.info(f"\n=== SUMMARY ===")
            logger.info(
                f"Pattern validation: {'✓ PASSED' if results['failed'] == 0 else '✗ FAILED'}"
            )
            logger.info(f"Server creation: {'✓ PASSED' if server_ok else '✗ FAILED'}")
            logger.info(f"Total errors: {total_errors}")
            logger.info(
                f"Overall result: {'✓ ALL TESTS PASSED' if validation_passed else '✗ VALIDATION FAILED'}"
            )

            return validation_passed

        except Exception as e:
            logger.error(f"Validation failed with exception: {str(e)}")
            return False


def main():
    """Main entry point."""
    validator = MCPPatternValidator()

    try:
        success = validator.run_comprehensive_validation()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
