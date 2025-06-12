"""
Deadline Cloud MCP Server

Model Context Protocol server for AWS Deadline Cloud APIs.
"""

from . import server
from .server import create_fastmcp_server

__version__ = "0.1.0"

__all__ = [
    "server",
    "create_fastmcp_server",
]
