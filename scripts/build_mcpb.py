#!/usr/bin/env python3
"""Build dist/agora-mcp.mcpb, the stdio bundle published as a GitHub Release asset.

Zip metadata is fixed (timestamp 2026-10-13 00:00:00, deflate level 6, Unix mode
0600) so the sha256 matches server.json and the v0.1.0 release asset.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "agora-mcp.mcpb"
STAMP = (2026, 10, 13, 0, 0, 0)
FILES = [
    "manifest.json",
    "run_mcp.py",
    "agora/__init__.py",
    "agora/mcp_server.py",
    "agora/protocol.py",
    "agora/moderation.py",
    "data/personas.json",
    "data/topics.json",
    "LICENSE",
    "README.md",
    "threads/seed-agent-credit-scores.json",
    "threads/seed-quantum-advantage-2026.json",
    "threads/seed-robot-liability.json",
]


def build_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name in FILES:
            info = zipfile.ZipInfo(filename=name, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, (ROOT / name).read_bytes(), compresslevel=6)
    return buf.getvalue()


def main() -> None:
    data = build_bytes()
    digest = hashlib.sha256(data).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    server = json.loads((ROOT / "server.json").read_text())
    expected = server["packages"][0]["fileSha256"]
    print(f"{digest}  {OUT.relative_to(ROOT)}")
    if digest != expected:
        print(f"sha256 does not match server.json fileSha256 ({expected})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
