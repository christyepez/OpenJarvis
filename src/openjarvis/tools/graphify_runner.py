"""Portable Graphify launcher that avoids blocked uv tool shims."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _uv_tool_dir() -> Path | None:
    try:
        result = subprocess.run(
            ["uv", "tool", "dir"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return Path(value) if value else None


def _graphify_site_packages(tool_dir: Path) -> list[Path]:
    root = tool_dir / "graphifyy"
    candidates = [root / "Lib" / "site-packages"]
    candidates.extend(sorted((root / "lib").glob("python*/site-packages")))
    return [path for path in candidates if path.is_dir()]


def ensure_graphify_importable() -> bool:
    """Make an installed Graphify uv-tool environment importable."""
    if importlib.util.find_spec("graphify") is not None:
        return True

    tool_dir = _uv_tool_dir()
    if tool_dir is None:
        return False

    for site_packages in _graphify_site_packages(tool_dir):
        value = str(site_packages)
        if value not in sys.path:
            sys.path.insert(0, value)
        if importlib.util.find_spec("graphify") is not None:
            return True
    return False


def main(argv: Sequence[str] | None = None) -> int:
    """Run Graphify in-process using the current approved Python executable."""
    if not ensure_graphify_importable():
        raise SystemExit(
            "Graphify is not installed. Run: "
            'uv tool install "graphifyy[mcp,office,pdf,svg,leiden]"'
        )

    from graphify.__main__ import main as graphify_main

    original_argv = sys.argv[:]
    try:
        sys.argv = ["graphify", *(list(argv) if argv is not None else sys.argv[1:])]
        result = graphify_main()
        return int(result or 0)
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
