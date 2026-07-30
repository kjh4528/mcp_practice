from mcp.server import MCPServer

# Initialize MCPServer
mcp = MCPServer("weather")

# Import tools so their @mcp.tool() decorators register against `mcp` above
import tools  # noqa: E402,F401

# Run the MCP server
if __name__ == "__main__":
    mcp.run(transport="stdio")
