# Official MCP Registry: steps (needs approval)
1. (Done) MCPB bundle attached to GitHub Release v0.1.0; server.json uses registryType "mcpb", so no PyPI account is needed.
2. Install mcp-publisher (github.com/modelcontextprotocol/registry releases).
3. `mcp-publisher login github`: a device-code login in the browser as Shashwat-Kumar.
4. `mcp-publisher publish` (reads ../server.json; schema 2025-12-11).
Alternative with no PyPI: build an `.mcpb` bundle, attach it to a GitHub Release, and change `packages[0]` to `registryType: "mcpb"`.
