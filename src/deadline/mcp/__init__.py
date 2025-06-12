"""
Deadline Cloud MCP Server

Model Context Protocol server for AWS Deadline Cloud APIs.
"""


# Lazy import to avoid circular import warnings when running as module
def create_fastmcp_server():
    """Create and return a FastMCP server instance."""
    from .server import create_fastmcp_server as _create_server

    return _create_server()


__version__ = "0.1.0"

__all__ = [
    "create_fastmcp_server",
]
