#!/usr/bin/env python3
"""
Entry point for running the Deadline Cloud MCP server.
"""

from deadline.mcp.server import create_fastmcp_server
import logging
import sys


def main():
    """Main entry point for the MCP server."""
    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        server = create_fastmcp_server()
        print("✅ Server created successfully")
        print("📊 Server ready to handle tool requests")

        # Run the server with stdio transport
        server.run("stdio")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Server creation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
