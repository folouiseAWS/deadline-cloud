#!/usr/bin/env python3
"""
Script to count how many AWS Deadline Cloud operations are skipped during MCP server initialization.
"""

import logging
import sys
from io import StringIO
from deadline.mcp.server import _initialize_client_and_apis


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
        # Initialize the server to trigger operation registration
        _initialize_client_and_apis()

        # Get the log output
        log_output = log_capture.getvalue()

        # Count skipped operations
        skip_lines = [
            line for line in log_output.split("\n") if "Skipping resource registration" in line
        ]

        print(f"=== AWS Deadline Cloud MCP Server Operation Analysis ===\n")

        # Import the global variables to get counts
        from deadline.mcp.server import operations, tools, resources

        print(f"Total Operations Discovered: {len(operations)}")
        print(f"Tools Registered: {len(tools)}")
        print(f"Resources Registered: {len(resources)}")
        print(f"Operations Skipped: {len(skip_lines)}")
        print(
            f"Registration Success Rate: {((len(tools) + len(resources)) / len(operations) * 100):.1f}%"
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
        print(f"✅ Successfully registered: {len(tools) + len(resources)} operations")
        print(f"⚠️  Skipped due to schema issues: {len(skip_lines)} operations")
        print(f"📊 Total discovered: {len(operations)} operations")

        return len(skip_lines)

    except Exception as e:
        print(f"Error during analysis: {e}")
        return -1
    finally:
        logger.removeHandler(log_handler)
        log_capture.close()


if __name__ == "__main__":
    skipped_count = count_skipped_operations()
    sys.exit(0 if skipped_count >= 0 else 1)
