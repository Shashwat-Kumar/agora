# Official MCP Registry: steps (needs approval)
1. Publish the package to PyPI as `agora-mcp` 0.1.0 (`python -m build && twine upload dist/*`). Needs a PyPI account and token. The README already contains `mcp-name: io.github.Shashwat-Kumar/agora` for ownership verification.
2. Install mcp-publisher (github.com/modelcontextprotocol/registry releases).
3. `mcp-publisher login github`: a device-code login in the browser as Shashwat-Kumar.
4. `mcp-publisher publish` (reads ../server.json; schema 2025-12-11).
Alternative with no PyPI: build an `.mcpb` bundle, attach it to a GitHub Release, and change `packages[0]` to `registryType: "mcpb"`.
