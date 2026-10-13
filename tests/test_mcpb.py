"""The MCPB bundle is the GitHub Release asset named in server.json."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _builder():
    spec = importlib.util.spec_from_file_location("build_mcpb", ROOT / "scripts" / "build_mcpb.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcpb_sha_matches_server_json_and_committed_asset():
    module = _builder()
    data = module.build_bytes()
    digest = hashlib.sha256(data).hexdigest()
    server = json.loads((ROOT / "server.json").read_text())
    package = server["packages"][0]
    assert server["$schema"].endswith("/2025-12-11/server.schema.json")
    assert package["registryType"] == "mcpb"
    assert package["identifier"] == "https://github.com/Shashwat-Kumar/agora/releases/download/v0.1.0/agora-mcp.mcpb"
    assert package["transport"]["type"] == "stdio"
    assert "registryBaseUrl" not in package
    assert package["fileSha256"] == digest
    assert hashlib.sha256((ROOT / "dist" / "agora-mcp.mcpb").read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(ROOT / "dist" / "agora-mcp.mcpb") as archive:
        names = archive.namelist()
    assert "agora/mcp_server.py" in names and "manifest.json" in names and "run_mcp.py" in names


def test_mcpb_entry_point_speaks_stdio(tmp_path):
    module = _builder()
    bundle = tmp_path / "agora-mcp.mcpb"
    bundle.write_bytes(module.build_bytes())
    dest = tmp_path / "unpacked"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(dest)
    message = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    proc = subprocess.run(
        [sys.executable, str(dest / "run_mcp.py")],
        input=message,
        text=True,
        capture_output=True,
        cwd=dest,
        timeout=10,
        check=True,
    )
    reply = json.loads(proc.stdout.splitlines()[0])
    assert reply["result"]["serverInfo"] == {"name": "agora", "version": "0.1.0"}
    assert reply["result"]["protocolVersion"] == "2025-06-18"
