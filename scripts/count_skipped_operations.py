#!/usr/bin/env python3
"""
Script to count how many AWS Deadline Cloud operations are skipped during MCP server initialization.
"""

import logging
import sys
from io import StringIO
from deadline.mcp.server import get_boto3_client, auto_register_mcp_operations
from deadline.mcp.boto3_adaptor import discover_apis


def count_skipped_operations():
    """Count how many operations are skipped during server initialization."""

    # Capture log output
    log_capture = StringIO()
    log_handler = logging.StreamHandler(log_capture)
    log_handler.setLevel(logging.WARNING)

    # Set up logger to capture warnings
    logger = logging.getLogger("deadline.mcp.server")
    logger.setLevel(logging.WARNING)
    logger.addHandler(log_handler)

    try:
        # Create a mock FastMCP server for registration testing
        class MockFastMCP:
            def __init__(self):
                self.tools_count = 0
                self.resources_count = 0

            def tool(self, description=""):
                def decorator(func):
                    self.tools_count += 1
                    return func

                return decorator

            def resource(self, pattern, description=""):
                def decorator(func):
                    self.resources_count += 1
                    return func

                return decorator

        # Get client and discover operations
        client = get_boto3_client()
        operations = discover_apis(client)

        # Create mock server and register operations
        mock_server = MockFastMCP()
        tools_count, resources_count = auto_register_mcp_operations(mock_server, client)

        # Get the log output
        log_output = log_capture.getvalue()

        # Count skipped operations
        skip_lines = [
            line for line in log_output.split("\n") if "Skipping resource registration" in line
        ]

        print(f"=== AWS Deadline Cloud MCP Server Operation Analysis ===\n")

        print(f"Total Operations Discovered: {len(operations)}")
        print(f"Tools Registered: {tools_count}")
        print(f"Resources Registered: {resources_count}")
        print(f"Operations Skipped: {len(skip_lines)}")
        print(
            f"Registration Success Rate: {((tools_count + resources_count) / len(operations) * 100):.1f}%"
        )

        if skip_lines:
            print(f"\n=== Skipped Operations Details ===")
            for i, line in enumerate(skip_lines, 1):
                # Extract operation name and reason from log line
                if "Skipping resource registration for" in line:
                    parts = line.split("Skipping resource registration for ")[1]
                    operation_part = parts.split(" - has URI params")[0]
                    params_part = parts.split("has URI params ")[1].split(" but no properties")[0]
                    print(f"{i}. {operation_part} (URI params: {params_part})")

        print(f"\n=== Summary ===")
        print(f"✅ Successfully registered: {tools_count + resources_count} operations")
        print(f"⚠️  Skipped due to schema issues: {len(skip_lines)} operations")
        print(f"📊 Total discovered: {len(operations)} operations")

        return len(skip_lines)

    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback

        traceback.print_exc()
        return -1
    finally:
        logger.removeHandler(log_handler)
        log_capture.close()


if __name__ == "__main__":
    skipped_count = count_skipped_operations()
    sys.exit(0 if skipped_count >= 0 else 1)
