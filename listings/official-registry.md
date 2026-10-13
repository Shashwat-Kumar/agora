# Official MCP Registry (no PyPI)

`server.json` uses schema `2025-12-11` and `registryType: "mcpb"`. The package is the GitHub Release asset, so no PyPI account is required. The registry rejects `registryBaseUrl` on MCPB packages; the full download URL goes in `identifier`, and `fileSha256` is required. During publish the registry HEADs that URL and accepts HTTP 200 or a redirect (GitHub returns 302).

Build the bundle (sha256 must stay equal to `packages[0].fileSha256`):

```bash
python3 scripts/build_mcpb.py
```

`dist/agora-mcp.mcpb` is that file. Release **v0.1.0** already has `agora-mcp.mcpb` with the same sha256. Do not create another release unless that asset is gone.

## Commands the owner runs

Install the publisher, then authenticate as GitHub user **Shashwat-Kumar** (the namespace `io.github.Shashwat-Kumar` is case-sensitive) and publish from the repo root:

```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
sudo mv mcp-publisher /usr/local/bin/

mcp-publisher login github
mcp-publisher publish
```

`mcp-publisher publish` reads `./server.json`. If the v0.1.0 asset is missing or was replaced with different bytes, upload the committed bundle first (this does not create a release):

```bash
gh release upload v0.1.0 dist/agora-mcp.mcpb --clobber --repo Shashwat-Kumar/agora
curl -I https://github.com/Shashwat-Kumar/agora/releases/download/v0.1.0/agora-mcp.mcpb
```
