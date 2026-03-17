"""Echo tool - demonstrates the simplest possible MCP tool pattern.

This tool shows:
- Basic input/output handling
- Input validation via type hints
- Structured response format
"""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP


def register_echo_tool(mcp: FastMCP, execute_tool: Callable) -> None:
    """Register the echo tool with the MCP server.

    Args:
        mcp: The FastMCP server instance
        execute_tool: Wrapper function for execution with timing/logging
    """

    @mcp.tool()
    def echo(message: str) -> dict:
        """Echo back the provided message.

        A simple tool that returns the input message. Useful for testing
        connectivity and basic tool invocation.

        Args:
            message: The message to echo back

        Returns:
            Dictionary containing the echoed message and metadata
        """
        return execute_tool(
            "echo",
            {"message": message},
            lambda: {
                "message": message,
                "length": len(message),
                "tool": "echo",
            },
        )
