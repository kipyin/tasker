"""Open files or folders with the OS default handler."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_path_with_default_handler(path: Path) -> None:
    """Open a path with the OS default app or file manager."""
    resolved = path.expanduser()
    if not resolved.exists():
        msg = f"Path does not exist: {resolved}"
        raise FileNotFoundError(msg)
    if sys.platform == "win32":
        os.startfile(resolved)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(resolved)], check=False)
    else:
        subprocess.run(["xdg-open", str(resolved)], check=False)
