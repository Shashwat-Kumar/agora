"""Entry point for the MCPB bundle: python run_mcp.py (stdio MCP server)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agora.mcp_server import main
main()
